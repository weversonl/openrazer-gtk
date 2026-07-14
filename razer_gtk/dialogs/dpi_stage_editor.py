"""DPI stage editor modal - onboard DPI stage memory, gated on caps.supports_dpi_stages."""

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from razer_gtk.backend import device_names
from razer_gtk.backend.device_adapter import DeviceCapabilities
from razer_gtk.backend.device_icons import generic_icon_name
from razer_gtk.i18n import _

STAGE_STEP = 200


def open_dpi_stage_editor(
    parent: Gtk.Widget,
    caps: DeviceCapabilities,
    perform_write: Callable[[Callable[[], None]], str | None],
    on_saved: Callable[[], None] | None = None,
    on_error: Callable[[str], None] | None = None,
) -> None:
    device = caps.device
    max_dpi = caps.max_dpi or 20000
    active_stage, stages = device.dpi_stages

    dialog = Adw.Dialog(content_width=440, follows_content_size=True, title=_("Estágios de DPI"))

    toolbar_view = Adw.ToolbarView()
    header = Adw.HeaderBar(show_start_title_buttons=False, show_end_title_buttons=False)
    cancel_button = Gtk.Button(label=_("Cancelar"))
    cancel_button.connect("clicked", lambda *_args: dialog.close())
    header.pack_start(cancel_button)
    save_button = Gtk.Button(label=_("Salvar"))
    save_button.add_css_class("suggested-action")
    header.pack_end(save_button)
    toolbar_view.add_top_bar(header)

    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    body.set_margin_top(16)
    body.set_margin_bottom(16)
    body.set_margin_start(16)
    body.set_margin_end(16)

    device_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    device_row.append(Gtk.Image.new_from_icon_name(generic_icon_name(device)))
    label_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    name_label = Gtk.Label(label=device_names.display_name(device), xalign=0.0)
    name_label.add_css_class("heading")
    subtitle_label = Gtk.Label(label=_("Até {max_dpi} DPI").format(max_dpi=max_dpi), xalign=0.0)
    subtitle_label.add_css_class("dim-label")
    label_box.append(name_label)
    label_box.append(subtitle_label)
    device_row.append(label_box)
    body.append(device_row)

    stages_list = Gtk.ListBox()
    stages_list.add_css_class("boxed-list")
    stages_list.set_selection_mode(Gtk.SelectionMode.NONE)
    body.append(stages_list)

    add_button = Gtk.Button(label=_("+ Adicionar estágio"))
    add_button.add_css_class("flat")
    body.append(add_button)

    sync_row = Adw.SwitchRow(
        title=_("Sincronizar"),
        subtitle=_("Também aplica o estágio ativo ao DPI atual do dispositivo ao salvar"),
        active=True,
    )
    body.append(sync_row)

    stage_rows: list[Adw.SpinRow] = []

    def rebuild_stage_rows() -> None:
        child = stages_list.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            stages_list.remove(child)
            child = nxt
        stage_rows.clear()

        for index, (dpi_x, _dpi_y) in enumerate(stages):
            row = Adw.SpinRow.new_with_range(100, max_dpi, 50)
            row.set_title(_("Estágio {n}").format(n=index + 1))
            row.set_value(dpi_x)
            if len(stages) > 1:
                remove_button = Gtk.Button(icon_name="user-trash-symbolic")
                remove_button.set_valign(Gtk.Align.CENTER)
                remove_button.add_css_class("flat")
                remove_button.connect("clicked", lambda _b, i=index: on_remove_stage(i))
                row.add_suffix(remove_button)
            stages_list.append(row)
            stage_rows.append(row)

    def on_remove_stage(index: int) -> None:
        if len(stages) <= 1:
            return
        for i, row in enumerate(stage_rows):
            stages[i] = (int(row.get_value()), int(row.get_value()))
        del stages[index]
        rebuild_stage_rows()

    def on_add_stage(_button: Gtk.Button) -> None:
        for i, row in enumerate(stage_rows):
            stages[i] = (int(row.get_value()), int(row.get_value()))
        last = stages[-1][0] if stages else 800
        new_value = min(last + STAGE_STEP, max_dpi)
        stages.append((new_value, new_value))
        rebuild_stage_rows()

    add_button.connect("clicked", on_add_stage)
    rebuild_stage_rows()

    def on_save(_button: Gtk.Button) -> None:
        final_stages = [(int(row.get_value()), int(row.get_value())) for row in stage_rows]
        active = min(active_stage, len(final_stages))

        def _write() -> None:
            device.dpi_stages = (active, final_stages)
            if sync_row.get_active():
                device.dpi = final_stages[active - 1]

        error = perform_write(_write)
        if error is None:
            dialog.close()
            if on_saved is not None:
                on_saved()
        elif on_error is not None:
            on_error(error)

    save_button.connect("clicked", on_save)

    toolbar_view.set_content(body)
    dialog.set_child(toolbar_view)
    dialog.present(parent)
