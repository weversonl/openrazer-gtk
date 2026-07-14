"""Overview 'DPI' card - boxed-list of ActionRows (title left, control right)."""

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, GObject, Gtk

from razer_gtk.backend.device_adapter import DeviceCapabilities
from razer_gtk.i18n import _
from razer_gtk.widgets.pill_row import PillRow
from razer_gtk.widgets.pill_selector import PillSelector

DPI_DEBOUNCE_MS = 250


class DpiCard(Adw.PreferencesGroup):
    __gsignals__ = {
        "write-failed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "stage-editor-requested": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(
        self,
        caps: DeviceCapabilities,
        perform_write_async: Callable[[Callable[[], None], Callable[[str | None], None]], None],
        snapshot: dict,
    ) -> None:
        super().__init__(title=_("Desempenho"), description=_("Sensibilidade e taxa de atualização do sensor"))
        self._caps = caps
        self._device = caps.device
        self._perform_write_async = perform_write_async
        self._snapshot = snapshot
        self._dpi_timeout_id: int | None = None
        self._independent = False

        if not caps.supports_dpi and not caps.supports_poll_rate:
            self.set_visible(False)
            return

        self._listbox = Gtk.ListBox()
        self._listbox.add_css_class("boxed-list")
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)

        if caps.supports_dpi:
            if caps.supports_dpi_stages:
                self._listbox.append(self._build_stage_row())
            elif caps.dpi_is_discrete:
                self._listbox.append(self._build_discrete_row())

            if caps.supports_independent_axes:
                self._listbox.append(self._build_independent_axes_row())

            if not caps.supports_dpi_stages and not caps.dpi_is_discrete:
                self._listbox.append(self._build_continuous_row())

        if caps.supports_poll_rate:
            self._listbox.append(self._build_poll_rate_row())

        row = Adw.PreferencesRow(activatable=False)
        row.set_child(self._listbox)
        self.add(row)

    def _build_stage_row(self) -> Gtk.Widget:
        active_stage, stages = self._snapshot.get("dpi_stages", (1, [(800, 800)]))
        options = [(str(i), str(dpi_x)) for i, (dpi_x, _dpi_y) in enumerate(stages, start=1)]

        pills = PillSelector(options, selected=str(active_stage), max_width=290)
        pills.connect("selection-changed", self._on_stage_selected, stages)

        edit_button = Gtk.Button(label=_("Editar"))
        edit_button.set_valign(Gtk.Align.CENTER)
        edit_button.connect("clicked", lambda *_a: self.emit("stage-editor-requested"))

        suffix = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        suffix.append(pills)
        suffix.append(edit_button)

        return PillRow("DPI", suffix, icon_name="speedometer-symbolic")

    def _on_stage_selected(self, _pills: PillSelector, value: str, stages: list[tuple[int, int]]) -> None:
        new_active = int(value)
        target = stages[new_active - 1]

        def _write() -> None:
            self._device.dpi_stages = (new_active, stages)
            self._device.dpi = target

        def _on_done(error: str | None) -> None:
            if error is not None:
                self.emit("write-failed", error)

        self._perform_write_async(_write, _on_done)

    def _build_discrete_row(self) -> Gtk.Widget:
        current_x, _current_y = self._snapshot.get("dpi", (800, 0))
        options = [(str(v), str(v)) for v in self._caps.available_dpi]

        pills = PillSelector(options, selected=str(current_x))
        pills.connect("selection-changed", self._on_discrete_dpi_selected)
        return PillRow(_("DPI"), pills, icon_name="speedometer-symbolic")

    def _on_discrete_dpi_selected(self, _pills: PillSelector, value: str) -> None:
        dpi_value = int(value)

        def _on_done(error: str | None) -> None:
            if error is not None:
                self.emit("write-failed", error)

        self._perform_write_async(lambda: setattr(self._device, "dpi", (dpi_value, 0)), _on_done)

    def _build_independent_axes_row(self) -> Adw.SwitchRow:
        row = Adw.SwitchRow(title=_("Eixos independentes (X/Y)"), icon_name="view-grid-symbolic")
        row.set_title_lines(1)
        row.connect("notify::active", self._on_independent_toggled)
        return row

    def _on_independent_toggled(self, row: Adw.SwitchRow, _pspec) -> None:
        self._independent = row.get_active()
        if hasattr(self, "_y_scale"):
            self._y_scale.set_visible(self._independent)
            if not self._independent:
                self._y_scale.set_value(self._x_scale.get_value())
                self._commit_dpi()

    def _build_continuous_row(self) -> Adw.ActionRow:
        max_dpi = self._caps.max_dpi or 20000
        current_x, current_y = self._snapshot.get("dpi", (800, 800))

        self._x_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, hexpand=True)
        self._x_scale.set_valign(Gtk.Align.CENTER)
        self._x_scale.set_range(100, max_dpi)
        self._x_scale.set_value(current_x)
        self._x_scale.set_draw_value(True)
        self._x_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self._x_scale.set_format_value_func(lambda _s, value: f"{value:.0f}")
        self._x_scale.connect("value-changed", self._on_dpi_scale_changed)

        self._y_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, hexpand=True)
        self._y_scale.set_valign(Gtk.Align.CENTER)
        self._y_scale.set_range(100, max_dpi)
        self._y_scale.set_value(current_y or current_x)
        self._y_scale.set_draw_value(True)
        self._y_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self._y_scale.set_format_value_func(lambda _s, value: f"{value:.0f}")
        self._y_scale.set_visible(False)
        self._y_scale.connect("value-changed", self._on_dpi_scale_changed)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True)
        x_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        x_row.append(Gtk.Label(label="X"))
        x_row.append(self._x_scale)
        y_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        y_row.append(Gtk.Label(label="Y"))
        y_row.append(self._y_scale)
        box.append(x_row)
        box.append(y_row)

        row = Adw.ActionRow(
            title=_("DPI (até {max_dpi})").format(max_dpi=max_dpi), icon_name="speedometer-symbolic"
        )
        row.set_title_lines(1)
        row.add_suffix(box)
        return row

    def _on_dpi_scale_changed(self, _scale: Gtk.Scale) -> None:
        if not self._independent:
            self._y_scale.handler_block_by_func(self._on_dpi_scale_changed)
            self._y_scale.set_value(self._x_scale.get_value())
            self._y_scale.handler_unblock_by_func(self._on_dpi_scale_changed)
        if self._dpi_timeout_id is not None:
            GLib.source_remove(self._dpi_timeout_id)
        self._dpi_timeout_id = GLib.timeout_add(DPI_DEBOUNCE_MS, self._commit_dpi)

    def _commit_dpi(self) -> bool:
        self._dpi_timeout_id = None
        x = int(self._x_scale.get_value())
        y = int(self._y_scale.get_value()) if self._independent else x

        def _on_done(error: str | None) -> None:
            if error is not None:
                self.emit("write-failed", error)

        self._perform_write_async(lambda: setattr(self._device, "dpi", (x, y)), _on_done)
        return GLib.SOURCE_REMOVE

    def _build_poll_rate_row(self) -> Gtk.Widget:
        current = self._snapshot.get("poll_rate", self._caps.supported_poll_rates[0] if self._caps.supported_poll_rates else 1000)
        options = [(str(v), f"{v} Hz") for v in self._caps.supported_poll_rates]

        pills = PillSelector(options, selected=str(current), max_width=290)
        pills.connect("selection-changed", self._on_poll_rate_selected)
        return PillRow(_("Taxa de atualização"), pills, icon_name="input-mouse-symbolic")

    def _on_poll_rate_selected(self, _pills: PillSelector, value: str) -> None:
        rate = int(value)

        def _on_done(error: str | None) -> None:
            if error is not None:
                self.emit("write-failed", error)

        self._perform_write_async(lambda: setattr(self._device, "poll_rate", rate), _on_done)
