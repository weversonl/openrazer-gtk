"""Main application window: sidebar + content pane + toasts."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk

from razer_gtk.backend import settings as settings_backend
from razer_gtk.backend.manager import AppDeviceManager
from razer_gtk.dialogs.color_picker import open_color_picker
from razer_gtk.dialogs.dpi_stage_editor import open_dpi_stage_editor
from razer_gtk.dialogs.preferences import open_preferences
from razer_gtk.i18n import _
from razer_gtk.widgets.device_overview import DeviceOverview
from razer_gtk.widgets.device_sidebar import DeviceSidebar

DEFAULT_WIDTH = 1360
DEFAULT_HEIGHT = 895

# Fallback default (used above) is a good fit on ~QHD/27". On smaller monitors
# it can dwarf the screen, so on first run (no saved user size yet) we instead
# derive the default from a percentage of the primary monitor's own work area.
MONITOR_WIDTH_FRACTION = 0.65
MONITOR_HEIGHT_FRACTION = 0.75
MIN_WIDTH = 1030  # boxed-list pill rows stop shrinking below this - see docs/pendente.md
MIN_HEIGHT = 600


def _default_size_for_monitor() -> tuple[int, int]:
    display = Gdk.Display.get_default()
    if display is None:
        return DEFAULT_WIDTH, DEFAULT_HEIGHT
    monitors = display.get_monitors()
    if monitors.get_n_items() == 0:
        return DEFAULT_WIDTH, DEFAULT_HEIGHT
    geometry = monitors.get_item(0).get_geometry()
    width = max(MIN_WIDTH, min(DEFAULT_WIDTH, round(geometry.width * MONITOR_WIDTH_FRACTION)))
    height = max(MIN_HEIGHT, min(DEFAULT_HEIGHT, round(geometry.height * MONITOR_HEIGHT_FRACTION)))
    return width, height


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, application: Adw.Application, manager: AppDeviceManager) -> None:
        settings = settings_backend.load_settings()
        if settings.window_width and settings.window_height:
            width, height = settings.window_width, settings.window_height
        else:
            width, height = _default_size_for_monitor()
        super().__init__(application=application, title="OpenRazerGTK", default_width=width, default_height=height)
        self._manager = manager
        self._current_serial: str | None = None
        self._overview: DeviceOverview | None = None
        # Which local preset each device's Presets card was last treating as
        # its baseline (for the save/undo dirty-state icons) - carried across
        # full-screen reloads, since those reconstruct the Presets card from
        # scratch (e.g. after editing DPI stages in the separate dialog,
        # which never touches the Presets card directly).
        self._active_preset_names: dict[str, str | None] = {}

        self._toast_overlay = Adw.ToastOverlay()

        self._split_view = Adw.NavigationSplitView(min_sidebar_width=250, max_sidebar_width=300)

        self._sidebar = DeviceSidebar(manager)
        self._sidebar.connect("device-selected", self._on_device_selected)
        self._sidebar.connect(
            "preferences-requested", lambda *_args: open_preferences(self, manager, self.reset_window_size)
        )
        self._sidebar.connect("refresh-requested", lambda *_args: self._on_refresh_requested())
        self._split_view.set_sidebar(self._sidebar)

        self._content_header = Adw.HeaderBar()

        content_toolbar = Adw.ToolbarView()
        content_toolbar.add_top_bar(self._content_header)

        self._content_stack = Gtk.Stack()
        content_toolbar.set_content(self._content_stack)

        self._empty_content = Adw.StatusPage(
            title=_("Selecione um dispositivo"),
            icon_name="input-mouse-symbolic",
        )
        self._content_stack.add_named(self._empty_content, "empty")

        self._loading_content = Adw.StatusPage(
            title=_("Procurando dispositivos..."),
            icon_name="content-loading-symbolic",
        )
        self._content_stack.add_named(self._loading_content, "loading")
        if manager.scanning:
            self._content_stack.set_visible_child_name("loading")

        self._content_page = Adw.NavigationPage(title="OpenRazerGTK", child=content_toolbar)
        self._split_view.set_content(self._content_page)

        self._toast_overlay.set_child(self._split_view)
        self.set_content(self._toast_overlay)

        manager.connect("devices-changed", self._on_devices_changed)
        manager.connect("scanning-changed", self._on_scanning_changed)
        manager.connect("device-state-changed", self._on_device_state_changed)
        manager.start_polling()

        if manager.devices:
            first_serial = manager.devices[0].device.serial
            self._on_device_selected(self._sidebar, first_serial)

    def _on_refresh_requested(self) -> None:
        """Manual re-scan (button in the sidebar), instead of waiting for
        the next 5s poll tick - also re-reads the currently open device's
        full snapshot so its cards pick up anything the poll doesn't cover."""
        self._manager.rescan_async()
        if self._current_serial is not None:
            self._request_rebuild(self._current_serial)

    def _on_device_state_changed(self, manager: AppDeviceManager, serial: str) -> None:
        """The 5s poll re-read battery level/charging for `serial` - push it
        into the visible card if that's the currently open device (the
        sidebar already listens to this same signal for its own row)."""
        if serial != self._current_serial or self._overview is None:
            return
        state = manager.get_volatile_state(serial)
        if state is not None:
            level, charging = state
            self._overview.battery_card.update_level(level, charging)

    def _on_scanning_changed(self, _manager: AppDeviceManager, scanning: bool) -> None:
        if scanning and not self._manager.devices:
            self._loading_content.set_title(_("Procurando dispositivos..."))
            self._content_stack.set_visible_child_name("loading")

    def _on_devices_changed(self, _manager: AppDeviceManager) -> None:
        available_serials = {str(caps.device.serial) for caps in self._manager.devices}

        if not available_serials:
            self._current_serial = None
            self._manager.select_device(None)
            self._content_stack.set_visible_child_name("empty")
            return

        if self._current_serial not in available_serials:
            first_serial = self._manager.devices[0].device.serial
            self._current_serial = None
            self._on_device_selected(self._sidebar, first_serial)

    def _on_device_selected(self, _sidebar: DeviceSidebar, serial: str) -> None:
        if serial == self._current_serial:
            return
        self._current_serial = serial
        self._manager.select_device(serial)
        self._request_rebuild(serial)

    def _request_rebuild(self, serial: str) -> None:
        """Prefetch this device's current values, then build widgets from that snapshot."""
        caps = self._manager.get_capabilities(serial)
        if caps is None:
            self._content_stack.set_visible_child_name("empty")
            return

        self._content_stack.set_visible_child_name("loading")
        self._loading_content.set_title(_("Carregando {device}...").format(device=caps.device.name))

        def on_snapshot_ready(snapshot: dict) -> None:
            if serial != self._current_serial:
                return
            self._rebuild_content(serial, snapshot)

        self._manager.prefetch_snapshot_async(serial, on_snapshot_ready)

    def _rebuild_content(self, serial: str, snapshot: dict) -> None:
        caps = self._manager.get_capabilities(serial)
        if caps is None:
            self._content_stack.set_visible_child_name("empty")
            return

        existing = self._content_stack.get_child_by_name("overview")
        if existing is not None:
            self._content_stack.remove(existing)

        def open_picker(current_hex: str, on_chosen) -> None:
            open_color_picker(self, current_hex, on_chosen)

        self._overview = DeviceOverview(
            caps,
            self._manager.perform_write_async,
            open_picker,
            snapshot,
            self._manager.perform_write,
            lambda on_ready: self._manager.prefetch_snapshot_async(serial, on_ready),
            self._active_preset_names.get(serial),
        )
        self._overview.connect("write-failed", self._on_write_failed)
        self._overview.connect("stage-editor-requested", lambda *_args: self._open_stage_editor(caps))
        self._overview.connect("reload-requested", lambda *_args: self._on_preset_reload_requested())
        self._overview.connect(
            "baseline-changed", lambda _w, name, serial=serial: self._active_preset_names.__setitem__(serial, name or None)
        )
        self._overview.connect("dirty-detected", lambda _w, name: self._show_preset_dirty_toast(name))
        self._content_stack.add_named(self._overview, "overview")
        self._content_stack.set_visible_child_name("overview")
        # Seed from whatever baseline the freshly-built Presets card settled
        # on (exact match, or the carried-over name above) - future changes
        # arrive via the signal just connected, but this initial value
        # predates that connection.
        self._active_preset_names[serial] = self._overview.baseline_name
        # A DPI-stage edit (or preset apply/undo) rebuilds this screen from
        # scratch, bypassing the live "dirty-detected" signal above (nothing
        # transitions - the new Presets card is just born dirty). Catch that
        # case here instead.
        if self._overview.presets_card is not None and self._overview.presets_card.is_dirty:
            self._show_preset_dirty_toast(self._overview.baseline_name)

        self._content_header.set_title_widget(Adw.WindowTitle(title=caps.device.name))

    def _open_stage_editor(self, caps) -> None:
        def on_saved() -> None:
            self._show_toast(_("Estágios de DPI salvos"))
            if self._current_serial is not None:
                self._request_rebuild(self._current_serial)

        open_dpi_stage_editor(
            self, caps, self._manager.perform_write, on_saved=on_saved, on_error=self._show_toast
        )

    def _on_preset_reload_requested(self) -> None:
        """After applying/undoing a preset, rebuild the overview so every
        card (DPI pills, effect pills, etc.) reflects the reverted state -
        not just the Presets card itself."""
        if self._current_serial is not None:
            self._request_rebuild(self._current_serial)

    def _on_write_failed(self, _widget, message: str) -> None:
        self._show_toast(message)

    def _show_toast(self, message: str) -> None:
        self._toast_overlay.add_toast(Adw.Toast(title=message, timeout=3))

    def _show_preset_dirty_toast(self, preset_name: str | None) -> None:
        if not preset_name:
            return
        toast = Adw.Toast(
            title=_('As configurações não batem mais com o preset "{name}"').format(name=preset_name),
            button_label=_("Salvar"),
            timeout=0,
        )
        toast.connect("button-clicked", lambda *_a: self._on_save_dirty_preset())
        self._toast_overlay.add_toast(toast)

    def _on_save_dirty_preset(self) -> None:
        if self._overview is not None and self._overview.presets_card is not None:
            self._overview.presets_card.save_baseline()

    def save_window_size(self) -> None:
        settings = settings_backend.load_settings()
        settings.window_width = self.get_width()
        settings.window_height = self.get_height()
        settings_backend.save_settings(settings)

    def reset_window_size(self) -> None:
        width, height = _default_size_for_monitor()
        self.set_default_size(width, height)
        settings = settings_backend.load_settings()
        settings.window_width = width
        settings.window_height = height
        settings_backend.save_settings(settings)
