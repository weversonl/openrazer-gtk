"""Generic per-device-type icon, shared by the sidebar and the overview header."""

DEVICE_TYPE_ICONS = {
    "mouse": "input-mouse-symbolic",
    "mousemat": "input-tablet-symbolic",
    "keyboard": "input-keyboard-symbolic",
    "keypad": "input-keyboard-symbolic",
    "headset": "audio-headset-symbolic",
    "accessory": "media-removable-symbolic",
}
DEFAULT_DEVICE_ICON = "input-gaming-symbolic"


def generic_icon_name(device) -> str:
    return DEVICE_TYPE_ICONS.get(getattr(device, "type", ""), DEFAULT_DEVICE_ICON)
