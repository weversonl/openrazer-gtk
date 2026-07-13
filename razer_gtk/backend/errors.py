"""Human-readable messages for daemon/device errors, shown in toasts by the UI."""

import dbus
from openrazer.client.device_manager import DaemonNotFound

from razer_gtk.i18n import _


def describe_write_error(exc: Exception) -> str:
    """Turn a caught exception from a device write into a localized UI-facing message."""
    if isinstance(exc, DaemonNotFound):
        return _("Daemon do OpenRazer indisponível")
    if isinstance(exc, dbus.DBusException):
        return _("Falha ao comunicar com o dispositivo")
    if isinstance(exc, (ValueError, NotImplementedError)):
        return _("Valor inválido para este dispositivo")
    return _("Erro inesperado")
