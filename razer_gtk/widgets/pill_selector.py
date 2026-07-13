"""Reusable pill-style single-choice selector (effects, DPI stages, poll rate, theme, language)."""

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GObject, Gtk


class PillSelector(Gtk.ScrolledWindow):
    """A row of round toggle buttons, only one active at a time.

    Wraps the actual Gtk.FlowBox in a scrollbar-less Gtk.ScrolledWindow
    with a fixed size_request, rather than exposing the FlowBox directly
    or leaving its size to GTK's own negotiation - GTK4's FlowBox has a
    real measurement bug in this environment: with two or more FlowBox-
    based widgets like this one in the same window, giving the FlowBox
    (or anything that lets it expand/hexpand) more room than one line
    needs makes it just fill that space left-aligned instead of reporting
    a smaller size to align against, and every attempt at computing a
    "smaller when tight, capped when spacious" size by hand (dynamic
    size_request from a resize handler, a custom Gtk.LayoutManager) hit a
    further GTK4 quirk of its own. A plain fixed size_request is the one
    approach that reliably measures and right-aligns correctly - the
    trade-off is that the row (and so the window) can't shrink below
    `max_width`, so pick it to match the content's real need, not a
    worst-case padding.
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

        self._flow = Gtk.FlowBox()
        self._flow.set_orientation(Gtk.Orientation.HORIZONTAL)
        self._flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._flow.set_row_spacing(6)
        self._flow.set_column_spacing(6)
        self._flow.set_homogeneous(False)
        self._flow.set_max_children_per_line(999)
        self._flow.set_halign(Gtk.Align.END)
        self.set_child(self._flow)

        self._buttons: dict[str, Gtk.ToggleButton] = {}
        self._selected: str | None = None
        self._in_update = False
        if options is not None:
            self.set_options(options, selected)

    def set_options(self, options: list[tuple[str, str]], selected: str | None = None) -> None:
        child = self._flow.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._flow.remove(child)
            child = nxt
        self._buttons = {}

        for option_id, label in options:
            button = Gtk.ToggleButton(label=label)
            button.set_valign(Gtk.Align.CENTER)
            button.add_css_class("chip-pill")
            button.connect("toggled", self._on_toggled, option_id)
            self._flow.append(button)
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
