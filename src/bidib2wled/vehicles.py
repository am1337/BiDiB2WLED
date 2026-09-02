"""Pixel animation for vehicles: indicators, strobes, beacons."""

from __future__ import annotations

import hashlib

from bidib2wled.config import VehicleConfig
from bidib2wled.pixels import clear_components, expand_anteil, set_components
from bidib2wled.wled import rgb_from_hex

# Per-vehicle blink-frequency offset so several models do not flash in lockstep.
_PERIOD_SPREAD = 0.22


def rundum_steps(leds: list[int], anteil: str, schritte: str = "auto") -> list[tuple[int, tuple[str, ...]]]:
    """Steps of a beacon / rotating light.

    `leds`: one step per pixel (all selected RGB components together).
    `channels`: one step per color channel, e.g. one WS2811 as 3 LEDs (R→G→B).
    `auto`: with one LED and several components like `channels`, otherwise like `leds`.
    """
    components = expand_anteil(anteil)
    walk_channels = schritte in ("channels", "kanaele") or (
        schritte != "leds" and len(leds) == 1 and len(components) > 1
    )
    if walk_channels:
        return [(led, (component,)) for led in leds for component in components]
    return [(led, components) for led in leds]


def vehicle_timing(object_id: str, base_period: float) -> tuple[float, float]:
    """Deterministic period and phase per object id (vehicles are not synchronized)."""
    digest = hashlib.sha256(object_id.encode("utf-8")).digest()
    u1 = int.from_bytes(digest[0:2], "big") / 65535.0
    u2 = int.from_bytes(digest[2:4], "big") / 65535.0
    period = max(0.2, float(base_period) * (1.0 - _PERIOD_SPREAD + 2.0 * _PERIOD_SPREAD * u1))
    phase = u2 * period
    return period, phase


def pattern_active(art: str, elapsed: float, blink_period: float) -> bool:
    if art in ("continuous", "dauer"):
        return True
    period = max(0.2, blink_period)
    if art == "blinker":
        return (elapsed % period) < (period * 0.5)
    if art in ("strobe", "blitz"):
        cycle = max(0.16, period * 0.48)
        return (elapsed % cycle) < (cycle * 0.2)
    if art in ("double_strobe", "doppelblitz"):
        cycle = max(0.45, period * 1.15)
        pos = elapsed % cycle
        flash = 0.07
        gap = 0.09
        return (pos < flash) or (flash + gap <= pos < flash + gap + flash)
    return True


def rundum_index(elapsed: float, step_s: float, count: int) -> int:
    if count <= 0:
        return 0
    step = step_s if step_s > 0 else 0.12
    return int(elapsed / step) % count


def vehicle_has_animation(vehicle: VehicleConfig, aspect: int) -> bool:
    mode = vehicle.resolved_modes().get(aspect)
    if not mode:
        return False
    for name in mode.channels:
        channel = vehicle.channels.get(name)
        if channel and channel.type != "continuous":
            return True
    return False


def apply_vehicle_to_pixels(
    pixels: list[tuple[int, int, int]],
    vehicle: VehicleConfig,
    object_id: str,
    aspect: int,
    now: float,
) -> set[int]:
    """Write the current vehicle state into `pixels`. Returns affected indices."""
    touched: set[int] = set()
    owned: dict[int, set[str]] = {}
    for channel in vehicle.channels.values():
        components = expand_anteil(channel.channel)
        for led in channel.leds:
            owned.setdefault(led, set()).update(components)
            touched.add(led)

    def ensure(index: int) -> None:
        while len(pixels) <= index:
            pixels.append((0, 0, 0))

    for led, components in owned.items():
        ensure(led)
        pixels[led] = clear_components(pixels[led], components)

    mode = vehicle.resolved_modes().get(aspect)
    active = list(mode.channels) if mode else []
    if not active:
        return touched

    period, phase = vehicle_timing(object_id, vehicle.blink_period_s)
    elapsed = now + phase
    step_s = vehicle.rundum_step_s

    for name in active:
        channel = vehicle.channels.get(name)
        if channel is None:
            continue
        color = rgb_from_hex(channel.color, channel.brightness)
        if channel.type == "beacon":
            steps = rundum_steps(channel.leds, channel.channel, channel.steps)
            if not steps:
                continue
            led, components = steps[rundum_index(elapsed, step_s, len(steps))]
            ensure(led)
            pixels[led] = set_components(pixels[led], components, color)
            continue
        if channel.type in ("blinker", "strobe", "double_strobe") and not pattern_active(
            channel.type, elapsed, period
        ):
            continue
        components = expand_anteil(channel.channel)
        for led in channel.leds:
            ensure(led)
            pixels[led] = set_components(pixels[led], components, color)
    return touched
