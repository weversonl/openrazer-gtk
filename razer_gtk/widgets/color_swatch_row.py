"""Reusable color swatch row: preset swatches + a dashed '+' for a custom color."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GObject, Gtk

_registered_colors: set[str] = set()
_shared_provider: Gtk.CssProvider | None = None


def _color_css_class(hex_color: str) -> str:
    """Ensure a `.swatch-<hex>` CSS class exists on the default display, return its name."""
    global _shared_provider
    hex_color = hex_color.lstrip("#").lower()
    class_name = f"swatch-{hex_color}"
    if class_name not in _registered_colors:
        if _shared_provider is None:
            _shared_provider = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                _shared_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
        # GtkCssProvider has no incremental API, so reload the whole stylesheet.
        _registered_colors.add(class_name)
        existing = "\n".join(f".{name} {{ background-color: #{name[7:]}; }}" for name in _registered_colors)
        _shared_provider.load_from_string(existing)
    return class_name


class ColorSwatchRow(Gtk.Box):
    """One row = a palette of preset color swatches + a dashed '+' custom trigger."""

    __gsignals__ = {
        "color-selected": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "custom-requested": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, palette: list[str], selected_hex: str | None = None) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._swatch_buttons: dict[str, Gtk.Button] = {}
        self._selected: str | None = None
        self.set_palette(palette, selected_hex)

    def set_palette(self, palette: list[str], selected_hex: str | None = None) -> None:
        child = self.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.remove(child)
            child = nxt
        self._swatch_buttons = {}

        for hex_color in palette:
            button = self._make_swatch_button(hex_color)
            button.connect("clicked", self._on_swatch_clicked, hex_color)
            self.append(button)
            self._swatch_buttons[hex_color.lstrip("#").lower()] = button

        plus_button = Gtk.Button()
        plus_button.set_size_request(28, 28)
        plus_button.set_halign(Gtk.Align.CENTER)
        plus_button.set_valign(Gtk.Align.CENTER)
        plus_button.add_css_class("round-swatch")
        plus_button.add_css_class("swatch-add")
        plus_button.set_child(Gtk.Image.new_from_icon_name("list-add-symbolic"))
        plus_button.connect("clicked", lambda *_args: self.emit("custom-requested"))
        self.append(plus_button)

        self._selected = None
        if selected_hex is not None:
            self.set_selected(selected_hex)

    def _make_swatch_button(self, hex_color: str) -> Gtk.Button:
        button = Gtk.Button()
        button.set_size_request(28, 28)
        button.set_halign(Gtk.Align.CENTER)
        button.set_valign(Gtk.Align.CENTER)
        button.add_css_class("round-swatch")
        button.add_css_class(_color_css_class(hex_color))
        return button

    def set_selected(self, hex_color: str) -> None:
        normalized = hex_color.lstrip("#").lower()
        for key, button in self._swatch_buttons.items():
            if key == normalized:
                button.add_css_class("selected-swatch")
            else:
                button.remove_css_class("selected-swatch")
        self._selected = normalized

    def get_selected(self) -> str | None:
        return self._selected

    def _on_swatch_clicked(self, _button: Gtk.Button, hex_color: str) -> None:
        self.set_selected(hex_color)
        self.emit("color-selected", hex_color.lstrip("#").lower())
