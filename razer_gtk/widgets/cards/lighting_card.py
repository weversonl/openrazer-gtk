"""Overview 'Iluminação' card - wraps EffectControlsGroup around the device's primary_light."""

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GObject

from razer_gtk.backend.device_adapter import DeviceCapabilities
from razer_gtk.i18n import _
from razer_gtk.widgets.effect_controls import EffectControlsGroup

QUICK_PALETTE = [
    "ff0000", "00ff00", "0000ff", "ffff00", "00ffff", "ff00ff", "ff8000", "8000ff", "ffffff",
]


class LightingCard(Adw.PreferencesGroup):
    __gsignals__ = {
        "write-failed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(
        self,
        caps: DeviceCapabilities,
        perform_write_async: Callable[[Callable[[], None], Callable[[str | None], None]], None],
        open_color_picker: Callable[[str, Callable[[str], None]], None],
        snapshot: dict,
    ) -> None:
        super().__init__(title=_("Iluminação"), description=_("Efeito, cor e brilho da luz principal do dispositivo"))
        zone = caps.primary_light
        if zone is None:
            self.set_visible(False)
            return

        controls = EffectControlsGroup(zone, caps.device, perform_write_async, QUICK_PALETTE, open_color_picker, snapshot)
        controls.connect("write-failed", lambda _w, msg: self.emit("write-failed", msg))

        row = Adw.PreferencesRow(activatable=False)
        row.set_child(controls)
        self.add(row)
