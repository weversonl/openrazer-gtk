"""Local presets: named snapshots of DPI/lighting/poll-rate settings. Not device profiles - OpenRazer has no on-board profile storage API."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from gi.repository import GLib

from razer_gtk.backend.device_adapter import EFFECT_EXTRA_ARGS, EFFECT_EXTRA_PARAM


def _presets_path() -> Path:
    config_dir = Path(GLib.get_user_config_dir()) / "razer-gtk"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "presets.json"


@dataclass
class LightingSnapshot:
    surface_key: str  # 'main' or a zone key like 'logo'
    effect: str
    colors: list[tuple[int, int, int]] = field(default_factory=list)
    extra_args: list = field(default_factory=list)
    brightness: float | None = None


@dataclass
class Preset:
    name: str
    dpi: tuple[int, int] | None = None
    # Full stage table (active_index, [(x, y), ...]) for stage-based mice -
    # a preset must restore the whole table, not just the active value,
    # otherwise switching presets doesn't change which DPIs the physical
    # stage button cycles through.
    dpi_stages: tuple[int, list[tuple[int, int]]] | None = None
    poll_rate: int | None = None
    lighting: list[LightingSnapshot] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "Preset":
        lighting = [LightingSnapshot(**snap) for snap in data.get("lighting", [])]
        dpi = tuple(data["dpi"]) if data.get("dpi") else None
        raw_stages = data.get("dpi_stages")
        dpi_stages = (raw_stages[0], [tuple(s) for s in raw_stages[1]]) if raw_stages else None
        return Preset(
            name=data["name"],
            dpi=dpi,
            dpi_stages=dpi_stages,
            poll_rate=data.get("poll_rate"),
            lighting=lighting,
        )


def load_presets(serial: str) -> list[Preset]:
    path = _presets_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    return [Preset.from_dict(p) for p in data.get(serial, [])]


def save_presets(serial: str, presets: list[Preset]) -> None:
    path = _presets_path()
    try:
        data = json.loads(path.read_text()) if path.exists() else {}
    except (json.JSONDecodeError, OSError):
        data = {}
    data[serial] = [p.to_dict() for p in presets]
    path.write_text(json.dumps(data, indent=2))


def capture_preset(caps, name: str) -> Preset:
    """Snapshot the device's current DPI/poll-rate/lighting into a new Preset."""
    device = caps.device
    dpi = device.dpi if caps.supports_dpi else None
    dpi_stages = device.dpi_stages if caps.supports_dpi_stages else None
    poll_rate = device.poll_rate if caps.supports_poll_rate else None

    surfaces = {caps.primary_light.key: caps.primary_light} if caps.primary_light else {}
    surfaces.update({zone.key: zone for zone in caps.zones})

    lighting: list[LightingSnapshot] = []
    for surface in surfaces.values():
        try:
            effect = surface.surface.effect
        except Exception:
            continue
        if effect not in surface.supported_effects:
            continue
        slots = surface.effect_color_slots.get(effect, 0)
        colors: list[tuple[int, int, int]] = []
        if slots:
            try:
                raw = surface.surface.colors
                for i in range(slots):
                    offset = i * 3
                    colors.append((raw[offset], raw[offset + 1], raw[offset + 2]))
            except Exception:
                colors = []
        brightness = None
        if surface.supports_brightness:
            try:
                brightness = device.brightness if surface.brightness_source == "device" else surface.surface.brightness
            except Exception:
                brightness = None
        extra_args: list = []
        spec = EFFECT_EXTRA_PARAM.get(effect)
        if spec is not None:
            try:
                extra_args = [getattr(surface.surface, spec["attr"])]
            except Exception:
                extra_args = [spec["default"]]

        lighting.append(LightingSnapshot(
            surface_key=surface.key,
            effect=effect,
            colors=colors,
            extra_args=extra_args,
            brightness=brightness,
        ))

    return Preset(name=name, dpi=dpi, dpi_stages=dpi_stages, poll_rate=poll_rate, lighting=lighting)


def is_preset_active(caps, preset: Preset, snapshot: dict) -> bool:
    """Whether `preset` matches the device's current state, per `snapshot`."""
    if preset.dpi is not None:
        if not caps.supports_dpi or tuple(snapshot.get("dpi", ())) != tuple(preset.dpi):
            return False

    if preset.dpi_stages is not None:
        actual = snapshot.get("dpi_stages")
        if actual is None:
            return False
        actual_active, actual_stages = actual
        expected_active, expected_stages = preset.dpi_stages
        if actual_active != expected_active:
            return False
        if [tuple(s) for s in actual_stages] != [tuple(s) for s in expected_stages]:
            return False

    if preset.poll_rate is not None:
        if not caps.supports_poll_rate or snapshot.get("poll_rate") != preset.poll_rate:
            return False

    if caps.primary_light is not None:
        primary_snapshot = next(
            (item for item in preset.lighting if item.surface_key == caps.primary_light.key), None
        )
        if primary_snapshot is not None:
            if snapshot.get("primary_effect") != primary_snapshot.effect:
                return False

            raw = snapshot.get("primary_colors", b"")
            actual_colors = [tuple(raw[i:i + 3]) for i in range(0, len(raw) - len(raw) % 3, 3)]
            expected_colors = [tuple(color) for color in primary_snapshot.colors]
            if actual_colors != expected_colors:
                return False

            if primary_snapshot.brightness is not None:
                actual_brightness = snapshot.get("primary_brightness")
                if actual_brightness is None or abs(actual_brightness - primary_snapshot.brightness) > 1.0:
                    return False

    return True


def apply_preset(caps, preset: Preset, perform_write) -> list[str]:
    """Replay a preset's stored values through the same setters the UI uses. Returns any write errors."""
    device = caps.device
    errors: list[str] = []

    def _write(fn) -> None:
        error = perform_write(fn)
        if error is not None:
            errors.append(error)

    if preset.dpi is not None and caps.supports_dpi:
        if caps.supports_dpi_stages and preset.dpi_stages is not None:
            # Stage-based mice keep two separate registers: the stage table
            # (`dpi_stages`, what the physical DPI button cycles through)
            # and the currently active DPI value (`dpi`). A preset must
            # restore the whole table - not just the active value - or
            # switching presets leaves the button cycling through whichever
            # table was configured last. Mirror dpi_card's stage-selection
            # write: set both together, same as picking a stage would.
            active_index, stages = preset.dpi_stages
            target = tuple(preset.dpi)

            def _write_stage(active_index=active_index, stages=stages, target=target) -> None:
                device.dpi_stages = (active_index, stages)
                device.dpi = target

            _write(_write_stage)
        elif caps.supports_dpi_stages:
            # Older preset saved before dpi_stages was captured - it has no
            # table to restore. Best effort: if the target happens to match
            # an existing stage, just switch to it; otherwise only write the
            # raw dpi value and leave the stage table untouched. Patching a
            # table slot here would silently corrupt whatever *other*
            # preset's table happens to be live on the device right now -
            # worse than a stale reading. The real fix is recreating this
            # preset so it has its own captured table.
            target = tuple(preset.dpi)

            def _write_stage_fallback(target=target) -> None:
                _active_stage, stages = device.dpi_stages
                try:
                    new_active = next(i for i, s in enumerate(stages, start=1) if tuple(s) == target)
                except StopIteration:
                    device.dpi = target
                    return
                device.dpi_stages = (new_active, stages)
                device.dpi = target

            _write(_write_stage_fallback)
        else:
            _write(lambda: setattr(device, "dpi", preset.dpi))

    if preset.poll_rate is not None and caps.supports_poll_rate:
        _write(lambda: setattr(device, "poll_rate", preset.poll_rate))

    surfaces = {caps.primary_light.key: caps.primary_light} if caps.primary_light else {}
    surfaces.update({zone.key: zone for zone in caps.zones})

    for snapshot in preset.lighting:
        surface = surfaces.get(snapshot.surface_key)
        if surface is None or snapshot.effect not in surface.supported_effects:
            continue
        effect_fn = getattr(surface.surface, snapshot.effect, None)
        if effect_fn is None:
            continue
        color_args = [component for triple in snapshot.colors for component in triple]
        extra_args = snapshot.extra_args or EFFECT_EXTRA_ARGS.get(snapshot.effect, [])
        args = [*color_args, *extra_args]

        def _apply(effect_fn=effect_fn, args=args):
            effect_fn(*args)

        _write(_apply)

        if snapshot.brightness is not None and surface.supports_brightness:
            if surface.brightness_source == "device":
                _write(lambda: setattr(device, "brightness", snapshot.brightness))
            elif surface.brightness_source == "zone":
                _write(lambda: setattr(surface.surface, "brightness", snapshot.brightness))

    return errors
