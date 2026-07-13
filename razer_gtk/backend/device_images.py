"""Per-device custom header image: an opt-in user-supplied photo, stored under ~/.config/razer-gtk/images/."""

from pathlib import Path

from gi.repository import GLib


def _images_dir() -> Path:
    directory = Path(GLib.get_user_config_dir()) / "razer-gtk" / "images"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def get_custom_image(serial: str) -> Path | None:
    for path in sorted(_images_dir().glob(f"{serial}.*")):
        return path
    return None


def set_custom_image(serial: str, source: Path) -> Path:
    remove_custom_image(serial)
    ext = source.suffix.lower() or ".png"
    dest = _images_dir() / f"{serial}{ext}"
    dest.write_bytes(source.read_bytes())
    return dest


def remove_custom_image(serial: str) -> None:
    for old in _images_dir().glob(f"{serial}.*"):
        old.unlink()
