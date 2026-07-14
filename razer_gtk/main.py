"""Adw.Application entrypoint."""

import os
import subprocess
import sys
from pathlib import Path

# Must run before any dbus.SessionBus()/openrazer call in the app, else
# D-Bus I/O isn't pumped by GLib's main loop and blocks the GTK thread.
from dbus.mainloop.glib import DBusGMainLoop, threads_init

DBusGMainLoop(set_as_default=True)
threads_init()

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, Gio, Gtk

from razer_gtk.backend import settings as settings_backend
from razer_gtk.backend.autostart import HIDDEN_START_ENV
from razer_gtk.backend.manager import AppDeviceManager
from razer_gtk.i18n import install as install_i18n
from razer_gtk.window import MainWindow

APP_ID = "io.github.weversonl.OpenRazerGTK"
STYLE_PATH = Path(__file__).parent / "resources" / "style.css"
ICON_THEME_DIR = Path(__file__).parent.parent / "data" / "icons"

_COLOR_SCHEMES = {
    "default": Adw.ColorScheme.DEFAULT,
    "light": Adw.ColorScheme.FORCE_LIGHT,
    "dark": Adw.ColorScheme.FORCE_DARK,
}

# Adw.StyleManager's accent-color is read-only, so we override the named
# colors Adwaita's own stylesheet defines instead (@define-color at
# APPLICATION priority beats the theme's).
_ACCENT_COLORS_LIGHT = {
    "accent_bg_color": "#26a269",
    "accent_color": "#2ec27e",
    "accent_fg_color": "#ffffff",
}
_ACCENT_COLORS_DARK = {
    "accent_bg_color": "#33d17a",
    "accent_color": "#33d17a",
    "accent_fg_color": "#ffffff",
}


class RazerGtkApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID)
        self._manager: AppDeviceManager | None = None
        self._window: MainWindow | None = None
        self._accent_provider: Gtk.CssProvider | None = None
        self._tray_process: subprocess.Popen | None = None
        self.connect("activate", self._on_activate)
        self.connect("shutdown", self._on_shutdown)

    def _on_activate(self, app: Adw.Application) -> None:
        window = self.props.active_window
        if window is not None:
            window.present()
            return

        self._load_style()
        self._load_icon_theme()
        install_i18n()

        settings = settings_backend.load_settings()
        style_manager = Adw.StyleManager.get_default()
        style_manager.set_color_scheme(_COLOR_SCHEMES.get(settings.theme, Adw.ColorScheme.DEFAULT))

        self._apply_accent_colors()
        style_manager.connect("notify::dark", lambda *_a: self._apply_accent_colors())

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_a: self.quit())
        self.add_action(quit_action)

        self._manager = AppDeviceManager()
        window = MainWindow(self, self._manager)
        window.set_icon_name(APP_ID)
        window.connect("close-request", self._on_window_close_request)
        self._window = window

        self._spawn_tray()

        if not os.environ.get(HIDDEN_START_ENV):
            window.present()

    def _on_window_close_request(self, window: Gtk.Window) -> bool:
        window.save_window_size()
        window.set_visible(False)
        return True

    def restart(self) -> None:
        """Re-exec the whole process in place, e.g. after a language change
        that only takes effect on next launch. Replaces this process image
        (same PID), so there's no window to leave open or mainloop to stop."""
        if self._window is not None:
            self._window.save_window_size()
        if self._tray_process is not None:
            self._tray_process.terminate()
            self._tray_process = None
        os.chdir(str(Path(__file__).parent.parent))
        os.execv(sys.executable, [sys.executable, "-m", "razer_gtk", *sys.argv[1:]])

    def _spawn_tray(self) -> None:
        if self._tray_process is not None:
            return
        # Must run as `-m razer_gtk.tray_helper`, not a bare script path,
        # so `import razer_gtk` resolves inside the subprocess.
        self._tray_process = subprocess.Popen(
            [sys.executable, "-m", "razer_gtk.tray_helper", APP_ID],
            cwd=str(Path(__file__).parent.parent),
        )

    def _on_shutdown(self, _app: Adw.Application) -> None:
        if self._window is not None:
            self._window.save_window_size()
        if self._tray_process is not None:
            self._tray_process.terminate()
            self._tray_process = None

    def _load_style(self) -> None:
        if not STYLE_PATH.exists():
            return
        provider = Gtk.CssProvider()
        provider.load_from_path(str(STYLE_PATH))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _load_icon_theme(self) -> None:
        # Not installed system-wide, so add the search path directly.
        if not ICON_THEME_DIR.exists():
            return
        icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        icon_theme.add_search_path(str(ICON_THEME_DIR))

    def _apply_accent_colors(self) -> None:
        is_dark = Adw.StyleManager.get_default().get_dark()
        colors = _ACCENT_COLORS_DARK if is_dark else _ACCENT_COLORS_LIGHT
        css = "\n".join(f"@define-color {name} {value};" for name, value in colors.items())

        if self._accent_provider is None:
            self._accent_provider = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                self._accent_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
        self._accent_provider.load_from_string(css)


def run() -> int:
    app = RazerGtkApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(run())
