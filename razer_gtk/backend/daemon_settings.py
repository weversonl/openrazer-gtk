"""Reads/writes openrazer-daemon's own config file (~/.config/openrazer/razer.conf) -
battery-low notifications are a daemon feature, not something this app implements itself."""

import configparser
import subprocess
from dataclasses import dataclass
from pathlib import Path

from gi.repository import GLib

SECTION = "Startup"
KEY_ENABLED = "battery_notifier"
KEY_PERCENT = "battery_notifier_percent"
KEY_FREQ = "battery_notifier_freq"

DEFAULT_PERCENT = 33
DEFAULT_FREQ_SECONDS = 3600


def _config_path() -> Path:
    return Path(GLib.get_user_config_dir()) / "openrazer" / "razer.conf"


@dataclass
class BatteryNotifierSettings:
    enabled: bool = True
    percent: int = DEFAULT_PERCENT
    freq_minutes: int = DEFAULT_FREQ_SECONDS // 60


def read() -> BatteryNotifierSettings:
    parser = configparser.ConfigParser()
    parser.read(_config_path())
    if not parser.has_section(SECTION):
        return BatteryNotifierSettings()
    return BatteryNotifierSettings(
        enabled=parser.getboolean(SECTION, KEY_ENABLED, fallback=True),
        percent=parser.getint(SECTION, KEY_PERCENT, fallback=DEFAULT_PERCENT),
        freq_minutes=parser.getint(SECTION, KEY_FREQ, fallback=DEFAULT_FREQ_SECONDS) // 60,
    )


def write(settings: BatteryNotifierSettings) -> None:
    path = _config_path()
    parser = configparser.ConfigParser()
    parser.read(path)
    if not parser.has_section(SECTION):
        parser.add_section(SECTION)
    parser.set(SECTION, KEY_ENABLED, str(settings.enabled))
    parser.set(SECTION, KEY_PERCENT, str(settings.percent))
    parser.set(SECTION, KEY_FREQ, str(settings.freq_minutes * 60))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        parser.write(f)


def restart_daemon() -> str | None:
    """Best-effort: openrazer-daemon usually runs as a `systemctl --user`
    service, but that's not guaranteed on every install - return an error
    string instead of raising so the caller can tell the user to restart
    it manually."""
    try:
        result = subprocess.run(
            ["systemctl", "--user", "restart", "openrazer-daemon"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return str(exc)
    if result.returncode != 0:
        return result.stderr.strip() or f"exit code {result.returncode}"
    return None
