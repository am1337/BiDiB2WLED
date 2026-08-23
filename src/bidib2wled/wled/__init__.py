"""WLED JSON-API Client."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import aiohttp

from bidib2wled.config import normalize_mac

__all__ = [
    "ActiveEffect",
    "LedOutput",
    "WledDevice",
    "WledInfo",
    "WledPool",
    "contiguous_ranges",
    "hex_from_rgb",
    "normalize_mac",
    "outputs_from_cfg",
    "rgb_from_hex",
    "warnings_from_cfg",
]

SIMULATED_EFFECTS = [
    "Solid",
    "Blink",
    "Breathe",
    "Wipe",
    "Fade",
    "Scan",
    "Theater",
    "Rainbow",
    "Rainbow Cycle",
    "Chase",
    "Fire 2012",
    "Twinkle",
    "Colortwinkle",
    "Lava",
    "Meteor",
    "Candle",
    "Fireworks",
    "Rain",
    "Noise Pal",
    "Dynamic",
    "Colorwaves",
    "Pride 2015",
    "Heartbeat",
    "Pacifica",
    "Ripple",
    "TV Simulator",
    "Aurora",
]
SIMULATED_PALETTES = [
    "Default",
    "Random Cycle",
    "Primary Color",
    "Based on Primary",
    "Set Colors",
    "Party",
    "Cloud",
    "Lava",
    "Ocean",
    "Forest",
    "Rainbow",
    "Rainbow Bands",
    "Sunset",
    "Rivendell",
    "Breeze",
    "Red & Blue",
    "Analogous",
    "Splash",
    "Pastel",
]

log = logging.getLogger(__name__)


@dataclass
class LedOutput:
    index: int
    start: int
    length: int
    pin: int | None = None

    def to_dict(self) -> dict:
        label = f"Ausgang {self.index + 1}"
        extras = []
        if self.pin is not None:
            extras.append(f"GPIO {self.pin}")
        extras.append(f"{self.length} LEDs")
        extras.append(f"Index {self.start}–{self.start + self.length - 1}")
        return {
            "id": self.index,
            "start": self.start,
            "len": self.length,
            "pin": self.pin,
            "label": f"{label} ({', '.join(extras)})",
        }


@dataclass
class ActiveEffect:
    object_id: str
    leds: tuple[int, ...]
    fx: int
    pal: int = 0
    sx: int = 128
    ix: int = 128
    color: tuple[int, int, int] = (255, 255, 255)
    bri: int = 255


@dataclass
class WledInfo:
    name: str
    mac: str
    ip: str
    port: int = 80
    led_count: int = 0
    version: str = ""
    mdns: str | None = None
    max_segments: int = 16
    reachable: bool = False
    outputs: list[LedOutput] = field(default_factory=list)
    effects: list[str] = field(default_factory=list)
    palettes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"http://{self.ip}:{self.port}/"


def rgb_from_hex(color: str, brightness: int = 255) -> tuple[int, int, int]:
    color = color.strip().lstrip("#")
    r = int(color[0:2], 16)
    g = int(color[2:4], 16)
    b = int(color[4:6], 16)
    scale = max(0, min(255, brightness)) / 255.0
    return (int(r * scale), int(g * scale), int(b * scale))


def hex_from_rgb(rgb: tuple[int, int, int]) -> str:
    return f"{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def outputs_from_cfg(cfg: dict, led_count: int = 0) -> list[LedOutput]:
    ins = ((cfg.get("hw") or {}).get("led") or {}).get("ins") or []
    outputs: list[LedOutput] = []
    for item in ins:
        if item.get("en") is False:
            continue
        length = int(item.get("len") or 0)
        if length <= 0:
            continue
        start = int(item.get("start") or 0)
        pin = item.get("pin")
        pin_n = pin[0] if isinstance(pin, list) and pin else (int(pin) if pin is not None else None)
        outputs.append(LedOutput(index=len(outputs), start=start, length=length, pin=pin_n))
    if outputs:
        return outputs
    return [LedOutput(0, 0, led_count or 1)]


def _truthy(value) -> bool:
    return value is True or value == 1 or str(value).lower() == "true"


def warnings_from_cfg(cfg: dict) -> list[str]:
    """Unpassende WLED-Einstellungen, die die Bridge überschreiben können."""
    warnings: list[str] = []
    iface = cfg.get("if") or {}
    sync = iface.get("sync") if isinstance(iface.get("sync"), dict) else cfg.get("sync")
    if not isinstance(sync, dict):
        sync = {}
    recv = sync.get("recv") if isinstance(sync.get("recv"), dict) else {}
    send = sync.get("send") if isinstance(sync.get("send"), dict) else {}
    if _truthy(recv.get("en")):
        warnings.append("UDP-Sync-Empfang ist aktiv. Andere WLED-Geräte können die LEDs überschreiben.")
    if _truthy(send.get("en")):
        warnings.append("UDP-Sync-Senden ist aktiv. Dieser Controller steuert andere Geräte mit.")
    live = iface.get("live") if isinstance(iface.get("live"), dict) else {}
    dmx = live.get("dmx") if isinstance(live.get("dmx"), dict) else {}
    mode = dmx.get("mode")
    if mode not in (None, 0, "0", False):
        warnings.append("E1.31/DMX-Empfang ist aktiv. Externe Quellen können die LEDs überschreiben.")
    return warnings


def contiguous_ranges(leds: list[int] | tuple[int, ...]) -> list[tuple[int, int]]:
    """Sortierte LED-Indizes → halboffene Bereiche (start, stop) für WLED-Segmente."""
    ordered = sorted({int(led) for led in leds})
    if not ordered:
        return []
    ranges: list[tuple[int, int]] = []
    start = prev = ordered[0]
    for led in ordered[1:]:
        if led == prev + 1:
            prev = led
            continue
        ranges.append((start, prev + 1))
        start = prev = led
    ranges.append((start, prev + 1))
    return ranges


@dataclass
class WledDevice:
    info: WledInfo
    pixels: list[tuple[int, int, int]] = field(default_factory=list)
    session: aiohttp.ClientSession | None = None
    simulate: bool = False
    active_effects: dict[str, ActiveEffect] = field(default_factory=dict)
    posted_overlay_ids: list[int] = field(default_factory=list)

    def ensure_size(self, count: int) -> None:
        if count <= 0:
            count = max(len(self.pixels), 1)
        if len(self.pixels) < count:
            self.pixels.extend([(0, 0, 0)] * (count - len(self.pixels)))
        elif len(self.pixels) > count:
            self.pixels = self.pixels[:count]

    @property
    def base_url(self) -> str:
        return f"http://{self.info.ip}:{self.info.port}"

    async def fetch_info(self) -> WledInfo:
        if self.simulate:
            self.info.reachable = True
            if not self.info.effects:
                self.info.effects = list(SIMULATED_EFFECTS)
            if not self.info.palettes:
                self.info.palettes = list(SIMULATED_PALETTES)
            await self._fetch_outputs()
            self.ensure_size(self.info.led_count or 1)
            return self.info
        assert self.session is not None
        url = f"{self.base_url}/json/info"
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=4)) as response:
                response.raise_for_status()
                data = await response.json()
            leds = data.get("leds") or {}
            count = int(leds.get("count") or 0)
            mac = normalize_mac(str(data.get("mac") or self.info.mac))
            self.info.mac = mac
            self.info.name = str(data.get("name") or self.info.name)
            self.info.led_count = count
            self.info.version = str(data.get("ver") or "")
            self.info.max_segments = int(leds.get("maxseg") or 16)
            self.info.reachable = True
            await self._fetch_outputs()
            await self._fetch_effects()
            self.ensure_size(count or len(self.pixels) or 1)
            return self.info
        except Exception:
            self.info.reachable = False
            raise

    async def _fetch_outputs(self) -> None:
        if self.simulate:
            if not self.info.outputs:
                total = self.info.led_count or 80
                mid = max(1, total // 2)
                self.info.outputs = [
                    LedOutput(0, 0, mid, pin=16),
                    LedOutput(1, mid, total - mid, pin=2),
                ]
            return
        assert self.session is not None
        try:
            async with self.session.get(
                f"{self.base_url}/json/cfg", timeout=aiohttp.ClientTimeout(total=4)
            ) as response:
                response.raise_for_status()
                cfg = await response.json()
        except Exception as exc:
            log.info("WLED %s: Ausgänge nicht lesbar (%s), ein Ausgang", self.info.ip, exc)
            self._fallback_outputs()
            return
        self.info.outputs = outputs_from_cfg(cfg, self.info.led_count)
        self.info.warnings = warnings_from_cfg(cfg)

    async def _fetch_effects(self) -> None:
        if self.simulate:
            return
        assert self.session is not None
        timeout = aiohttp.ClientTimeout(total=4)
        try:
            async with self.session.get(f"{self.base_url}/json/eff", timeout=timeout) as response:
                response.raise_for_status()
                data = await response.json(content_type=None)
            if isinstance(data, list):
                self.info.effects = [str(name) for name in data]
        except Exception as exc:
            log.info("WLED %s: Effekte nicht lesbar (%s)", self.info.ip, exc)
        try:
            async with self.session.get(f"{self.base_url}/json/pal", timeout=timeout) as response:
                response.raise_for_status()
                data = await response.json(content_type=None)
            if isinstance(data, list):
                self.info.palettes = [str(name) for name in data]
        except Exception as exc:
            log.info("WLED %s: Paletten nicht lesbar (%s)", self.info.ip, exc)

    def _fallback_outputs(self) -> None:
        total = self.info.led_count or len(self.pixels) or 1
        self.info.outputs = [LedOutput(0, 0, total)]

    def global_index(self, output: int, local_index: int) -> int:
        if not self.info.outputs:
            self._fallback_outputs()
        if output < 0 or output >= len(self.info.outputs):
            raise ValueError(f"Ausgang {output} existiert nicht")
        bus = self.info.outputs[output]
        if local_index < 0 or local_index >= bus.length:
            raise ValueError(f"LED {local_index} liegt nicht auf Ausgang {output + 1}")
        return bus.start + local_index

    async def apply_pixels(self, updates: dict[int, tuple[int, int, int]]) -> None:
        if not updates:
            return
        if not self.simulate and not self.info.outputs:
            await self._fetch_outputs()
        max_idx = max(updates)
        total = max(max_idx + 1, self.info.led_count, 1)
        self.ensure_size(total)
        for idx, color in updates.items():
            if 0 <= idx < len(self.pixels):
                self.pixels[idx] = color
        if self.simulate:
            log.info("simulate %s pixels %s", self.info.name, updates)
            self.state_body(updates)
            return
        await self._post_state(self.state_body(updates))

    async def apply_effect(self, effect: ActiveEffect) -> None:
        self.active_effects[effect.object_id] = effect
        if self.simulate:
            log.info("simulate %s effect %s fx=%s", self.info.name, effect.object_id, effect.fx)
            self.state_body()
            return
        await self._post_state(self.state_body())

    async def clear_effect(self, object_id: str) -> None:
        self.active_effects.pop(object_id, None)

    def state_body(self, updates: dict[int, tuple[int, int, int]] | None = None) -> dict:
        updates = dict(updates or {})
        if updates:
            max_idx = max(updates)
            total = max(max_idx + 1, self.info.led_count, len(self.pixels), 1)
        else:
            total = max(self.info.led_count, len(self.pixels), 1)
        self.ensure_size(total)
        for idx, color in updates.items():
            if 0 <= idx < len(self.pixels):
                self.pixels[idx] = color
        outputs = self.info.outputs or [LedOutput(0, 0, total)]
        segs: list[dict] = []
        for out in outputs:
            start = out.start
            length = max(out.length, 1)
            stop = start + length
            # Hex-Strings, damit WLED Schwarz nicht als LED-Bereich 0–0 liest.
            colors = [
                hex_from_rgb(self.pixels[idx] if idx < len(self.pixels) else (0, 0, 0))
                for idx in range(start, stop)
            ]
            segs.append(
                {
                    "id": out.index,
                    "start": start,
                    "stop": stop,
                    "frz": True,
                    "i": colors,
                }
            )
        next_id = max((out.index for out in outputs), default=-1) + 1
        maxseg = self.info.max_segments or 16
        overlay_ids: list[int] = []
        for effect in self.active_effects.values():
            r, g, b = effect.color
            for start, stop in contiguous_ranges(effect.leds):
                if next_id >= maxseg:
                    log.warning(
                        "WLED %s: max. %s Segmente erreicht, Effekt %s unvollständig",
                        self.info.name,
                        maxseg,
                        effect.object_id,
                    )
                    break
                segs.append(
                    {
                        "id": next_id,
                        "start": start,
                        "stop": stop,
                        "grp": 0,
                        "spc": 0,
                        "of": 0,
                        "on": True,
                        "frz": False,
                        "fx": int(effect.fx),
                        "sx": int(effect.sx),
                        "ix": int(effect.ix),
                        "pal": int(effect.pal),
                        "col": [[r, g, b], [0, 0, 0], [0, 0, 0]],
                        "bri": int(effect.bri),
                        "sel": False,
                    }
                )
                overlay_ids.append(next_id)
                next_id += 1
        # Overlay-Segmente, die nicht mehr aktiv sind, müssen explizit
        # gelöscht werden. Sonst läuft der WLED-Effekt weiter. stop:0 nur
        # für IDs oberhalb der Hardware-Ausgänge – nie für Bus-Segmente.
        stale = [seg_id for seg_id in self.posted_overlay_ids if seg_id not in overlay_ids]
        hardware_ids = {out.index for out in outputs}
        for seg_id in stale:
            if seg_id in hardware_ids:
                continue
            segs.append({"id": seg_id, "on": False, "fx": 0, "frz": True, "stop": 0})
        self.posted_overlay_ids = overlay_ids
        body: dict = {"tt": 0, "seg": segs}
        if any(pixel != (0, 0, 0) for pixel in self.pixels) or self.active_effects:
            body["on"] = True
        return body

    async def identify(self, index: int, color: str = "FFFFFF") -> None:
        count = self.info.led_count or len(self.pixels) or (index + 1)
        self.ensure_size(count)
        updates = {i: (0, 0, 0) for i in range(count)}
        updates[index] = rgb_from_hex(color, 255)
        await self.apply_pixels(updates)

    async def blink(self, index: int, times: int = 4, interval: float = 0.25) -> None:
        on = rgb_from_hex("FFFFFF")
        off = (0, 0, 0)
        for _ in range(times):
            await self.apply_pixels({index: on})
            await asyncio.sleep(interval)
            await self.apply_pixels({index: off})
            await asyncio.sleep(interval)

    async def _post_state(self, body: dict) -> None:
        assert self.session is not None
        url = f"{self.base_url}/json/state"
        try:
            async with self.session.post(
                url, json=body, timeout=aiohttp.ClientTimeout(total=4)
            ) as response:
                response.raise_for_status()
            self.info.reachable = True
        except Exception as exc:
            self.info.reachable = False
            log.warning("WLED %s nicht erreichbar: %s", self.info.ip, exc)
            raise


class WledPool:
    def __init__(self, simulate: bool = False) -> None:
        self.simulate = simulate
        self.session: aiohttp.ClientSession | None = None
        self.devices: dict[str, WledDevice] = {}  # key = logical name or mac

    async def start(self) -> None:
        self.session = aiohttp.ClientSession()

    async def close(self) -> None:
        if self.session:
            await self.session.close()
            self.session = None

    def get(self, name: str) -> WledDevice | None:
        return self.devices.get(name)

    def by_mac(self, mac: str) -> WledDevice | None:
        mac = normalize_mac(mac)
        for device in self.devices.values():
            if device.info.mac == mac:
                return device
        return None

    def bind(
        self,
        name: str,
        *,
        ip: str,
        port: int = 80,
        mac: str = "",
        leds: int = 0,
        mdns: str | None = None,
        wled_name: str = "",
    ) -> WledDevice:
        info = WledInfo(
            name=wled_name or name,
            mac=normalize_mac(mac) if mac else "",
            ip=ip,
            port=port,
            led_count=leds,
            mdns=mdns,
        )
        existing = self.devices.get(name)
        device = WledDevice(info=info, session=self.session, simulate=self.simulate)
        if existing:
            if existing.pixels:
                device.pixels = list(existing.pixels)
            if existing.info.outputs:
                device.info.outputs = list(existing.info.outputs)
            if existing.info.led_count:
                device.info.led_count = existing.info.led_count
            if existing.info.max_segments:
                device.info.max_segments = existing.info.max_segments
            if existing.info.effects:
                device.info.effects = list(existing.info.effects)
            if existing.info.palettes:
                device.info.palettes = list(existing.info.palettes)
            if existing.info.warnings:
                device.info.warnings = list(existing.info.warnings)
            if existing.active_effects:
                device.active_effects = dict(existing.active_effects)
            if existing.posted_overlay_ids:
                device.posted_overlay_ids = list(existing.posted_overlay_ids)
            device.info.reachable = existing.info.reachable
        device.ensure_size(max(leds or 1, len(device.pixels), device.info.led_count or 0))
        self.devices[name] = device
        return device

    async def probe(self, ip: str, port: int = 80) -> WledInfo | None:
        if self.simulate:
            return WledInfo(name=f"sim-{ip}", mac="00:00:00:00:00:00", ip=ip, port=port, led_count=80)
        if not self.session:
            return None
        url = f"http://{ip}:{port}/json/info"
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as response:
                response.raise_for_status()
                data = await response.json()
        except Exception:
            return None
        leds = data.get("leds") or {}
        return WledInfo(
            name=str(data.get("name") or ip),
            mac=normalize_mac(str(data.get("mac") or "")),
            ip=ip,
            port=port,
            led_count=int(leds.get("count") or 0),
            version=str(data.get("ver") or ""),
            max_segments=int(leds.get("maxseg") or 16),
        )
