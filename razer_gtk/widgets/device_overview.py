"""Device Overview screen: header + Lighting/DPI/Battery/Presets cards, all capability-gated."""

from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, GObject, Gtk

from razer_gtk.backend import device_images
from razer_gtk.backend import device_names
from razer_gtk.backend.device_adapter import DeviceCapabilities
from razer_gtk.i18n import _
from razer_gtk.widgets.cards.battery_card import BatteryCard
from razer_gtk.widgets.cards.dpi_card import DpiCard
from razer_gtk.widgets.cards.lighting_card import LightingCard
from razer_gtk.widgets.cards.presets_card import PresetsCard

DEVICE_TYPE_ICONS = {
    "mouse": "input-mouse-symbolic",
    "mousemat": "input-tablet-symbolic",
    "keyboard": "input-keyboard-symbolic",
    "keypad": "input-keyboard-symbolic",
    "headset": "audio-headset-symbolic",
    "accessory": "media-removable-symbolic",
}
DEFAULT_DEVICE_ICON = "input-gaming-symbolic"

# Wider than Adw.PreferencesPage's built-in clamp (fixed at 600px, no public
# API to change) so pill rows with many/long options (e.g. all 7 lighting
# effects) have room to lay out on one line instead of wrapping.
CONTENT_MAX_WIDTH = 1180


def _generic_icon_name(device) -> str:
    return DEVICE_TYPE_ICONS.get(getattr(device, "type", ""), DEFAULT_DEVICE_ICON)


class DeviceOverview(Gtk.Box):
    """The whole (and only) content screen for a selected device: header +
    Lighting/DPI/Battery/Presets cards, all capability-gated."""

    __gsignals__ = {
        "write-failed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "stage-editor-requested": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "reload-requested": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "baseline-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "dirty-detected": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "name-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(
        self,
        caps: DeviceCapabilities,
        perform_write_async: Callable[[Callable[[], None], Callable[[str | None], None]], None],
        open_color_picker: Callable[[str, Callable[[str], None]], None],
        snapshot: dict,
        perform_write_sync: Callable[[Callable[[], None]], str | None],
        prefetch_snapshot: Callable[[Callable[[dict], None]], None],
        initial_baseline_name: str | None = None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._caps = caps
        self._prefetch_snapshot = prefetch_snapshot
        self.presets_card: PresetsCard | None = None

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        content_box.set_margin_top(24)
        content_box.set_margin_bottom(24)
        content_box.set_margin_start(12)
        content_box.set_margin_end(12)

        content_box.append(self._build_header_group(caps))

        # DPI/lighting writes can change whether the current state still
        # matches the "active" local preset, so the Presets card needs to
        # know about them - see _perform_write_and_refresh_presets below.
        tracked_write_async = self._perform_write_and_refresh_presets(perform_write_async)

        self.dpi_card = DpiCard(caps, tracked_write_async, snapshot)
        self.dpi_card.connect("write-failed", lambda _c, msg: self.emit("write-failed", msg))
        self.dpi_card.connect("stage-editor-requested", lambda _c: self.emit("stage-editor-requested"))
        content_box.append(self.dpi_card)

        lighting_card = LightingCard(caps, tracked_write_async, open_color_picker, snapshot)
        lighting_card.connect("write-failed", lambda _c, msg: self.emit("write-failed", msg))
        content_box.append(lighting_card)

        battery_card = BatteryCard(caps, perform_write_async, snapshot)
        battery_card.connect("write-failed", lambda _c, msg: self.emit("write-failed", msg))
        content_box.append(battery_card)
        self.battery_card = battery_card

        presets_card = PresetsCard(caps, perform_write_sync, snapshot, initial_baseline_name)
        presets_card.connect("write-failed", lambda _c, msg: self.emit("write-failed", msg))
        presets_card.connect("preset-applied", lambda *_a: self.emit("reload-requested"))
        presets_card.connect("baseline-changed", lambda _c, name: self.emit("baseline-changed", name))
        presets_card.connect("dirty-detected", lambda _c, name: self.emit("dirty-detected", name))
        content_box.append(presets_card)
        self.presets_card = presets_card

        clamp = Adw.Clamp(maximum_size=CONTENT_MAX_WIDTH, tightening_threshold=800)
        clamp.set_child(content_box)

        scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_child(clamp)

        self.append(scroller)

    @property
    def baseline_name(self) -> str | None:
        return self.presets_card.baseline_name if self.presets_card is not None else None

    def _perform_write_and_refresh_presets(
        self, perform_write_async: Callable[[Callable[[], None], Callable[[str | None], None]], None]
    ) -> Callable[[Callable[[], None], Callable[[str | None], None]], None]:
        def tracked(fn: Callable[[], None], on_done: Callable[[str | None], None]) -> None:
            def wrapped_on_done(error: str | None) -> None:
                on_done(error)
                if error is None:
                    self._prefetch_snapshot(self._on_presets_snapshot_ready)

            perform_write_async(fn, wrapped_on_done)

        return tracked

    def _on_presets_snapshot_ready(self, snapshot: dict) -> None:
        if self.presets_card is not None:
            self.presets_card.update_snapshot(snapshot)

    def _build_header_group(self, caps: DeviceCapabilities) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        device = caps.device
        serial = device.serial

        image_box = Gtk.Box()
        image_box.set_size_request(84, 84)
        image_box.set_halign(Gtk.Align.CENTER)
        # border-radius alone doesn't clip children in GTK4.
        image_box.set_overflow(Gtk.Overflow.HIDDEN)

        def refresh_image() -> None:
            child = image_box.get_first_child()
            while child is not None:
                nxt = child.get_next_sibling()
                image_box.remove(child)
                child = nxt

            custom_path = device_images.get_custom_image(serial)
            if custom_path is not None:
                image_box.remove_css_class("dpi-image-placeholder")
                image_box.add_css_class("device-image-filled")
                picture = Gtk.Picture.new_for_filename(str(custom_path))
                picture.set_content_fit(Gtk.ContentFit.COVER)
                picture.set_hexpand(True)
                picture.set_vexpand(True)
                image_box.append(picture)
            else:
                image_box.remove_css_class("device-image-filled")
                image_box.add_css_class("dpi-image-placeholder")
                icon = Gtk.Image.new_from_icon_name(_generic_icon_name(device))
                icon.set_pixel_size(36)
                icon.set_halign(Gtk.Align.CENTER)
                icon.set_valign(Gtk.Align.CENTER)
                icon.set_hexpand(True)
                icon.set_vexpand(True)
                image_box.append(icon)

        refresh_image()

        edit_button = Gtk.Button()
        edit_button.add_css_class("device-image-edit-button")
        edit_button.add_css_class("osd")
        edit_button.set_child(Gtk.Image.new_from_icon_name("document-edit-symbolic"))
        edit_button.set_halign(Gtk.Align.END)
        edit_button.set_valign(Gtk.Align.END)
        edit_button.set_tooltip_text(_("Alterar imagem"))
        edit_button.connect(
            "clicked", lambda button: self._open_image_menu(button, serial, refresh_image)
        )

        image_overlay = Gtk.Overlay()
        image_overlay.set_child(image_box)
        image_overlay.add_overlay(edit_button)
        image_overlay.set_halign(Gtk.Align.CENTER)

        self._name_label = Gtk.Label(label=device_names.display_name(device))
        self._name_label.add_css_class("title-2")

        rename_button = Gtk.Button(icon_name="document-edit-symbolic")
        rename_button.add_css_class("flat")
        rename_button.set_valign(Gtk.Align.CENTER)
        rename_button.set_tooltip_text(_("Renomear dispositivo"))
        rename_button.connect("clicked", lambda *_a: self._open_rename_dialog(serial, device.name))

        name_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        name_row.set_halign(Gtk.Align.CENTER)
        name_row.append(self._name_label)
        name_row.append(rename_button)

        status_label = Gtk.Label(label=_("Conectado"))
        status_label.add_css_class("dim-label")

        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        header_box.set_halign(Gtk.Align.CENTER)
        header_box.set_hexpand(True)
        header_box.set_margin_top(20)
        header_box.set_margin_bottom(20)
        header_box.set_margin_start(12)
        header_box.set_margin_end(12)
        header_box.append(image_overlay)
        header_box.append(name_row)
        header_box.append(status_label)

        row = Adw.PreferencesRow(activatable=False)
        row.set_child(header_box)
        group.add(row)
        return group

    def _open_rename_dialog(self, serial: str, original_name: str) -> None:
        dialog = Adw.AlertDialog(
            heading=_("Renomear dispositivo"),
            body=_("Só muda o nome mostrado no app - o dispositivo em si não é alterado."),
        )
        entry = Gtk.Entry(text=device_names.display_name(self._caps.device))
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", _("Cancelar"))
        if device_names.get_custom_name(serial) is not None:
            dialog.add_response("reset", _("Restaurar nome original"))
        dialog.add_response("save", _("Salvar"))
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")

        def on_response(_dialog, response: str) -> None:
            if response == "save":
                name = entry.get_text().strip()
                if name and name != original_name:
                    device_names.set_custom_name(serial, name)
                else:
                    device_names.remove_custom_name(serial)
                self._name_label.set_label(device_names.display_name(self._caps.device))
                self.emit("name-changed")
            elif response == "reset":
                device_names.remove_custom_name(serial)
                self._name_label.set_label(original_name)
                self.emit("name-changed")

        dialog.connect("response", on_response)
        dialog.present(self.get_root())

    def _open_image_menu(self, button: Gtk.Button, serial: str, refresh_image: Callable[[], None]) -> None:
        popover = Gtk.Popover()
        popover.set_parent(button)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.set_margin_start(4)
        box.set_margin_end(4)

        choose_row = Gtk.Button(label=_("Escolher imagem…"))
        choose_row.add_css_class("flat")
        choose_row.connect(
            "clicked", lambda *_a: (popover.popdown(), self._choose_image(button, serial, refresh_image))
        )
        box.append(choose_row)

        if device_images.get_custom_image(serial) is not None:
            remove_row = Gtk.Button(label=_("Remover imagem"))
            remove_row.add_css_class("flat")
            remove_row.add_css_class("destructive-action")

            def on_remove(*_args) -> None:
                popover.popdown()
                device_images.remove_custom_image(serial)
                refresh_image()

            remove_row.connect("clicked", on_remove)
            box.append(remove_row)

        popover.set_child(box)
        popover.popup()

    def _choose_image(self, button: Gtk.Button, serial: str, refresh_image: Callable[[], None]) -> None:
        dialog = Gtk.FileDialog(title=_("Escolher imagem"))

        image_filter = Gtk.FileFilter()
        image_filter.set_name(_("Imagens"))
        image_filter.add_pixbuf_formats()
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(image_filter)
        dialog.set_filters(filters)

        def on_chosen(source: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
            try:
                gfile = source.open_finish(result)
            except GLib.Error:
                return
            if gfile is None:
                return
            path = gfile.get_path()
            if not path:
                return
            device_images.set_custom_image(serial, Path(path))
            refresh_image()

        dialog.open(button.get_root(), None, on_chosen)
