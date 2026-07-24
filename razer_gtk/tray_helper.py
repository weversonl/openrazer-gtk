"""Standalone GTK3 process for the tray/status icon.

AyatanaAppIndicator3 only accepts a GTK3 Gtk.Menu, and a process can't load
both Gtk 3.0 and 4.0 - so this runs separately and talks back to the main
app over D-Bus (org.freedesktop.Application / org.gtk.Actions).
"""

import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import Gio, GLib, Gtk, AyatanaAppIndicator3

from razer_gtk.i18n import _
from razer_gtk.i18n import install as install_i18n

ICON_NAME = "org.gnome.Settings-mouse-symbolic"


def _object_path(app_id: str) -> str:
    return "/" + app_id.replace(".", "/")


def _activate_app(app_id: str) -> None:
    proxy = Gio.DBusProxy.new_for_bus_sync(
        Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None,
        app_id, _object_path(app_id), "org.freedesktop.Application", None,
    )
    proxy.call_sync("Activate", GLib.Variant("(a{sv})", ({},)), Gio.DBusCallFlags.NONE, -1, None)


def _quit_app(app_id: str) -> None:
    proxy = Gio.DBusProxy.new_for_bus_sync(
        Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None,
        app_id, _object_path(app_id), "org.gtk.Actions", None,
    )
    proxy.call_sync(
        "Activate", GLib.Variant("(sava{sv})", ("quit", [], {})), Gio.DBusCallFlags.NONE, -1, None,
    )


def main() -> None:
    app_id = sys.argv[1] if len(sys.argv) > 1 else "io.github.weversonl.OpenRazerGTK"
    install_i18n()

    menu = Gtk.Menu()

    open_item = Gtk.MenuItem(label=_("Abrir"))
    open_item.connect("activate", lambda *_a: _activate_app(app_id))
    menu.append(open_item)

    menu.append(Gtk.SeparatorMenuItem())

    quit_item = Gtk.MenuItem(label=_("Sair"))
    quit_item.connect("activate", lambda *_a: _quit_app(app_id))
    menu.append(quit_item)

    menu.show_all()

    indicator = AyatanaAppIndicator3.Indicator.new(
        app_id, ICON_NAME, AyatanaAppIndicator3.IndicatorCategory.HARDWARE,
    )
    indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
    indicator.set_title("OpenRazerGTK")
    indicator.set_menu(menu)

    Gtk.main()


if __name__ == "__main__":
    main()
