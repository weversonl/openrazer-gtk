"""gettext setup for the app. Source strings are PT-BR; en_US catalog translates them."""

import gettext
from pathlib import Path

from razer_gtk.backend.settings import load_settings

DOMAIN = "razer-gtk"
LOCALE_DIR = Path(__file__).parent / "locale"

_translation: gettext.NullTranslations = gettext.NullTranslations()


def install(lang: str | None = None) -> None:
    """(Re)bind the active translation catalog. Call before building any UI."""
    global _translation
    if lang is None:
        lang = load_settings().lang
    try:
        _translation = gettext.translation(DOMAIN, localedir=str(LOCALE_DIR), languages=[lang])
    except FileNotFoundError:
        _translation = gettext.NullTranslations()


def _(message: str) -> str:
    """Not a `_ = gettext.gettext` alias - stays a function so it re-resolves through `install()`'s latest catalog."""
    return _translation.gettext(message)


def N_(message: str) -> str:
    """No-op marker so `xgettext --keyword=N_` can statically extract strings translated later via `_()`."""
    return message
