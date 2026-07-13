"""Autostart: a .desktop file dropped into ~/.config/autostart/."""

import sys
from pathlib import Path

from gi.repository import GLib

APP_ID = "io.github.weversonl.OpenRazerGTK"
PROJECT_ROOT = Path(__file__).resolve().parents[2]

HIDDEN_START_ENV = "RAZER_GTK_START_HIDDEN"


def _autostart_path() -> Path:
    return Path(GLib.get_user_config_dir()) / "autostart" / f"{APP_ID}.desktop"


def is_enabled() -> bool:
    return _autostart_path().exists()


def set_enabled(enabled: bool) -> None:
    path = _autostart_path()
    if not enabled:
        path.unlink(missing_ok=True)
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=OpenRazerGTK\n"
        f"Exec=env {HIDDEN_START_ENV}=1 {sys.executable} -m razer_gtk\n"
        f"Path={PROJECT_ROOT}\n"
        "Icon=input-mouse-symbolic\n"
        "X-GNOME-Autostart-enabled=true\n"
        "NoDisplay=true\n"
    )
    path.write_text(content)
