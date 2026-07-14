"""Overview 'Presets' card - local, app-only snapshots (not on-board hardware profiles)."""

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GObject, Gtk

from razer_gtk.backend import presets as presets_backend
from razer_gtk.backend.device_adapter import DeviceCapabilities
from razer_gtk.i18n import _


class PresetsCard(Adw.PreferencesGroup):
    __gsignals__ = {
        "write-failed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "preset-applied": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "baseline-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "dirty-detected": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(
        self,
        caps: DeviceCapabilities,
        perform_write: Callable[[Callable[[], None]], str | None],
        snapshot: dict,
        initial_baseline_name: str | None = None,
    ) -> None:
        super().__init__(
            title=_("Presets"),
            description=_("Combinações salvas localmente neste app - não são perfis de hardware"),
        )
        self._caps = caps
        self._perform_write = perform_write
        self._serial = str(caps.device.serial)
        self._presets = presets_backend.load_presets(self._serial)
        self._snapshot = snapshot

        # The preset the device matched when this screen was built (or last
        # time it was made to match again, via apply/undo/save). While the
        # live snapshot still matches it, it shows the "Ativo" badge; once
        # the user changes something elsewhere and it stops matching, this
        # is the preset that gets the save/undo icons instead.
        #
        # A full screen reload (e.g. after editing DPI stages in the
        # dedicated dialog, which doesn't go through this card at all) loses
        # any in-memory baseline, so the caller passes back whatever name
        # was baseline before the reload - if there's no exact match here
        # either, that remembered preset becomes the dirty baseline instead
        # of silently forgetting the divergence.
        exact_match = next(
            (p for p in self._presets if presets_backend.is_preset_active(caps, p, snapshot)), None
        )
        if exact_match is not None:
            self._baseline_preset: presets_backend.Preset | None = exact_match
        elif initial_baseline_name is not None:
            self._baseline_preset = next(
                (p for p in self._presets if p.name == initial_baseline_name), None
            )
        else:
            self._baseline_preset = None

        self._listbox = Gtk.ListBox()
        self._listbox.add_css_class("boxed-list")
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)

        row = Adw.PreferencesRow(activatable=False)
        row.set_child(self._listbox)
        self.add(row)

        self._known_dirty = self._is_dirty()
        self._rebuild_list()

    @property
    def baseline_name(self) -> str | None:
        return self._baseline_preset.name if self._baseline_preset is not None else None

    @property
    def is_dirty(self) -> bool:
        return self._known_dirty

    def _set_baseline(self, preset: presets_backend.Preset | None) -> None:
        self._baseline_preset = preset
        self._known_dirty = self._is_dirty()
        self.emit("baseline-changed", preset.name if preset is not None else "")

    def save_baseline(self) -> None:
        """Save the current (diverged) device state into the baseline
        preset - what the toast's "Salvar" action triggers."""
        if self._baseline_preset is not None:
            self._on_save_clicked(None, self._baseline_preset)

    def update_snapshot(self, snapshot: dict) -> None:
        """Called from outside whenever a write elsewhere (DPI, lighting)
        succeeds, so the baseline preset's active/dirty state stays live."""
        if not snapshot:
            return
        self._snapshot = snapshot
        was_dirty = self._known_dirty
        self._known_dirty = self._is_dirty()
        self._rebuild_list()
        if self._known_dirty and not was_dirty and self._baseline_preset is not None:
            self.emit("dirty-detected", self._baseline_preset.name)

    def _is_dirty(self) -> bool:
        if self._baseline_preset is None:
            return False
        return not presets_backend.is_preset_active(self._caps, self._baseline_preset, self._snapshot)

    def _rebuild_list(self) -> None:
        child = self._listbox.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._listbox.remove(child)
            child = nxt

        dirty = self._is_dirty()

        for preset in self._presets:
            row = Adw.ActionRow(title=preset.name)
            is_baseline = self._baseline_preset is not None and preset.name == self._baseline_preset.name

            if is_baseline and dirty:
                save_button = Gtk.Button(icon_name="document-save-symbolic")
                save_button.set_valign(Gtk.Align.CENTER)
                save_button.add_css_class("flat")
                save_button.set_tooltip_text(_("Salvar alterações no preset"))
                save_button.connect("clicked", self._on_save_clicked, preset)
                row.add_suffix(save_button)

                undo_button = Gtk.Button(icon_name="edit-undo-symbolic")
                undo_button.set_valign(Gtk.Align.CENTER)
                undo_button.add_css_class("flat")
                undo_button.set_tooltip_text(_("Desfazer alterações"))
                undo_button.connect("clicked", self._on_undo_clicked, preset)
                row.add_suffix(undo_button)
            elif is_baseline:
                badge = Gtk.Label(label=_("Ativo"))
                badge.add_css_class("preset-active-badge")
                badge.set_valign(Gtk.Align.CENTER)
                row.add_suffix(badge)
            else:
                apply_button = Gtk.Button(icon_name="media-playback-start-symbolic")
                apply_button.set_valign(Gtk.Align.CENTER)
                apply_button.add_css_class("flat")
                apply_button.set_tooltip_text(_("Aplicar"))
                apply_button.connect("clicked", self._on_apply_clicked, preset)
                row.add_suffix(apply_button)

            delete_button = Gtk.Button(icon_name="user-trash-symbolic")
            delete_button.set_valign(Gtk.Align.CENTER)
            delete_button.add_css_class("flat")
            delete_button.set_tooltip_text(_("Excluir"))
            delete_button.connect("clicked", self._on_delete_clicked, preset)
            row.add_suffix(delete_button)

            self._listbox.append(row)

        add_row = Adw.ActionRow(title=_("Novo preset"), activatable=True)
        add_row.add_prefix(Gtk.Image.new_from_icon_name("list-add-symbolic"))
        add_row.connect("activated", self._on_add_preset)
        self._listbox.append(add_row)

    def _on_add_preset(self, _row: Adw.ActionRow) -> None:
        dialog = Adw.AlertDialog(
            heading=_("Novo preset"),
            body=_("Salva DPI, taxa de atualização e iluminação atuais deste dispositivo."),
        )
        entry = Gtk.Entry(placeholder_text=_("Nome do preset"))
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", _("Cancelar"))
        dialog.add_response("save", _("Salvar"))
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")

        def on_response(_dialog, response: str) -> None:
            if response != "save":
                return
            name = entry.get_text().strip() or _("Preset sem nome")
            preset = presets_backend.capture_preset(self._caps, name)
            self._presets.append(preset)
            presets_backend.save_presets(self._serial, self._presets)
            self._set_baseline(preset)
            self._rebuild_list()

        dialog.connect("response", on_response)
        root = self.get_root()
        dialog.present(root)

    def _on_apply_clicked(self, _button: Gtk.Button, preset) -> None:
        errors = presets_backend.apply_preset(self._caps, preset, self._perform_write)
        for error in errors:
            self.emit("write-failed", error)
        if not errors:
            self._set_baseline(preset)
            self._rebuild_list()
            self.emit("preset-applied")

    def _on_save_clicked(self, _button: Gtk.Button, preset) -> None:
        """Overwrite `preset` with the device's current (diverged) state."""
        updated = presets_backend.capture_preset(self._caps, preset.name)
        self._presets = [updated if p is preset else p for p in self._presets]
        presets_backend.save_presets(self._serial, self._presets)
        self._set_baseline(updated)
        self._rebuild_list()

    def _on_undo_clicked(self, _button: Gtk.Button, preset) -> None:
        """Revert the device back to `preset`'s stored values."""
        errors = presets_backend.apply_preset(self._caps, preset, self._perform_write)
        for error in errors:
            self.emit("write-failed", error)
        if not errors:
            self._set_baseline(preset)
            self._rebuild_list()
            self.emit("preset-applied")

    def _on_delete_clicked(self, _button: Gtk.Button, preset) -> None:
        self._presets = [p for p in self._presets if p is not preset]
        presets_backend.save_presets(self._serial, self._presets)
        if self._baseline_preset is not None and self._baseline_preset.name == preset.name:
            self._set_baseline(None)
        self._rebuild_list()
