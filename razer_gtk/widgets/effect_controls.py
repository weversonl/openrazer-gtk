"""Reusable effect pills + color swatches + brightness slider, driving one LightSurface."""

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, GObject, Gtk

from razer_gtk.backend.device_adapter import EFFECT_EXTRA_PARAM, LightSurface
from razer_gtk.i18n import N_, _
from razer_gtk.widgets.color_swatch_row import ColorSwatchRow
from razer_gtk.widgets.pill_row import PillRow
from razer_gtk.widgets.pill_selector import PillSelector

EFFECT_LABELS = {
    "static": N_("Estática"),
    "spectrum": N_("Espectro"),
    "wave": N_("Onda"),
    "wheel": N_("Roda"),
    "breath_single": N_("Respiração"),
    "breath_dual": N_("Respiração dupla"),
    "breath_triple": N_("Respiração tripla"),
    "breath_random": N_("Respiração aleatória"),
    "breath_mono": N_("Respiração mono"),
    "reactive": N_("Reativo"),
    "ripple": N_("Ondulação"),
    "ripple_random": N_("Ondulação aleatória"),
    "starlight_single": N_("Starlight"),
    "starlight_dual": N_("Starlight duplo"),
    "starlight_random": N_("Starlight aleatório"),
    "none": N_("Desligado"),
    "on": N_("Ligado"),
    "blinking": N_("Piscando"),
    "pulsate": N_("Pulsante"),
}

DEFAULT_SWATCH_HEX = "00ff00"
BRIGHTNESS_DEBOUNCE_MS = 250

# Must match the Effect row's PillSelector max_width below, so both rows
# share the same right edge.
EFFECT_PILL_MAX_WIDTH = 920


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"{r:02x}{g:02x}{b:02x}"


class EffectControlsGroup(Gtk.Box):
    __gsignals__ = {
        "write-failed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(
        self,
        zone: LightSurface,
        device,
        perform_write_async: Callable[[Callable[[], None], Callable[[str | None], None]], None],
        palette: list[str],
        open_color_picker: Callable[[str, Callable[[str], None]], None],
        snapshot: dict,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self._zone = zone
        self._device = device
        self._perform_write_async = perform_write_async
        self._palette = palette
        self._open_color_picker = open_color_picker
        self._brightness_timeout_id: int | None = None
        self._initial_brightness = snapshot.get("primary_brightness", 100.0)

        snapshot_effect = snapshot.get("primary_effect")
        self._effect = snapshot_effect if snapshot_effect in zone.supported_effects else None
        if self._effect is None:
            self._effect = zone.supported_effects[0] if zone.supported_effects else None

        self._colors = self._read_initial_colors(snapshot.get("primary_colors", b""))
        self._extra_arg = self._read_initial_extra_arg(snapshot.get("primary_extra_arg"))

        listbox = Gtk.ListBox()
        listbox.add_css_class("boxed-list")
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.append(listbox)

        self._pills = PillSelector(
            [(name, _(EFFECT_LABELS.get(name, name.title()))) for name in zone.supported_effects],
            selected=self._effect,
            max_width=EFFECT_PILL_MAX_WIDTH,
        )
        effect_row = PillRow(_("Efeito"), self._pills)
        listbox.append(effect_row)
        self._pills.connect("selection-changed", self._on_effect_selected)

        self._color_row = Adw.ActionRow(title=_("Cor"))
        self._color_row.set_title_lines(1)
        self._swatch_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._swatch_box.set_valign(Gtk.Align.CENTER)
        self._color_row.add_suffix(self._swatch_box)
        listbox.append(self._color_row)
        # Adw.ActionRow acts as the GtkListBox row itself (no auto-wrap),
        # so hiding it directly correctly excludes it from the list.
        self._rebuild_swatches()

        self._extra_arg_pill_holder = Gtk.Box()
        self._extra_arg_row = PillRow("", self._extra_arg_pill_holder)
        listbox.append(self._extra_arg_row)
        # Unlike Adw.ActionRow, a plain Gtk.Box (PillRow) *does* get
        # auto-wrapped in its own GtkListBoxRow - hiding just the PillRow
        # leaves that wrapper visible with empty content, still painting
        # its own separator (the boxed-list showed a doubled divider).
        # Hide the wrapper itself instead.
        self._extra_arg_list_row = self._extra_arg_row.get_parent()
        self._rebuild_extra_arg_row()

        if zone.supports_brightness:
            listbox.append(self._build_brightness_row())

    def _read_initial_colors(self, raw: bytes) -> list[str]:
        slots = self._zone.effect_color_slots.get(self._effect, 0) if self._effect else 0
        if slots == 0:
            return []
        colors = []
        for i in range(slots):
            offset = i * 3
            if offset + 3 <= len(raw):
                colors.append(_rgb_to_hex(raw[offset], raw[offset + 1], raw[offset + 2]))
            else:
                colors.append(DEFAULT_SWATCH_HEX)
        return colors

    def _read_initial_extra_arg(self, raw_value) -> object | None:
        spec = EFFECT_EXTRA_PARAM.get(self._effect) if self._effect else None
        if spec is None:
            return None
        valid = {value for value, _label in spec["options"]}
        return raw_value if raw_value in valid else spec["default"]

    def _on_effect_selected(self, _pills: PillSelector, effect: str) -> None:
        self._effect = effect
        slots = self._zone.effect_color_slots.get(effect, 0)
        self._colors = [DEFAULT_SWATCH_HEX] * slots
        spec = EFFECT_EXTRA_PARAM.get(effect)
        self._extra_arg = spec["default"] if spec is not None else None
        self._rebuild_swatches()
        self._rebuild_extra_arg_row()
        self._apply()

    def _rebuild_extra_arg_row(self) -> None:
        child = self._extra_arg_pill_holder.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._extra_arg_pill_holder.remove(child)
            child = nxt

        spec = EFFECT_EXTRA_PARAM.get(self._effect) if self._effect else None
        if spec is None:
            self._extra_arg_list_row.set_visible(False)
            return

        self._extra_arg_row.set_title(_(spec["label"]))
        pills = PillSelector(
            [(str(value), _(label)) for value, label in spec["options"]],
            selected=str(self._extra_arg),
            max_width=400,
        )
        pills.connect("selection-changed", self._on_extra_arg_selected)
        self._extra_arg_pill_holder.append(pills)
        self._extra_arg_list_row.set_visible(True)

    def _on_extra_arg_selected(self, _pills: PillSelector, value: str) -> None:
        self._extra_arg = int(value)
        self._apply()

    def _rebuild_swatches(self) -> None:
        child = self._swatch_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._swatch_box.remove(child)
            child = nxt

        for index, current_hex in enumerate(self._colors):
            row = ColorSwatchRow(self._palette, selected_hex=current_hex)
            row.connect("color-selected", self._on_color_selected, index)
            row.connect("custom-requested", self._on_custom_requested, index)
            self._swatch_box.append(row)

        self._color_row.set_visible(bool(self._colors))

    def _on_color_selected(self, _row: ColorSwatchRow, hex_color: str, index: int) -> None:
        self._colors[index] = hex_color
        self._apply()

    def _on_custom_requested(self, _row: ColorSwatchRow, index: int) -> None:
        def on_chosen(hex_color: str) -> None:
            self._colors[index] = hex_color
            self._rebuild_swatches()
            self._apply()

        current = self._colors[index] if index < len(self._colors) else DEFAULT_SWATCH_HEX
        self._open_color_picker(current, on_chosen)

    def _build_brightness_row(self) -> Gtk.Widget:
        scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL)
        scale.set_valign(Gtk.Align.CENTER)
        scale.set_range(0, 100)
        scale.set_value(self._initial_brightness)
        scale.set_size_request(160, -1)

        value_label = Gtk.Label(label=f"{self._initial_brightness:.0f}%")
        value_label.set_width_chars(4)
        value_label.set_xalign(1.0)
        value_label.add_css_class("dim-label")

        holder = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        holder.append(scale)
        holder.append(value_label)
        holder.set_halign(Gtk.Align.END)

        # Fixed-width clamp so this row shares a right edge with the
        # Effect row's PillSelector regardless of window width.
        clamp = Gtk.ScrolledWindow()
        clamp.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)
        clamp.set_propagate_natural_height(True)
        clamp.set_size_request(EFFECT_PILL_MAX_WIDTH, -1)
        clamp.set_valign(Gtk.Align.CENTER)
        clamp.set_hexpand(True)
        clamp.set_halign(Gtk.Align.END)
        clamp.set_child(holder)

        scale.connect("value-changed", self._on_brightness_changed, value_label)
        return PillRow(_("Brilho"), clamp)

    def _on_brightness_changed(self, scale: Gtk.Scale, value_label: Gtk.Label) -> None:
        if self._brightness_timeout_id is not None:
            GLib.source_remove(self._brightness_timeout_id)
        value = scale.get_value()
        value_label.set_label(f"{value:.0f}%")
        self._brightness_timeout_id = GLib.timeout_add(
            BRIGHTNESS_DEBOUNCE_MS, self._commit_brightness, value
        )

    def _commit_brightness(self, value: float) -> bool:
        self._brightness_timeout_id = None

        def _write() -> None:
            if self._zone.brightness_source == "zone":
                self._zone.surface.brightness = value
            elif self._zone.brightness_source == "device":
                self._device.brightness = value

        def _on_done(error: str | None) -> None:
            if error is not None:
                self.emit("write-failed", error)

        self._perform_write_async(_write, _on_done)
        return GLib.SOURCE_REMOVE

    def _apply(self) -> None:
        if self._effect is None:
            return
        effect_fn = getattr(self._zone.surface, self._effect, None)
        if effect_fn is None:
            return
        color_args: list[int] = []
        for hex_color in self._colors:
            color_args.extend(_hex_to_rgb(hex_color))
        extra_args = [self._extra_arg] if self._extra_arg is not None else []
        args = [*color_args, *extra_args]

        def _write() -> None:
            effect_fn(*args)

        def _on_done(error: str | None) -> None:
            if error is not None:
                self.emit("write-failed", error)

        self._perform_write_async(_write, _on_done)

    def current_effect(self) -> str | None:
        return self._effect

    def current_colors(self) -> list[str]:
        return list(self._colors)
