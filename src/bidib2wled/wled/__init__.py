"""WLED JSON-API Client."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import aiohttp

from bidib2wled.config import normalize_mac

__all__ = [
    "LedOutput",
    "WledDevice",
    "WledInfo",
    "WledPool",
    "hex_from_rgb",
    "normalize_mac",
    "outputs_from_cfg",
    "rgb_from_hex",
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
class WledInfo:
    name: str
    mac: str
    ip: str
    port: int = 80
    led_count: int = 0
    version: str = ""
    mdns: str | None = None
    max_segments: int = 16
    reachable: bool = True
    outputs: list[LedOutput] = field(default_factory=list)

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


@dataclass
class WledDevice:
    info: WledInfo
    pixels: list[tuple[int, int, int]] = field(default_factory=list)
    session: aiohttp.ClientSession | None = None
    simulate: bool = False

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
            await self._fetch_outputs()
            self.ensure_size(self.info.led_count or 1)
            return self.info
        assert self.session is not None
        url = f"{self.base_url}/json/info"
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
        self.ensure_size(count or len(self.pixels) or 1)
        return self.info

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
            return
        await self._post_state(self.state_body(updates))

    def state_body(self, updates: dict[int, tuple[int, int, int]]) -> dict:
        max_idx = max(updates)
        total = max(max_idx + 1, self.info.led_count, len(self.pixels), 1)
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
        # Kein {"stop": 0}: das löscht Segmente. Bei zwei WLED-Ausgängen
        # ist Segment 1 der zweite Bus – der würde mit ausgehen.
        body: dict = {"tt": 0, "seg": segs}
        if any(pixel != (0, 0, 0) for pixel in self.pixels):
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
