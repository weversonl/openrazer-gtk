"""App-level local settings (theme, language) - JSON under the user config dir."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from gi.repository import GLib


def _settings_path() -> Path:
    config_dir = Path(GLib.get_user_config_dir()) / "razer-gtk"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "settings.json"


@dataclass
class AppSettings:
    theme: str = "default"    # 'light', 'dark', or 'default' (follow system)
    lang: str = "pt_BR"       # 'pt_BR' or 'en_US'
    window_width: int | None = None
    window_height: int | None = None


def load_settings() -> AppSettings:
    path = _settings_path()
    if not path.exists():
        return AppSettings()
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return AppSettings()
    return AppSettings(
        theme=data.get("theme", "default"),
        lang=data.get("lang", "pt_BR"),
        window_width=data.get("window_width"),
        window_height=data.get("window_height"),
    )


def save_settings(settings: AppSettings) -> None:
    _settings_path().write_text(json.dumps(asdict(settings), indent=2))
