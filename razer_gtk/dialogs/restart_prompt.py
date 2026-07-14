"""Reusable 'restart needed' prompt - for any setting that only takes effect on next launch."""

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from razer_gtk.i18n import _


def prompt_restart(
    parent: Gtk.Widget,
    on_restart: Callable[[], None],
    heading: str | None = None,
    body: str | None = None,
) -> None:
    dialog = Adw.AlertDialog(
        heading=heading or _("Reiniciar o aplicativo?"),
        body=body or _("Essa alteração só terá efeito depois de reiniciar o OpenRazerGTK."),
    )
    dialog.add_response("later", _("Depois"))
    dialog.add_response("restart", _("Reiniciar agora"))
    dialog.set_response_appearance("restart", Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response("restart")
    dialog.set_close_response("later")

    def on_response(_dialog: Adw.AlertDialog, response: str) -> None:
        if response == "restart":
            on_restart()

    dialog.connect("response", on_response)
    dialog.present(parent)
