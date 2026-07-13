"""Per-device display name override - purely cosmetic, never touches the device/daemon."""

import json
from pathlib import Path

from gi.repository import GLib


def _names_path() -> Path:
    config_dir = Path(GLib.get_user_config_dir()) / "razer-gtk"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "device_names.json"


def _load() -> dict:
    path = _names_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    _names_path().write_text(json.dumps(data, indent=2))


def get_custom_name(serial: str) -> str | None:
    return _load().get(str(serial))


def set_custom_name(serial: str, name: str) -> None:
    data = _load()
    data[str(serial)] = name
    _save(data)


def remove_custom_name(serial: str) -> None:
    data = _load()
    if data.pop(str(serial), None) is not None:
        _save(data)


def display_name(device) -> str:
    return get_custom_name(str(device.serial)) or device.name
