"""A boxed-list row: title (protected, never shrinks) + flexible control (e.g. PillSelector) that wraps instead."""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


class PillRow(Gtk.Box):
    """Plain Gtk.Box row, not Adw.ActionRow: an ActionRow's title/suffix
    both compete for space via hexpand, so a wide suffix can crush the
    title. Here the title has hexpand=False (protected, always its full
    natural width) and the control has hexpand=True + halign=END - hexpand
    alone only inflates the control's own cell without moving its content,
    so halign=END is what actually pins it to the right edge.

    `control` should already be sized (e.g. a PillSelector with its own
    `max_width`) - this row doesn't compute or resize it itself.
    """

    def __init__(
        self,
        title: str,
        control: Gtk.Widget,
        icon_name: str | None = None,
        subtitle: str | None = None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.set_margin_top(12)
        self.set_margin_bottom(12)
        self.set_margin_start(12)
        self.set_margin_end(12)

        if icon_name is not None:
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_valign(Gtk.Align.CENTER)
            self.append(icon)

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_box.set_hexpand(False)
        title_box.set_valign(Gtk.Align.CENTER)

        self._title_label = Gtk.Label(label=title, xalign=0.0)
        title_box.append(self._title_label)

        self._subtitle_label = Gtk.Label(xalign=0.0)
        self._subtitle_label.add_css_class("dim-label")
        self._subtitle_label.add_css_class("caption")
        title_box.append(self._subtitle_label)
        if subtitle:
            self._subtitle_label.set_label(subtitle)
        else:
            self._subtitle_label.set_visible(False)

        self.append(title_box)

        control.set_hexpand(True)
        control.set_halign(Gtk.Align.END)
        self.append(control)

    def set_title(self, title: str) -> None:
        self._title_label.set_label(title)
