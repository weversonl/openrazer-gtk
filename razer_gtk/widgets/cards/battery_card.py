"""Overview 'Bateria e Energia' card - wireless-only, gated on caps.supports_battery."""

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, GObject, Gtk

from razer_gtk.backend.device_adapter import DeviceCapabilities
from razer_gtk.i18n import _

SETTINGS_DEBOUNCE_MS = 400


class BatteryCard(Adw.PreferencesGroup):
    __gsignals__ = {
        "write-failed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(
        self,
        caps: DeviceCapabilities,
        perform_write_async: Callable[[Callable[[], None], Callable[[str | None], None]], None],
        snapshot: dict,
    ) -> None:
        super().__init__(title=_("Bateria e Energia"), description=_("Nível de carga e economia de energia"))
        self._caps = caps
        self._device = caps.device
        self._perform_write_async = perform_write_async
        self._idle_timeout_id: int | None = None
        self._threshold_timeout_id: int | None = None

        if not caps.supports_battery:
            self.set_visible(False)
            return

        self._level_row = Adw.ActionRow(title=_("Bateria"), icon_name="battery-symbolic")
        self._level_row.set_title_lines(1)
        self._level_bar = Gtk.LevelBar()
        self._level_bar.set_min_value(0)
        self._level_bar.set_max_value(100)
        self._level_bar.set_size_request(140, -1)
        self._level_bar.set_valign(Gtk.Align.CENTER)
        self._charge_icon = Gtk.Image()
        self._charge_icon.set_valign(Gtk.Align.CENTER)
        self._percent_label = Gtk.Label()
        self._percent_label.add_css_class("numeric")

        level_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        level_box.append(self._level_bar)
        level_box.append(self._charge_icon)
        level_box.append(self._percent_label)
        self._level_row.add_suffix(level_box)
        self.add(self._level_row)
        self._apply_level(snapshot.get("battery_level", 0), snapshot.get("is_charging", False))

        if caps.supports_idle_time:
            idle_row = Adw.SpinRow.new_with_range(1, 15, 1)
            idle_row.set_title(_("Modo de dormir depois"))
            idle_row.set_icon_name("openrazer-gtk-battery-save-symbolic")
            idle_row.set_title_lines(1)
            idle_row.set_subtitle(_("Minutos de inatividade"))
            idle_row.set_value(round(snapshot.get("idle_time", 300) / 60))
            idle_row.connect("notify::value", self._on_idle_changed)
            self.add(idle_row)

        if caps.supports_low_battery_threshold:
            threshold_row = Adw.SpinRow.new_with_range(5, 50, 5)
            threshold_row.set_title(_("Entrar em baixa energia em"))
            threshold_row.set_icon_name("power-profile-power-saver-symbolic")
            threshold_row.set_title_lines(1)
            threshold_row.set_subtitle(_("Percentual de bateria"))
            threshold_row.set_value(snapshot.get("low_battery_threshold", 10))
            threshold_row.connect("notify::value", self._on_threshold_changed)
            self.add(threshold_row)

    def update_level(self, level: int, charging: bool) -> None:
        """Push a freshly-polled battery reading into the already-built
        card, so it doesn't only ever show the value from when the screen
        was first constructed."""
        if not self._caps.supports_battery:
            return
        self._apply_level(level, charging)

    def _apply_level(self, level: int, charging: bool) -> None:
        self._level_bar.set_value(level)
        self._level_bar.remove_css_class("success")
        self._level_bar.remove_css_class("warning")
        self._level_bar.remove_css_class("error")
        self._level_bar.remove_css_class("battery-charging")
        if charging:
            self._level_bar.add_css_class("battery-charging")
        elif level >= 50:
            self._level_bar.add_css_class("success")
        elif level >= 20:
            self._level_bar.add_css_class("warning")
        else:
            self._level_bar.add_css_class("error")
        rounded = min(100, max(0, round(level / 10) * 10))
        if charging:
            self._charge_icon.set_from_icon_name(f"battery-level-{rounded}-charging-symbolic")
            self._charge_icon.set_tooltip_text(_("Carregando"))
            self._charge_icon.set_visible(True)
        else:
            self._charge_icon.set_visible(False)
        self._percent_label.set_label(f"{level}%")

    def _on_idle_changed(self, row: Adw.SpinRow, _pspec) -> None:
        if self._idle_timeout_id is not None:
            GLib.source_remove(self._idle_timeout_id)
        value = int(row.get_value())
        self._idle_timeout_id = GLib.timeout_add(SETTINGS_DEBOUNCE_MS, self._commit_idle, value)

    def _commit_idle(self, minutes: int) -> bool:
        self._idle_timeout_id = None

        def _on_done(error: str | None) -> None:
            if error is not None:
                self.emit("write-failed", error)

        self._perform_write_async(lambda: self._device.set_idle_time(minutes * 60), _on_done)
        return GLib.SOURCE_REMOVE

    def _on_threshold_changed(self, row: Adw.SpinRow, _pspec) -> None:
        if self._threshold_timeout_id is not None:
            GLib.source_remove(self._threshold_timeout_id)
        value = int(row.get_value())
        self._threshold_timeout_id = GLib.timeout_add(SETTINGS_DEBOUNCE_MS, self._commit_threshold, value)

    def _commit_threshold(self, percent: int) -> bool:
        self._threshold_timeout_id = None

        def _on_done(error: str | None) -> None:
            if error is not None:
                self.emit("write-failed", error)

        self._perform_write_async(lambda: self._device.set_low_battery_threshold(percent), _on_done)
        return GLib.SOURCE_REMOVE
