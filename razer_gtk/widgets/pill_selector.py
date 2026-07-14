"""Reusable pill-style single-choice selector (effects, DPI stages, poll rate, theme, language)."""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GObject, Gtk


class PillSelector(Gtk.ScrolledWindow):
    """A row of round toggle buttons, right-aligned within a fixed-width box.

    Uses a plain Gtk.Box with a leading hexpand spacer, not Gtk.FlowBox -
    FlowBox doesn't reliably right-align or report its own width on this
    GTK stack (4.22/Libadwaita 1.9). `max_width` should match the content's
    real need: the row (and window) can't shrink below it.
    """

    __gsignals__ = {
        "selection-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(
        self,
        options: list[tuple[str, str]] | None = None,
        selected: str | None = None,
        max_width: int = 420,
    ) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)
        self.set_propagate_natural_height(True)
        self.set_size_request(max_width, -1)
        self.set_valign(Gtk.Align.CENTER)
        self.set_hexpand(True)
        self.set_halign(Gtk.Align.END)

        self._box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self._spacer = Gtk.Box()
        self._spacer.set_hexpand(True)
        self._box.append(self._spacer)

        self.set_child(self._box)

        self._buttons: dict[str, Gtk.ToggleButton] = {}
        self._selected: str | None = None
        self._in_update = False
        if options is not None:
            self.set_options(options, selected)

    def set_options(self, options: list[tuple[str, str]], selected: str | None = None) -> None:
        child = self._spacer.get_next_sibling()
        while child is not None:
            nxt = child.get_next_sibling()
            self._box.remove(child)
            child = nxt
        self._buttons = {}

        for option_id, label in options:
            button = Gtk.ToggleButton(label=label)
            button.set_valign(Gtk.Align.CENTER)
            button.add_css_class("chip-pill")
            button.connect("toggled", self._on_toggled, option_id)
            self._box.append(button)
            self._buttons[option_id] = button

        self._selected = None
        if selected is not None and selected in self._buttons:
            self.set_selected(selected)
        elif options:
            self.set_selected(options[0][0])

    def set_selected(self, option_id: str) -> None:
        if option_id not in self._buttons or option_id == self._selected:
            return
        self._in_update = True
        for oid, button in self._buttons.items():
            active = oid == option_id
            button.set_active(active)
            if active:
                button.add_css_class("suggested-action")
            else:
                button.remove_css_class("suggested-action")
        self._selected = option_id
        self._in_update = False

    def get_selected(self) -> str | None:
        return self._selected

    def _on_toggled(self, button: Gtk.ToggleButton, option_id: str) -> None:
        if self._in_update:
            return
        if not button.get_active():
            if self._selected == option_id:
                button.set_active(True)
            return
        self.set_selected(option_id)
        self.emit("selection-changed", option_id)
