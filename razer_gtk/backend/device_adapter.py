"""Capability-gating layer. Only module allowed to call `device.has(...)` / capability-dict lookups directly."""

import logging
from dataclasses import dataclass, field

from openrazer.client import constants as c
from openrazer.client.device import RazerDevice
from openrazer.client.fx import RazerFX, SingleLed

from razer_gtk.i18n import N_, _

logger = logging.getLogger(__name__)

# Effects taking a positional speed/direction arg after the color
# components. `attr` is the read-only property that reports the device's
# current value, used to preselect the right pill.
EFFECT_EXTRA_PARAM: dict[str, dict] = {
    "reactive": {
        "attr": "speed",
        "default": c.REACTIVE_1000MS,
        "label": N_("Velocidade"),
        "options": [
            (c.REACTIVE_500MS, N_("Rápida")),
            (c.REACTIVE_1000MS, N_("Normal")),
            (c.REACTIVE_1500MS, N_("Lenta")),
            (c.REACTIVE_2000MS, N_("Muito lenta")),
        ],
    },
    "starlight_single": {
        "attr": "speed",
        "default": c.STARLIGHT_NORMAL,
        "label": N_("Velocidade"),
        "options": [
            (c.STARLIGHT_FAST, N_("Rápida")),
            (c.STARLIGHT_NORMAL, N_("Normal")),
            (c.STARLIGHT_SLOW, N_("Lenta")),
        ],
    },
    "wave": {
        "attr": "wave_dir",
        "default": c.WAVE_LEFT,
        "label": N_("Direção"),
        "options": [
            (c.WAVE_LEFT, N_("Esquerda")),
            (c.WAVE_RIGHT, N_("Direita")),
        ],
    },
    "wheel": {
        "attr": "wave_dir",
        "default": c.WHEEL_LEFT,
        "label": N_("Direção"),
        "options": [
            (c.WHEEL_LEFT, N_("Esquerda")),
            (c.WHEEL_RIGHT, N_("Direita")),
        ],
    },
}
EFFECT_EXTRA_PARAM["starlight_dual"] = EFFECT_EXTRA_PARAM["starlight_single"]
EFFECT_EXTRA_PARAM["starlight_random"] = EFFECT_EXTRA_PARAM["starlight_single"]

# Fallback default extra-args for presets saved before this feature existed.
EFFECT_EXTRA_ARGS: dict[str, list] = {
    name: [spec["default"]] for name, spec in EFFECT_EXTRA_PARAM.items()
}

# 'blinking' has a capability key but no RazerFX.blinking() method - excluded.
# "none" is always last (deliberate, consistent ordering across devices).
MAIN_EFFECT_CANDIDATES = [
    "static", "spectrum", "wave", "wheel",
    "breath_single", "breath_dual", "breath_triple", "breath_random",
    "reactive", "ripple", "ripple_random",
    "starlight_single", "starlight_dual", "starlight_random",
    "none",
]

# Number of color slots each main effect takes (0 = no color picker shown).
MAIN_EFFECT_COLOR_SLOTS = {
    "static": 1, "reactive": 1, "ripple": 1,
    "breath_single": 1, "breath_dual": 2, "breath_triple": 3,
    "starlight_single": 1, "starlight_dual": 2,
    "spectrum": 0, "wave": 0, "wheel": 0,
    "breath_random": 0, "ripple_random": 0, "starlight_random": 0, "none": 0,
}

ZONE_EFFECT_CANDIDATES = [
    "static", "spectrum", "wave", "reactive", "on",
    "breath_single", "breath_dual", "breath_random", "breath_mono",
    "blinking", "pulsate",
    "none",
]

ZONE_EFFECT_COLOR_SLOTS = {
    "static": 1, "reactive": 1, "breath_single": 1, "breath_dual": 2,
    "blinking": 1, "pulsate": 1,
    "spectrum": 0, "wave": 0, "none": 0, "on": 0,
    "breath_random": 0, "breath_mono": 0,
}

ZONE_LABELS = {
    "logo": N_("Logo"),
    "scroll": N_("Roda de rolagem"),
    "left": N_("Lado esquerdo"),
    "right": N_("Lado direito"),
    "charging": N_("Carregando"),
    "fast_charging": N_("Carregamento rápido"),
    "fully_charged": N_("Totalmente carregada"),
    "backlight": N_("Luz de fundo"),
}

FALLBACK_POLL_RATES = [125, 500, 1000]

ZONE_PROPERTY_NAMES = {
    "logo": "logo",
    "scroll": "scroll_wheel",
    "left": "left",
    "right": "right",
    "charging": "charging",
    "fast_charging": "fast_charging",
    "fully_charged": "fully_charged",
    "backlight": "backlight",
}


@dataclass(frozen=True)
class LightSurface:
    """A controllable light source: either the device-wide `fx` or one LED zone."""

    key: str
    label: str
    surface: RazerFX | SingleLed
    supported_effects: list[str]
    effect_color_slots: dict[str, int]
    supports_brightness: bool
    brightness_source: str | None  # 'device' or 'zone'


@dataclass(frozen=True)
class DeviceCapabilities:
    device: RazerDevice

    supports_battery: bool
    supports_idle_time: bool
    supports_low_battery_threshold: bool

    supports_dpi: bool
    dpi_is_discrete: bool
    available_dpi: list[int]
    max_dpi: int | None
    supports_dpi_stages: bool
    supports_independent_axes: bool

    supports_poll_rate: bool
    supported_poll_rates: list[int]

    primary_light: LightSurface | None
    zones: list[LightSurface]

    supports_profiles: bool = False


def _probe_main_light(device: RazerDevice) -> LightSurface | None:
    fx = device.fx
    effects = [name for name in MAIN_EFFECT_CANDIDATES if fx.has(name)]
    if not effects:
        return None
    return LightSurface(
        key="main",
        label=_("Iluminação"),
        surface=fx,
        supported_effects=effects,
        effect_color_slots={name: MAIN_EFFECT_COLOR_SLOTS[name] for name in effects},
        supports_brightness=device.has("brightness"),
        brightness_source="device" if device.has("brightness") else None,
    )


def _probe_zones(device: RazerDevice) -> list[LightSurface]:
    misc = device.fx.misc
    zones: list[LightSurface] = []
    for zone_key, prop_name in ZONE_PROPERTY_NAMES.items():
        led = getattr(misc, prop_name)
        if led is None:
            continue
        effects = [
            name for name in ZONE_EFFECT_CANDIDATES
            if device.capabilities.get(f"lighting_{zone_key}_{name}", False)
        ]
        supports_brightness = device.capabilities.get(f"lighting_{zone_key}_brightness", False)
        zones.append(LightSurface(
            key=zone_key,
            label=_(ZONE_LABELS[zone_key]),
            surface=led,
            supported_effects=effects,
            effect_color_slots={name: ZONE_EFFECT_COLOR_SLOTS[name] for name in effects},
            supports_brightness=supports_brightness,
            brightness_source="zone" if supports_brightness else None,
        ))
    return zones


def _pick_primary_light(main: LightSurface | None, zones: list[LightSurface]) -> LightSurface | None:
    if main is not None:
        return main
    if not zones:
        return None
    for zone in zones:
        if zone.key == "logo":
            return zone
    return zones[0]


def from_device(device: RazerDevice) -> DeviceCapabilities:
    """Build a DeviceCapabilities snapshot. Call once per device selection."""
    supports_dpi = device.has("dpi")
    dpi_is_discrete = device.has("available_dpi")
    supports_poll_rate = device.has("poll_rate")
    if supports_poll_rate:
        poll_rates = (
            list(device.supported_poll_rates)
            if device.has("supported_poll_rates")
            else list(FALLBACK_POLL_RATES)
        )
    else:
        poll_rates = []

    main_light = _probe_main_light(device)
    zones = _probe_zones(device)

    return DeviceCapabilities(
        device=device,
        supports_battery=device.has("battery"),
        supports_idle_time=device.has("battery") and device.has("idle_time"),
        supports_low_battery_threshold=device.has("battery") and device.has("low_battery_threshold"),
        supports_dpi=supports_dpi,
        dpi_is_discrete=dpi_is_discrete,
        available_dpi=list(device.available_dpi) if supports_dpi and dpi_is_discrete else [],
        max_dpi=device.max_dpi if supports_dpi else None,
        supports_dpi_stages=device.has("dpi_stages"),
        supports_independent_axes=supports_dpi and not dpi_is_discrete,
        supports_poll_rate=supports_poll_rate,
        supported_poll_rates=poll_rates,
        primary_light=_pick_primary_light(main_light, zones),
        zones=zones,
    )


def fetch_live_snapshot(caps: DeviceCapabilities) -> dict:
    """Read every 'current value' widgets need, in one pass on a background
    thread - D-Bus reads on this daemon can take 5+ seconds intermittently,
    so widgets must never read `caps.device`/`zone.surface` live."""
    device = caps.device
    snap: dict = {}

    if caps.supports_dpi:
        try:
            snap["dpi"] = device.dpi
        except Exception:
            logger.exception("fetch_live_snapshot: dpi failed")
    if caps.supports_dpi_stages:
        try:
            snap["dpi_stages"] = device.dpi_stages
        except Exception:
            logger.exception("fetch_live_snapshot: dpi_stages failed")
    if caps.supports_poll_rate:
        try:
            snap["poll_rate"] = device.poll_rate
        except Exception:
            logger.exception("fetch_live_snapshot: poll_rate failed")

    if caps.supports_battery:
        try:
            snap["battery_level"] = device.battery_level
            snap["is_charging"] = device.is_charging
        except Exception:
            logger.exception("fetch_live_snapshot: battery failed")
        if caps.supports_idle_time:
            try:
                snap["idle_time"] = device.get_idle_time()
            except Exception:
                logger.exception("fetch_live_snapshot: idle_time failed")
        if caps.supports_low_battery_threshold:
            try:
                snap["low_battery_threshold"] = device.get_low_battery_threshold()
            except Exception:
                logger.exception("fetch_live_snapshot: low_battery_threshold failed")

    if caps.primary_light is not None:
        zone = caps.primary_light
        try:
            effect = zone.surface.effect
            slots = zone.effect_color_slots.get(effect, 0)
            snap["primary_effect"] = effect
            snap["primary_colors"] = bytes(zone.surface.colors) if slots else b""
        except Exception:
            logger.exception("fetch_live_snapshot: primary effect/colors failed")
        else:
            spec = EFFECT_EXTRA_PARAM.get(effect)
            if spec is not None:
                try:
                    raw = getattr(zone.surface, spec["attr"])
                    if raw in (value for value, _label in spec["options"]):
                        snap["primary_extra_arg"] = raw
                except Exception:
                    logger.exception("fetch_live_snapshot: primary extra arg failed")
        if zone.supports_brightness:
            try:
                if zone.brightness_source == "device":
                    snap["primary_brightness"] = device.brightness
                elif zone.brightness_source == "zone":
                    snap["primary_brightness"] = zone.surface.brightness
            except Exception:
                logger.exception("fetch_live_snapshot: primary brightness failed")

    return snap
