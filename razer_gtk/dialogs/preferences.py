"""Preferences dialog: Geral (tema/idioma/...) + Backend (status do daemon)."""

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from razer_gtk.backend import autostart as autostart_backend
from razer_gtk.backend import settings as settings_backend
from razer_gtk.backend.manager import AppDeviceManager
from razer_gtk.i18n import _
from razer_gtk.widgets.pill_row import PillRow
from razer_gtk.widgets.pill_selector import PillSelector

_COLOR_SCHEMES = {
    "default": Adw.ColorScheme.DEFAULT,
    "light": Adw.ColorScheme.FORCE_LIGHT,
    "dark": Adw.ColorScheme.FORCE_DARK,
}


def _theme_options() -> list[tuple[str, str]]:
    return [("default", _("Sistema")), ("light", _("Claro")), ("dark", _("Escuro"))]


def _lang_options() -> list[tuple[str, str]]:
    return [("pt_BR", "Português (Brasil)"), ("en_US", "English (US)")]


def open_preferences(parent: Gtk.Widget, manager: AppDeviceManager, on_reset_window: Callable[[], None]) -> None:
    dialog = Adw.PreferencesDialog(content_width=560)
    page = Adw.PreferencesPage()
    dialog.add(page)

    settings = settings_backend.load_settings()

    general_group = Adw.PreferencesGroup(title=_("Geral"))
    page.add(general_group)

    theme_pills = PillSelector(_theme_options(), selected=settings.theme, max_width=280)

    def on_theme_selected(_pills: PillSelector, value: str) -> None:
        settings.theme = value
        settings_backend.save_settings(settings)
        Adw.StyleManager.get_default().set_color_scheme(_COLOR_SCHEMES.get(value, Adw.ColorScheme.DEFAULT))

    theme_pills.connect("selection-changed", on_theme_selected)
    theme_row = Adw.PreferencesRow(activatable=False)
    theme_row.set_child(PillRow(_("Tema"), theme_pills))
    general_group.add(theme_row)

    lang_pills = PillSelector(_lang_options(), selected=settings.lang, max_width=310)

    def on_lang_selected(_pills: PillSelector, value: str) -> None:
        settings.lang = value
        settings_backend.save_settings(settings)

    lang_pills.connect("selection-changed", on_lang_selected)
    lang_row = Adw.PreferencesRow(activatable=False)
    lang_row.set_child(PillRow(_("Idioma"), lang_pills, subtitle=_("Aplicado ao reiniciar o app")))
    general_group.add(lang_row)

    autostart_row = Adw.SwitchRow(
        title=_("Iniciar automaticamente"),
        subtitle=_("Abre minimizado na bandeja ao ligar o sistema"),
        active=autostart_backend.is_enabled(),
    )

    def on_autostart_toggled(row: Adw.SwitchRow, _pspec) -> None:
        autostart_backend.set_enabled(row.get_active())

    autostart_row.connect("notify::active", on_autostart_toggled)
    general_group.add(autostart_row)

    reset_window_row = Adw.ActionRow(title=_("Tamanho da janela"))
    reset_window_button = Gtk.Button(label=_("Redefinir"))
    reset_window_button.set_valign(Gtk.Align.CENTER)
    reset_window_button.connect("clicked", lambda *_args: on_reset_window())
    reset_window_row.add_suffix(reset_window_button)
    general_group.add(reset_window_row)

    backend_group = Adw.PreferencesGroup(title=_("Backend"))
    page.add(backend_group)

    status_row = Adw.ActionRow(title=_("Status do OpenRazer"))
    status_badge = Gtk.Label()
    status_badge.add_css_class("caption")
    status_row.add_suffix(status_badge)
    backend_group.add(status_row)

    version_row = Adw.ActionRow(title=_("Versão do daemon"))
    backend_group.add(version_row)

    def refresh_backend_status() -> None:
        if manager.daemon_available:
            status_badge.set_label(_("Conectado"))
            status_badge.add_css_class("success")
            status_badge.remove_css_class("error")
            version_row.set_subtitle(manager.daemon_version or "-")
        else:
            status_badge.set_label(_("Indisponível"))
            status_badge.add_css_class("error")
            status_badge.remove_css_class("success")
            version_row.set_subtitle("-")

    refresh_backend_status()
    signal_id = manager.connect("backend-status-changed", lambda *_args: refresh_backend_status())

    def on_closed(_dialog: Adw.PreferencesDialog) -> None:
        manager.disconnect(signal_id)

    dialog.connect("closed", on_closed)
    dialog.present(parent)
