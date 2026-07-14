"""Device list sidebar: DEVICES section, one row per connected device, pinned Preferences footer."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GObject, Gtk

from razer_gtk.backend import device_names
from razer_gtk.backend.device_icons import generic_icon_name
from razer_gtk.backend.manager import AppDeviceManager
from razer_gtk.i18n import _


class DeviceSidebar(Adw.NavigationPage):
    __gsignals__ = {
        "device-selected": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "preferences-requested": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "refresh-requested": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, manager: AppDeviceManager) -> None:
        super().__init__(title=_("Dispositivos"))
        self._manager = manager
        self._serials: list[str] = []
        self._selected_serial: str | None = None

        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar(show_end_title_buttons=False, show_start_title_buttons=False)
        refresh_button = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_button.set_tooltip_text(_("Procurar dispositivos novamente"))
        refresh_button.connect("clicked", lambda *_args: self.emit("refresh-requested"))
        header.pack_end(refresh_button)
        toolbar_view.add_top_bar(header)

        self._stack = Gtk.Stack()

        self._listbox = Gtk.ListBox()
        self._listbox.add_css_class("navigation-sidebar")
        self._listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._listbox.connect("row-selected", self._on_row_selected)

        section_label = Gtk.Label(label=_("DISPOSITIVOS"), xalign=0.0)
        section_label.add_css_class("caption-heading")
        section_label.add_css_class("dim-label")
        section_label.set_margin_start(16)
        section_label.set_margin_top(12)
        section_label.set_margin_bottom(4)

        list_scroller = Gtk.ScrolledWindow(vexpand=True)
        list_scroller.set_child(self._listbox)

        list_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        list_page.append(section_label)
        list_page.append(list_scroller)

        self._empty_status = Adw.StatusPage(
            title=_("Nenhum dispositivo Razer encontrado"),
            description=_("Conecte um mouse compatível com o OpenRazer para começar."),
            icon_name="input-mouse-symbolic",
            vexpand=True,
        )

        self._stack.add_named(list_page, "list")
        self._stack.add_named(self._empty_status, "empty")

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, vexpand=True)
        content_box.append(self._stack)
        content_box.append(Gtk.Separator())

        prefs_row = Adw.ActionRow(title=_("Preferências"), activatable=True)
        prefs_row.add_prefix(Gtk.Image.new_from_icon_name("emblem-system-symbolic"))
        prefs_row.connect("activated", lambda *_args: self.emit("preferences-requested"))
        prefs_box = Gtk.ListBox()
        prefs_box.add_css_class("navigation-sidebar")
        prefs_box.set_selection_mode(Gtk.SelectionMode.NONE)
        prefs_box.append(prefs_row)
        content_box.append(prefs_box)

        toolbar_view.set_content(content_box)
        self.set_child(toolbar_view)

        manager.connect("devices-changed", lambda *_args: self.rebuild())
        manager.connect("device-state-changed", lambda *_args_a: self.rebuild(keep_selection=True))
        self.rebuild()

    def rebuild(self, keep_selection: bool = False) -> None:
        devices = self._manager.devices

        if not devices:
            self._stack.set_visible_child_name("empty")
            self._serials = []
            return
        self._stack.set_visible_child_name("list")

        child = self._listbox.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._listbox.remove(child)
            child = nxt

        self._serials = [caps.device.serial for caps in devices]
        for caps in devices:
            row = self._build_row(caps)
            self._listbox.append(row)

        target_serial = self._selected_serial if keep_selection and self._selected_serial in self._serials else self._serials[0]
        index = self._serials.index(target_serial)
        self._listbox.select_row(self._listbox.get_row_at_index(index))

    def _build_row(self, caps) -> Adw.ActionRow:
        # No live D-Bus call here (e.g. device.battery_level) to detect
        # connectivity - this reruns on every poll tick, and daemon calls
        # can take 5+ seconds. Presence in manager.devices means connected.
        device = caps.device

        row = Adw.ActionRow(
            title=device_names.display_name(device),
            subtitle=_("Conectado"),
        )
        row.add_prefix(Gtk.Image.new_from_icon_name(generic_icon_name(device)))

        dot = Gtk.Box()
        dot.set_size_request(8, 8)
        dot.set_halign(Gtk.Align.CENTER)
        dot.set_valign(Gtk.Align.CENTER)
        dot.add_css_class("status-dot")
        dot.add_css_class("status-connected")
        row.add_suffix(dot)

        return row

    def _on_row_selected(self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        if row is None:
            return
        index = row.get_index()
        if 0 <= index < len(self._serials):
            self._selected_serial = self._serials[index]
            self.emit("device-selected", self._selected_serial)
