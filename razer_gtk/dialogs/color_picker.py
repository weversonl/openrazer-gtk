"""Color picker: fixed 45-swatch vivid palette grid + custom hex entry."""

import re
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, GLib, Gtk

from razer_gtk.i18n import _
from razer_gtk.widgets.color_swatch_row import _color_css_class

PALETTE = [
    "ff0000", "ff8000", "ffff00", "80ff00", "00ff00", "00ff80", "00ffff", "0080ff", "0000ff",
    "8000ff", "ff00ff", "ff0080", "ff4040", "ffa040", "ffff40", "40ff40", "40ffff", "4040ff",
    "b30000", "b35900", "b3b300", "59b300", "00b300", "00b359", "00b3b3", "0059b3", "0000b3",
    "ff9999", "ffd199", "ffff99", "d1ff99", "99ff99", "99ffd1", "99ffff", "99d1ff", "9999ff",
    "ffffff", "e0e0e0", "c0c0c0", "a0a0a0", "808080", "606060", "404040", "202020", "000000",
]

HEX_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")


def open_color_picker(parent: Gtk.Widget, initial_hex: str, on_chosen: Callable[[str], None]) -> None:
    dialog = Adw.Dialog(content_width=420, follows_content_size=True, title=_("Escolher cor"))

    toolbar_view = Adw.ToolbarView()
    header = Adw.HeaderBar(show_start_title_buttons=False, show_end_title_buttons=False)
    cancel_button = Gtk.Button(label=_("Cancelar"))
    cancel_button.connect("clicked", lambda *_args: dialog.close())
    header.pack_start(cancel_button)
    select_button = Gtk.Button(label=_("Selecionar"))
    select_button.add_css_class("suggested-action")
    header.pack_end(select_button)
    toolbar_view.add_top_bar(header)

    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    body.set_margin_top(16)
    body.set_margin_bottom(16)
    body.set_margin_start(16)
    body.set_margin_end(16)

    selected_hex = initial_hex.lstrip("#").lower()

    flow = Gtk.FlowBox()
    flow.set_max_children_per_line(9)
    flow.set_min_children_per_line(9)
    flow.set_selection_mode(Gtk.SelectionMode.NONE)
    flow.set_row_spacing(6)
    flow.set_column_spacing(6)

    preview = Gtk.Box()
    preview.set_size_request(32, 32)
    preview.set_halign(Gtk.Align.CENTER)
    preview.set_valign(Gtk.Align.CENTER)
    preview.add_css_class("round-swatch")

    hex_entry = Gtk.Entry(text=f"#{selected_hex}")

    def set_selected(hex_color: str) -> None:
        nonlocal selected_hex
        selected_hex = hex_color.lstrip("#").lower()
        for child in preview.get_css_classes():
            if child.startswith("swatch-"):
                preview.remove_css_class(child)
        preview.add_css_class(_color_css_class(selected_hex))
        if hex_entry.get_text().lstrip("#").lower() != selected_hex:
            hex_entry.handler_block_by_func(on_hex_changed)
            hex_entry.set_text(f"#{selected_hex}")
            hex_entry.handler_unblock_by_func(on_hex_changed)

    for hex_color in PALETTE:
        button = Gtk.Button()
        button.set_size_request(28, 28)
        button.set_halign(Gtk.Align.CENTER)
        button.set_valign(Gtk.Align.CENTER)
        button.add_css_class("round-swatch")
        button.add_css_class(_color_css_class(hex_color))
        button.connect("clicked", lambda _b, h=hex_color: set_selected(h))
        flow.append(button)

    body.append(flow)
    body.append(Gtk.Separator())

    custom_label = Gtk.Label(label=_("Personalizada"), xalign=0.0)
    custom_label.add_css_class("heading")
    body.append(custom_label)

    custom_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    custom_row.append(preview)
    hex_entry.set_hexpand(True)
    custom_row.append(hex_entry)

    more_colors_button = Gtk.Button(label=_("Mais cores…"))
    more_colors_button.connect("clicked", lambda *_args: on_more_colors())
    custom_row.append(more_colors_button)

    body.append(custom_row)

    def on_hex_changed(entry: Gtk.Entry) -> None:
        text = entry.get_text()
        if HEX_RE.match(text):
            set_selected(text)
            select_button.set_sensitive(True)
        else:
            select_button.set_sensitive(False)

    hex_entry.connect("changed", on_hex_changed)

    def on_more_colors() -> None:
        rgba = Gdk.RGBA()
        rgba.parse(f"#{selected_hex}")
        color_dialog = Gtk.ColorDialog(with_alpha=False, title=_("Escolher cor"))

        def on_picked(dialog: Gtk.ColorDialog, result) -> None:
            try:
                picked = dialog.choose_rgba_finish(result)
            except GLib.Error:
                return
            if picked is None:
                return
            hex_color = "{:02x}{:02x}{:02x}".format(
                round(picked.red * 255), round(picked.green * 255), round(picked.blue * 255)
            )
            set_selected(hex_color)

        root = dialog.get_root()
        color_dialog.choose_rgba(root, rgba, None, on_picked)

    def on_select(_button: Gtk.Button) -> None:
        on_chosen(selected_hex)
        dialog.close()

    select_button.connect("clicked", on_select)

    set_selected(selected_hex)

    toolbar_view.set_content(body)
    dialog.set_child(toolbar_view)
    dialog.present(parent)
