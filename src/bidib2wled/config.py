"""YAML configuration (Pydantic). English keys; legacy German keys are accepted on load."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from bidib2wled.legacy import migrate_legacy_config

_DURATION_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*s?\s*$", re.I)
_MAC_HEX_RE = re.compile(r"[^0-9a-fA-F]")


def normalize_mac(value: str | None) -> str | None:
    """WLED liefert oft '4cc382c3d6e0', BiDiB/YAML sollen '4c:c3:82:c3:d6:e0'."""
    if value is None:
        return None
    hexdigits = _MAC_HEX_RE.sub("", str(value).strip())
    if not hexdigits:
        return None
    if len(hexdigits) != 12:
        raise ValueError(f"Invalid MAC: {value!r}")
    return ":".join(hexdigits[i : i + 2].lower() for i in range(0, 12, 2))


def parse_duration(value: Any) -> float:
    """'10s', 10 oder 10.5 → Sekunden."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = _DURATION_RE.match(value)
        if match:
            return float(match.group(1))
    raise ValueError(f"Invalid duration: {value!r} (expected e.g. 10 or '10s')")


def parse_delay_range(value: Any) -> tuple[float, float]:
    if value is None:
        return (0.0, 0.0)
    if isinstance(value, (list, tuple)) and len(value) == 2:
        lo, hi = parse_duration(value[0]), parse_duration(value[1])
        return (min(lo, hi), max(lo, hi))
    seconds = parse_duration(value)
    return (seconds, seconds)


_ANTEIL_ALIASES = {
    "r": "r",
    "rot": "r",
    "red": "r",
    "g": "g",
    "gruen": "g",
    "grün": "g",
    "green": "g",
    "b": "b",
    "blau": "b",
    "blue": "b",
    "rgb": "rgb",
    "alle": "rgb",
    "all": "rgb",
}


def parse_channel(value: Any) -> str:
    raw = str(value or "rgb").strip().lower()
    mapped = _ANTEIL_ALIASES.get(raw)
    if mapped is None:
        raise ValueError(f"channel must be r, g, b or rgb: {value!r}")
    return mapped


parse_anteil = parse_channel


_STEPS_ALIASES = {
    "auto": "auto",
    "automatisch": "auto",
    "leds": "leds",
    "led": "leds",
    "pixel": "leds",
    "pixeln": "leds",
    "kanaele": "channels",
    "kanäle": "channels",
    "anteile": "channels",
    "channels": "channels",
    "rgb": "channels",
}


def parse_steps(value: Any) -> str:
    raw = str(value or "auto").strip().lower().replace("ä", "ae")
    mapped = _STEPS_ALIASES.get(raw)
    if mapped is None:
        raise ValueError(f"steps must be auto, leds or channels: {value!r}")
    return mapped


parse_schritte = parse_steps


_TURN_ON_ALIASES = {
    "sofort": "immediate",
    "immediate": "immediate",
    "nacheinander": "sequential",
    "sequential": "sequential",
    "zufaellig": "random",
    "zufällig": "random",
    "random": "random",
}


def parse_turn_on(value: Any) -> str:
    raw = str(value or "random").strip().lower().replace("ä", "ae")
    mapped = _TURN_ON_ALIASES.get(raw)
    if mapped is None:
        raise ValueError(f"turn_on must be immediate, sequential or random: {value!r}")
    return mapped


_ORDER_ALIASES = {
    "definiert": "defined",
    "defined": "defined",
    "zufaellig": "random",
    "zufällig": "random",
    "random": "random",
}


def parse_order(value: Any) -> str:
    if isinstance(value, list):
        return value
    raw = str(value or "random").strip().lower().replace("ä", "ae")
    mapped = _ORDER_ALIASES.get(raw)
    if mapped is None:
        raise ValueError(f"order must be defined or random: {value!r}")
    return mapped


_LED_NAME_SPEC = re.compile(
    r"^(?:led\s*)?(?P<von>\d+)(?:\s*[-–]\s*(?:led\s*)?(?P<bis>\d+))?"
    r"(?:\s*(?P<farbe>r|g|b|rot|gruen|grün|green|blau|blue))?$",
    re.I,
)


def parse_led_name_line(line: str) -> tuple[int, int, str, str] | None:
    """Liest 'LED1 = Laterne', '3-7 Haus3', '12r=Halt'. Nummern sind 1-basiert."""
    raw = (line or "").strip()
    if not raw or raw.startswith("#"):
        return None
    if "=" in raw:
        left, name = raw.split("=", 1)
    elif ":" in raw:
        left, name = raw.split(":", 1)
    else:
        parts = raw.split(None, 1)
        if len(parts) != 2:
            return None
        left, name = parts
    name = name.strip()
    left = left.strip()
    if not name or not left:
        return None
    match = _LED_NAME_SPEC.match(left)
    if not match:
        return None
    von = int(match.group("von"))
    bis = int(match.group("bis") or von)
    if von < 1 or bis < 1:
        return None
    if bis < von:
        von, bis = bis, von
    farbe = match.group("farbe")
    anteil = parse_anteil(farbe) if farbe else "rgb"
    return von, bis, anteil, name


def format_led_name_line(von_1: int, bis_1: int, anteil: str, name: str) -> str:
    span = str(von_1) if von_1 == bis_1 else f"{von_1}-{bis_1}"
    color = "" if (anteil or "rgb") == "rgb" else anteil
    return f"{span}{color} = {name}"


class LampConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    controller: str
    leds: list[int] = Field(min_length=1)
    color: str = Field(default="FFFFFF", validation_alias=AliasChoices("color", "farbe"))
    brightness: int = Field(default=180, ge=0, le=255, validation_alias=AliasChoices("brightness", "helligkeit"))
    channel: Literal["r", "g", "b", "rgb"] = Field(default="rgb", validation_alias=AliasChoices("channel", "anteil"))

    @field_validator("color")
    @classmethod
    def _color(cls, value: str) -> str:
        cleaned = value.strip().lstrip("#").upper()
        if not re.fullmatch(r"[0-9A-F]{6}", cleaned):
            raise ValueError(f"color must be RRGGBB: {value!r}")
        return cleaned

    @field_validator("channel", mode="before")
    @classmethod
    def _channel(cls, value: Any) -> str:
        return parse_channel(value)

    @property
    def farbe(self) -> str:
        return self.color

    @property
    def helligkeit(self) -> int:
        return self.brightness

    @property
    def anteil(self) -> str:
        return self.channel


class WindowConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    leds: list[int] = Field(min_length=1)
    color: str = Field(default="FFFFFF", validation_alias=AliasChoices("color", "farbe"))
    brightness: int = Field(default=180, ge=0, le=255, validation_alias=AliasChoices("brightness", "helligkeit"))
    channel: Literal["r", "g", "b", "rgb"] = Field(default="rgb", validation_alias=AliasChoices("channel", "anteil"))

    @field_validator("color")
    @classmethod
    def _color(cls, value: str) -> str:
        return LampConfig._color(value)

    @field_validator("channel", mode="before")
    @classmethod
    def _channel(cls, value: Any) -> str:
        return parse_channel(value)

    @property
    def farbe(self) -> str:
        return self.color

    @property
    def helligkeit(self) -> int:
        return self.brightness

    @property
    def anteil(self) -> str:
        return self.channel


FensterConfig = WindowConfig


class HouseConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    controller: str
    windows: dict[str, WindowConfig] = Field(validation_alias=AliasChoices("windows", "fenster"))
    turn_on: Literal["immediate", "sequential", "random"] = Field(
        default="random", validation_alias=AliasChoices("turn_on", "einschalten")
    )
    delay: Any = Field(default=["2s", "8s"], validation_alias=AliasChoices("delay", "verzoegerung"))
    night_probability: float = Field(
        default=1.0, ge=0.0, le=1.0, validation_alias=AliasChoices("night_probability", "nacht-wahrscheinlichkeit", "nacht_wahrscheinlichkeit")
    )

    @field_validator("turn_on", mode="before")
    @classmethod
    def _turn_on(cls, value: Any) -> str:
        return parse_turn_on(value)

    @property
    def delay_range(self) -> tuple[float, float]:
        return parse_delay_range(self.delay)

    @property
    def fenster(self) -> dict[str, WindowConfig]:
        return self.windows

    @property
    def einschalten(self) -> str:
        return self.turn_on

    @property
    def verzoegerung(self) -> Any:
        return self.delay

    @property
    def nacht_wahrscheinlichkeit(self) -> float:
        return self.night_probability


class GroupConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    members: list[str] = Field(min_length=1, validation_alias=AliasChoices("members", "mitglieder"))

    @property
    def mitglieder(self) -> list[str]:
        return self.members


class SequenceConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    groups: list[str] = Field(min_length=1, validation_alias=AliasChoices("groups", "gruppen"))
    order: Literal["defined", "random"] | list[str] = Field(
        default="random", validation_alias=AliasChoices("order", "reihenfolge")
    )
    delay: Any = Field(default=["10s", "120s"], validation_alias=AliasChoices("delay", "verzoegerung"))

    @field_validator("order", mode="before")
    @classmethod
    def _order(cls, value: Any) -> Any:
        return parse_order(value)

    @property
    def delay_range(self) -> tuple[float, float]:
        return parse_delay_range(self.delay)

    @property
    def gruppen(self) -> list[str]:
        return self.groups

    @property
    def reihenfolge(self):
        return self.order

    @property
    def verzoegerung(self) -> Any:
        return self.delay


class SignalAspectConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str
    leds: dict[int, str] = Field(default_factory=dict)
    channels: dict[int, str] = Field(default_factory=dict, validation_alias=AliasChoices("channels", "anteile"))

    @model_validator(mode="before")
    @classmethod
    def _drop_null_channels(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = dict(data)
            if data.get("channels") is None:
                data.pop("channels", None)
            if data.get("anteile") is None:
                data.pop("anteile", None)
        return data

    @field_validator("leds")
    @classmethod
    def _colors(cls, value: dict[int, str]) -> dict[int, str]:
        return {int(idx): LampConfig._color(color) for idx, color in value.items()}

    @field_validator("channels", mode="before")
    @classmethod
    def _channels(cls, value: Any) -> dict[int, str]:
        if not value:
            return {}
        if not isinstance(value, dict):
            raise ValueError("channels must be an object")
        return {int(idx): parse_channel(channel) for idx, channel in value.items()}

    def channel_of(self, led: int) -> str:
        return self.channels.get(int(led), "rgb")

    def anteil_of(self, led: int) -> str:
        return self.channel_of(led)

    @property
    def anteile(self) -> dict[int, str]:
        return self.channels

    @anteile.setter
    def anteile(self, value: dict[int, str]) -> None:
        self.channels = value


class SignalConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    controller: str
    aspects: dict[int, SignalAspectConfig] = Field(validation_alias=AliasChoices("aspects", "begriffe"))

    @property
    def begriffe(self) -> dict[int, SignalAspectConfig]:
        return self.aspects


VEHICLE_TYPES = ("continuous", "blinker", "beacon", "strobe", "double_strobe")
VEHICLE_EMERGENCY_TYPES = ("beacon", "strobe", "double_strobe")
VEHICLE_ARTS = VEHICLE_TYPES
VEHICLE_EINSATZ_ARTS = VEHICLE_EMERGENCY_TYPES
_TYPE_ALIASES = {
    "dauerlicht": "continuous",
    "dauer": "continuous",
    "continuous": "continuous",
    "steady": "continuous",
    "warnblinker": "blinker",
    "blinker-links": "blinker",
    "blinker-rechts": "blinker",
    "blinker_links": "blinker",
    "blinker_rechts": "blinker",
    "rundumlicht": "beacon",
    "rundum": "beacon",
    "beacon": "beacon",
    "strobe": "strobe",
    "blitz": "strobe",
    "double": "double_strobe",
    "doppelblitz": "double_strobe",
    "double_strobe": "double_strobe",
    "blinker": "blinker",
}


class VehicleChannelConfig(BaseModel):
    """One vehicle light channel (headlights, indicators, beacon, …)."""

    model_config = ConfigDict(populate_by_name=True)
    leds: list[int] = Field(min_length=1)
    channel: Literal["r", "g", "b", "rgb"] = Field(default="rgb", validation_alias=AliasChoices("channel", "anteil"))
    color: str = Field(default="FFFFFF", validation_alias=AliasChoices("color", "farbe"))
    brightness: int = Field(default=180, ge=0, le=255, validation_alias=AliasChoices("brightness", "helligkeit"))
    type: Literal["continuous", "blinker", "beacon", "strobe", "double_strobe"] = Field(
        default="continuous", validation_alias=AliasChoices("type", "art")
    )
    steps: Literal["auto", "leds", "channels"] = Field(
        default="auto", validation_alias=AliasChoices("steps", "schritte")
    )

    @field_validator("channel", mode="before")
    @classmethod
    def _channel(cls, value: Any) -> str:
        return parse_channel(value)

    @field_validator("steps", mode="before")
    @classmethod
    def _steps(cls, value: Any) -> str:
        return parse_steps(value)

    @field_validator("type", mode="before")
    @classmethod
    def _type(cls, value: Any) -> str:
        raw = str(value or "continuous").strip().lower().replace("ü", "ue")
        raw = _TYPE_ALIASES.get(raw, raw)
        if raw not in VEHICLE_TYPES:
            raise ValueError(f"Unknown light type: {value!r}")
        return raw

    @field_validator("color")
    @classmethod
    def _color(cls, value: str) -> str:
        return LampConfig._color(value)

    @property
    def art(self) -> str:
        return self.type

    @property
    def anteil(self) -> str:
        return self.channel

    @property
    def farbe(self) -> str:
        return self.color

    @property
    def helligkeit(self) -> int:
        return self.brightness

    @property
    def schritte(self) -> str:
        return self.steps


class VehicleModeConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str
    channels: list[str] = Field(default_factory=list, validation_alias=AliasChoices("channels", "kanaele"))

    @property
    def kanaele(self) -> list[str]:
        return self.channels


def default_vehicle_modes(channels: dict[str, VehicleChannelConfig]) -> dict[int, VehicleModeConfig]:
    """Off / Lights / Hazards / Emergency, depending on which channel types exist."""
    continuous = [name for name, ch in channels.items() if ch.type == "continuous"]
    blinker = [name for name, ch in channels.items() if ch.type == "blinker"]
    emergency = [name for name, ch in channels.items() if ch.type in VEHICLE_EMERGENCY_TYPES]
    modes: dict[int, VehicleModeConfig] = {0: VehicleModeConfig(name="Off", channels=[])}
    next_n = 1
    if continuous:
        modes[next_n] = VehicleModeConfig(name="Lights", channels=list(continuous))
        next_n += 1
    if blinker:
        modes[next_n] = VehicleModeConfig(name="Hazards", channels=list(continuous) + blinker)
        next_n += 1
    if emergency:
        modes[next_n] = VehicleModeConfig(name="Emergency", channels=list(continuous) + emergency)
        next_n += 1
    if len(modes) == 1:
        modes[1] = VehicleModeConfig(name="On", channels=list(channels))
    return modes


default_vehicle_modi = default_vehicle_modes


class VehicleConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    controller: str
    channels: dict[str, VehicleChannelConfig] = Field(
        min_length=1, validation_alias=AliasChoices("channels", "kanaele")
    )
    modes: dict[int, VehicleModeConfig] = Field(
        default_factory=dict, validation_alias=AliasChoices("modes", "modi")
    )
    blink_period: Any = Field(default="0.75s", validation_alias=AliasChoices("blink_period", "blink_periode"))
    beacon_step: Any = Field(default="0.12s", validation_alias=AliasChoices("beacon_step", "rundum_schritt"))

    @property
    def kanaele(self) -> dict[str, VehicleChannelConfig]:
        return self.channels

    @property
    def modi(self) -> dict[int, VehicleModeConfig]:
        return self.modes

    @property
    def blink_periode(self) -> Any:
        return self.blink_period

    @property
    def rundum_schritt(self) -> Any:
        return self.beacon_step

    @property
    def blink_period_s(self) -> float:
        return parse_duration(self.blink_period)

    @property
    def rundum_step_s(self) -> float:
        return parse_duration(self.beacon_step)

    def resolved_modes(self) -> dict[int, VehicleModeConfig]:
        return self.modes if self.modes else default_vehicle_modes(self.channels)

    def resolved_modi(self) -> dict[int, VehicleModeConfig]:
        return self.resolved_modes()

    def all_leds(self) -> set[int]:
        leds: set[int] = set()
        for channel in self.channels.values():
            leds.update(channel.leds)
        return leds

    @model_validator(mode="after")
    def _mode_refs(self) -> VehicleConfig:
        known = set(self.channels)
        for mode_id, mode in self.modes.items():
            for name in mode.channels:
                if name not in known:
                    raise ValueError(f"Mode {mode_id}: unknown channel {name!r}")
        return self


class SpecialConfig(BaseModel):
    """WLED effect on contiguous LED ranges (special object type)."""

    model_config = ConfigDict(populate_by_name=True)
    controller: str
    leds: list[int] = Field(min_length=1)
    effect: int = Field(default=0, ge=0, validation_alias=AliasChoices("effect", "effekt"))
    palette: int = Field(default=0, ge=0)
    speed: int = Field(default=128, ge=0, le=255, validation_alias=AliasChoices("speed", "geschwindigkeit"))
    intensity: int = Field(default=128, ge=0, le=255, validation_alias=AliasChoices("intensity", "intensitaet"))
    color: str = Field(default="FFFFFF", validation_alias=AliasChoices("color", "farbe"))
    brightness: int | None = Field(default=None, ge=1, le=255, validation_alias=AliasChoices("brightness", "helligkeit"))
    channel: Literal["r", "g", "b", "rgb"] = Field(default="rgb", validation_alias=AliasChoices("channel", "anteil"))

    @field_validator("color")
    @classmethod
    def _color(cls, value: str) -> str:
        return LampConfig._color(value)

    @field_validator("channel", mode="before")
    @classmethod
    def _channel(cls, value: Any) -> str:
        return parse_channel(value)

    @property
    def effekt(self) -> int:
        return self.effect

    @property
    def geschwindigkeit(self) -> int:
        return self.speed

    @property
    def intensitaet(self) -> int:
        return self.intensity

    @property
    def farbe(self) -> str:
        return self.color

    @property
    def helligkeit(self) -> int | None:
        return self.brightness

    @property
    def anteil(self) -> str:
        return self.channel


class LedNameConfig(BaseModel):
    """Display name for an LED, an RGB channel, or a range (0-based indices)."""

    model_config = ConfigDict(populate_by_name=True)
    name: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    channel: Literal["r", "g", "b", "rgb"] = "rgb"

    @model_validator(mode="before")
    @classmethod
    def _led_alias(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "led" in data and "start" not in data:
            data = dict(data)
            led = data.pop("led")
            data["start"] = led
            data.setdefault("end", led)
        return data

    @field_validator("channel", mode="before")
    @classmethod
    def _channel(cls, value: Any) -> str:
        return parse_channel(value)

    @model_validator(mode="after")
    def _order(self) -> LedNameConfig:
        if self.end < self.start:
            self.start, self.end = self.end, self.start
        return self

    def covers(self, index: int) -> bool:
        return self.start <= int(index) <= self.end

    @property
    def von(self) -> int:
        return self.start

    @property
    def bis(self) -> int:
        return self.end

    @property
    def anteil(self) -> str:
        return self.channel


class ControllerConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str
    mdns: str | None = None
    mac: str | None = None
    ip: str | None = None
    leds: int | None = None
    port: int = 80
    names: list[LedNameConfig] = Field(default_factory=list, validation_alias=AliasChoices("names", "namen"))

    @field_validator("mac")
    @classmethod
    def _mac(cls, value: str | None) -> str | None:
        return normalize_mac(value)

    @property
    def namen(self) -> list[LedNameConfig]:
        return self.names

    @namen.setter
    def namen(self, value: list[LedNameConfig]) -> None:
        self.names = value


class NetBidibConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    enabled: bool = Field(default=True, validation_alias=AliasChoices("enabled", "aktiv"))
    mode: Literal["server", "client"] = Field(default="server", validation_alias=AliasChoices("mode", "modus"))
    port: int = 62875
    host: str | None = None
    node_name: str = Field(default="BiDiB2WLED", validation_alias=AliasChoices("node_name", "knotenname"))
    unique_id: str | None = None
    trusted: list[str] = Field(default_factory=list)
    pairing_timeout: float = 30.0
    accessories: dict[int, str] = Field(default_factory=dict)

    @property
    def aktiv(self) -> bool:
        return self.enabled

    @property
    def modus(self) -> str:
        return self.mode

    @property
    def knotenname(self) -> str:
        return self.node_name


class ClientConfig(BaseModel):
    """Future host client (not netBiDiB). Legacy YAML key: rocrail."""

    model_config = ConfigDict(populate_by_name=True)
    enabled: bool = Field(default=False, validation_alias=AliasChoices("enabled", "aktiv"))
    host: str = "127.0.0.1"
    port: int = 8051
    id_prefix: str = Field(default="wled-", validation_alias=AliasChoices("id_prefix", "id-praefix", "id_praefix"))

    @property
    def aktiv(self) -> bool:
        return self.enabled

    @property
    def id_praefix(self) -> str:
        return self.id_prefix


class AdapterConfig(BaseModel):
    netbidib: NetBidibConfig = Field(default_factory=NetBidibConfig)
    client: ClientConfig = Field(default_factory=ClientConfig)


class DiscoveryConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    mdns: bool = True
    interval: Any = Field(default="30s", validation_alias=AliasChoices("interval", "intervall"))
    timeout: Any = "90s"

    @property
    def intervall(self) -> Any:
        return self.interval

    @property
    def interval_s(self) -> float:
        return parse_duration(self.interval)

    @property
    def timeout_s(self) -> float:
        return parse_duration(self.timeout)


class WebConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080


class AppConfig(BaseModel):
    adapter: AdapterConfig = Field(default_factory=AdapterConfig)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    controller: list[ControllerConfig] = Field(default_factory=list)
    lamps: dict[str, LampConfig] = Field(default_factory=dict)
    houses: dict[str, HouseConfig] = Field(default_factory=dict)
    groups: dict[str, GroupConfig] = Field(default_factory=dict)
    sequences: dict[str, SequenceConfig] = Field(default_factory=dict)
    signals: dict[str, SignalConfig] = Field(default_factory=dict)
    special: dict[str, SpecialConfig] = Field(default_factory=dict)
    vehicles: dict[str, VehicleConfig] = Field(default_factory=dict)

    @property
    def lampen(self) -> dict[str, LampConfig]:
        return self.lamps

    @property
    def haeuser(self) -> dict[str, HouseConfig]:
        return self.houses

    @property
    def gruppen(self) -> dict[str, GroupConfig]:
        return self.groups

    @property
    def sequenzen(self) -> dict[str, SequenceConfig]:
        return self.sequences

    @property
    def signale(self) -> dict[str, SignalConfig]:
        return self.signals

    @property
    def spezial(self) -> dict[str, SpecialConfig]:
        return self.special

    @property
    def fahrzeuge(self) -> dict[str, VehicleConfig]:
        return self.vehicles

    @property
    def erkennung(self) -> DiscoveryConfig:
        return self.discovery

    @model_validator(mode="before")
    @classmethod
    def _legacy(cls, data: Any) -> Any:
        return migrate_legacy_config(data)

    @model_validator(mode="after")
    def _refs(self) -> AppConfig:
        names = {item.name for item in self.controller}
        for lamp_id, lamp in self.lamps.items():
            if lamp.controller not in names:
                raise ValueError(f"Lamp {lamp_id}: unknown controller {lamp.controller!r}")
        for house_id, house in self.houses.items():
            if house.controller not in names:
                raise ValueError(f"House {house_id}: unknown controller {house.controller!r}")
        for signal_id, signal in self.signals.items():
            if signal.controller not in names:
                raise ValueError(f"Signal {signal_id}: unknown controller {signal.controller!r}")
        for spec_id, spec in self.special.items():
            if spec.controller not in names:
                raise ValueError(f"Special {spec_id}: unknown controller {spec.controller!r}")
        for vehicle_id, vehicle in self.vehicles.items():
            if vehicle.controller not in names:
                raise ValueError(f"Vehicle {vehicle_id}: unknown controller {vehicle.controller!r}")
        known = (
            set(self.lamps)
            | set(self.houses)
            | set(self.groups)
            | set(self.sequences)
            | set(self.signals)
            | set(self.special)
            | set(self.vehicles)
        )
        for house_id, house in self.houses.items():
            for window_id in house.windows:
                known.add(f"{house_id}.{window_id}")
        for group_id, group in self.groups.items():
            for member in group.members:
                if member not in known and member not in self.groups:
                    raise ValueError(f"Group {group_id}: unknown member {member!r}")
        for seq_id, seq in self.sequences.items():
            for group_id in seq.groups:
                if group_id not in self.groups:
                    raise ValueError(f"Sequence {seq_id}: unknown group {group_id!r}")
        for anum, obj_id in self.adapter.netbidib.accessories.items():
            if obj_id not in known:
                raise ValueError(f"Accessory {anum}: unknown object {obj_id!r}")
        return self

    def controller_by_name(self, name: str) -> ControllerConfig | None:
        for item in self.controller:
            if item.name == name:
                return item
        return None

    def led_label(self, controller: str, index: int, anteil: str = "rgb") -> str:
        """Display name for an LED in lists, or empty.

        Multiple color names (R/G/B) are always joined with ' / '.
        """
        ctrl = self.controller_by_name(controller)
        if ctrl is None:
            return ""
        covering = [item for item in ctrl.names if item.covers(index)]
        if not covering:
            return ""

        def smallest(items: list[LedNameConfig]) -> LedNameConfig:
            return min(items, key=lambda item: (item.end - item.start, item.name))

        parts: list[str] = []
        for component in ("r", "g", "b"):
            hits = [item for item in covering if item.channel == component]
            if hits:
                parts.append(smallest(hits).name)
        if parts:
            return " / ".join(parts)
        rgb = [item for item in covering if item.channel == "rgb"]
        return smallest(rgb).name if rgb else ""

    def switchable_object_ids(self) -> list[str]:
        """Objects with their own BiDiB accessory number (windows only after a manual assignment)."""
        return (
            list(self.lamps)
            + list(self.houses)
            + list(self.groups)
            + list(self.sequences)
            + list(self.signals)
            + list(self.special)
            + list(self.vehicles)
        )

    def all_object_ids(self) -> list[str]:
        ids = self.switchable_object_ids()
        for house_id, house in self.houses.items():
            ids.extend(f"{house_id}.{window_id}" for window_id in house.windows)
        return ids

    def accessory_map(self) -> dict[int, str]:
        """BiDiB-Accessory-Index (ab 0) → Objekt. Feste YAML-Nummern bleiben, Rest bekommt die nächste freie."""
        known = set(self.all_object_ids())
        mapping: dict[int, str] = {}
        used: set[str] = set()
        for anum, obj_id in self.adapter.netbidib.accessories.items():
            try:
                idx = int(anum)
            except (TypeError, ValueError):
                continue
            if obj_id in known and obj_id not in used:
                mapping[idx] = obj_id
                used.add(obj_id)
        next_n = 0
        for obj_id in self.switchable_object_ids():
            if obj_id in used:
                continue
            while next_n in mapping:
                next_n += 1
            mapping[next_n] = obj_id
            used.add(obj_id)
            next_n += 1
        return dict(sorted(mapping.items()))

    def ensure_accessories(self) -> bool:
        filled = self.accessory_map()
        current = {int(k): v for k, v in self.adapter.netbidib.accessories.items()}
        if current == filled:
            return False
        self.adapter.netbidib.accessories = filled
        return True

    def set_accessory(self, object_id: str, accessory: int) -> None:
        if self.object_kind(object_id) is None:
            raise ValueError(f"Unknown object: {object_id}")
        if accessory < 0 or accessory > 255:
            raise ValueError("Address must be between 0 and 255")
        self.ensure_accessories()
        mapping = dict(self.adapter.netbidib.accessories)
        reverse = {obj: anum for anum, obj in mapping.items()}
        new_anum = accessory
        old_anum = reverse.get(object_id)
        occupant = mapping.get(new_anum)
        if occupant == object_id:
            return
        if occupant is not None and old_anum is not None:
            mapping[old_anum] = occupant
            mapping[new_anum] = object_id
        elif occupant is not None:
            free = 0
            while free in mapping:
                free += 1
            mapping[free] = occupant
            mapping[new_anum] = object_id
        else:
            if old_anum is not None:
                del mapping[old_anum]
            mapping[new_anum] = object_id
        self.adapter.netbidib.accessories = dict(sorted(mapping.items()))

    def object_kind(self, object_id: str) -> str | None:
        if object_id in self.lamps:
            return "lamp"
        if object_id in self.houses:
            return "house"
        if object_id in self.groups:
            return "group"
        if object_id in self.sequences:
            return "sequence"
        if object_id in self.signals:
            return "signal"
        if object_id in self.special:
            return "special"
        if object_id in self.vehicles:
            return "vehicle"
        if "." in object_id:
            house_id, window_id = object_id.split(".", 1)
            house = self.houses.get(house_id)
            if house and window_id in house.windows:
                return "window"
        return None

    def aspect_count(self, object_id: str) -> int:
        if object_id in self.signals:
            aspects = self.signals[object_id].aspects
            return max(aspects) + 1 if aspects else 2
        if object_id in self.vehicles:
            modes = self.vehicles[object_id].resolved_modes()
            return max(modes) + 1 if modes else 2
        return 2

    def led_usage(self) -> dict[str, dict[str, list[str]]]:
        """Controller → LED-Index (als String) → Objekt-IDs, die diese LED nutzen."""
        return {ctrl: {led: list(info["objects"]) for led, info in leds.items()} for ctrl, leds in self._led_map().items()}

    def led_channel_usage(self) -> dict[str, dict[str, dict[str, list[str]]]]:
        """Controller → LED-Index → Anteil (r/g/b) → Objekt-IDs."""
        return {
            ctrl: {led: {comp: list(owners) for comp, owners in info["channels"].items()} for led, info in leds.items()}
            for ctrl, leds in self._led_map().items()
        }

    def _led_map(self) -> dict[str, dict[str, dict[str, object]]]:
        from bidib2wled.pixels import expand_anteil

        usage: dict[str, dict[str, dict[str, object]]] = {}

        def add(controller: str, leds, obj_id: str, anteil: str = "rgb") -> None:
            bucket = usage.setdefault(controller, {})
            for led in leds:
                key = str(int(led))
                entry = bucket.setdefault(key, {"objects": [], "channels": {"r": [], "g": [], "b": []}})
                objects: list[str] = entry["objects"]  # type: ignore[assignment]
                channels: dict[str, list[str]] = entry["channels"]  # type: ignore[assignment]
                if obj_id not in objects:
                    objects.append(obj_id)
                for component in expand_anteil(anteil):
                    owners = channels.setdefault(component, [])
                    if obj_id not in owners:
                        owners.append(obj_id)

        for lamp_id, lamp in self.lamps.items():
            add(lamp.controller, lamp.leds, lamp_id, lamp.channel)
        for house_id, house in self.houses.items():
            for window_id, window in house.windows.items():
                add(house.controller, window.leds, f"{house_id}.{window_id}", window.channel)
        for signal_id, signal in self.signals.items():
            for aspect in signal.aspects.values():
                for idx in aspect.leds:
                    add(signal.controller, [idx], signal_id, aspect.channel_of(idx))
        for spec_id, spec in self.special.items():
            add(spec.controller, spec.leds, spec_id, spec.channel)
        for vehicle_id, vehicle in self.vehicles.items():
            for channel in vehicle.channels.values():
                add(vehicle.controller, channel.leds, vehicle_id, channel.channel)
        return usage

    def max_led_index(self, controller: str) -> int:
        """Höchster verwendeter LED-Index auf dem Controller, oder -1."""
        highest = -1
        for key in self._led_map().get(controller, {}):
            highest = max(highest, int(key))
        return highest

    def shift_controller_leds(self, controller: str, first_shifted: int, count: int, wled_count: int) -> int:
        """Schiebt alle LED-Adressen ab `first_shifted` um `count`. Prüft gegen die WLED-Länge."""
        from bidib2wled.pixels import shift_index_map, shift_led_list, shift_span

        if count < 1:
            raise ValueError("Count must be at least 1")
        if first_shifted < 0:
            raise ValueError("Invalid insert position")
        if wled_count < 1:
            raise ValueError("WLED LED count unknown – claim the controller first")
        current_max = self.max_led_index(controller)
        shifted_max = current_max + count if current_max >= first_shifted else current_max
        last_new = first_shifted + count - 1
        need = max(shifted_max, last_new) + 1
        if need > wled_count:
            raise ValueError(
                f"Inserting would require {need} LEDs, but WLED reports only {wled_count}. "
                f"Increase the LED count in WLED to at least {need} first."
            )
        changed = 0
        for lamp in self.lamps.values():
            if lamp.controller != controller:
                continue
            lamp.leds, n = shift_led_list(lamp.leds, first_shifted, count)
            changed += n
        for house in self.houses.values():
            if house.controller != controller:
                continue
            for window in house.windows.values():
                window.leds, n = shift_led_list(window.leds, first_shifted, count)
                changed += n
        for signal in self.signals.values():
            if signal.controller != controller:
                continue
            for aspect in signal.aspects.values():
                new_leds, n = shift_index_map(dict(aspect.leds), first_shifted, count)
                aspect.leds = {int(k): str(v) for k, v in new_leds.items()}
                changed += n
                if aspect.channels:
                    new_channels, _ = shift_index_map(dict(aspect.channels), first_shifted, count)
                    aspect.channels = {int(k): str(v) for k, v in new_channels.items()}
        for spec in self.special.values():
            if spec.controller != controller:
                continue
            spec.leds, n = shift_led_list(spec.leds, first_shifted, count)
            changed += n
        for vehicle in self.vehicles.values():
            if vehicle.controller != controller:
                continue
            for channel in vehicle.channels.values():
                channel.leds, n = shift_led_list(channel.leds, first_shifted, count)
                changed += n
        ctrl = self.controller_by_name(controller)
        if ctrl and ctrl.names:
            moved: list[LedNameConfig] = []
            for label in ctrl.names:
                start, end = shift_span(label.start, label.end, first_shifted, count)
                moved.append(label.model_copy(update={"start": start, "end": end}))
            ctrl.names = moved
        return changed

    def delete_controller_leds(self, controller: str, first_removed: int, count: int) -> dict[str, int | list[str]]:
        """Entfernt `count` LEDs ab `first_removed` und zählt Folgeadressen herunter. Keine WLED-Sperre."""
        from bidib2wled.pixels import delete_index_range, delete_led_range, delete_span

        if count < 1:
            raise ValueError("Count must be at least 1")
        if first_removed < 0:
            raise ValueError("Invalid delete position")
        emptied: list[str] = []

        def list_empty(obj_id: str, leds: list[int]) -> None:
            kept, _, _ = delete_led_range(leds, first_removed, count)
            if not kept:
                emptied.append(obj_id)

        for lamp_id, lamp in self.lamps.items():
            if lamp.controller == controller:
                list_empty(lamp_id, lamp.leds)
        for house_id, house in self.houses.items():
            if house.controller != controller:
                continue
            for window_id, window in house.windows.items():
                list_empty(f"{house_id}.{window_id}", window.leds)
        for signal_id, signal in self.signals.items():
            if signal.controller != controller:
                continue
            for aspect_id, aspect in signal.aspects.items():
                kept, _, _ = delete_index_range(dict(aspect.leds), first_removed, count)
                if not kept:
                    emptied.append(f"{signal_id}:{aspect.name or aspect_id}")
        for spec_id, spec in self.special.items():
            if spec.controller == controller:
                list_empty(spec_id, spec.leds)
        for vehicle_id, vehicle in self.vehicles.items():
            if vehicle.controller != controller:
                continue
            for channel_id, channel in vehicle.channels.items():
                list_empty(f"{vehicle_id}.{channel_id}", channel.leds)
        if emptied:
            names = ", ".join(emptied)
            raise ValueError(
                f"These LEDs cannot be removed, or the following objects would have no LED left: {names}. "
                "Change or delete those objects first."
            )

        shifted = 0
        dropped = 0
        for lamp in self.lamps.values():
            if lamp.controller != controller:
                continue
            lamp.leds, n, d = delete_led_range(lamp.leds, first_removed, count)
            shifted += n
            dropped += d
        for house in self.houses.values():
            if house.controller != controller:
                continue
            for window in house.windows.values():
                window.leds, n, d = delete_led_range(window.leds, first_removed, count)
                shifted += n
                dropped += d
        for signal in self.signals.values():
            if signal.controller != controller:
                continue
            for aspect in signal.aspects.values():
                new_leds, n, d = delete_index_range(dict(aspect.leds), first_removed, count)
                aspect.leds = {int(k): str(v) for k, v in new_leds.items()}
                shifted += n
                dropped += d
                if aspect.channels:
                    new_channels, _, _ = delete_index_range(dict(aspect.channels), first_removed, count)
                    aspect.channels = {int(k): str(v) for k, v in new_channels.items()}
        for spec in self.special.values():
            if spec.controller != controller:
                continue
            spec.leds, n, d = delete_led_range(spec.leds, first_removed, count)
            shifted += n
            dropped += d
        for vehicle in self.vehicles.values():
            if vehicle.controller != controller:
                continue
            for channel in vehicle.channels.values():
                channel.leds, n, d = delete_led_range(channel.leds, first_removed, count)
                shifted += n
                dropped += d
        ctrl = self.controller_by_name(controller)
        if ctrl and ctrl.names:
            kept_names: list[LedNameConfig] = []
            for label in ctrl.names:
                span = delete_span(label.start, label.end, first_removed, count)
                if span is None:
                    continue
                kept_names.append(label.model_copy(update={"start": span[0], "end": span[1]}))
            ctrl.names = kept_names
        return {"shifted": shifted, "dropped": dropped}

    def object_usage(self) -> dict[str, list[str]]:
        """Objekt-ID → Gruppen/Sequenzen, die das Objekt referenzieren."""
        usage: dict[str, list[str]] = {}

        def add(obj_id: str, owner: str) -> None:
            usage.setdefault(obj_id, []).append(owner)

        for group_id, group in self.groups.items():
            for member in group.members:
                add(member, group_id)
        for seq_id, seq in self.sequences.items():
            for group_id in seq.groups:
                add(group_id, seq_id)
        return usage


def host_setup_info(kind: str, accessory: int | None) -> list[dict[str, str]]:
    """Short per-host setup hint (Info column). Add further programs as builders."""
    builders = (_rocrail_setup,)
    return [row for build in builders if (row := build(kind, accessory))]


def _rocrail_setup(kind: str, accessory: int | None) -> dict[str, str] | None:
    if accessory is None:
        if kind in ("window", "fenster"):
            return {
                "program": "Rocrail",
                "text": "no own address – switch the house (output, port 0, accessory on, protocol Default)",
            }
        return None
    rocrail = accessory + 1
    base = f"address {rocrail} (address+1), port 0, bus 0, protocol Default, accessory on"
    if kind == "signal":
        return {"program": "Rocrail", "text": f"Signal: {base}; aspects as in the list"}
    if kind in ("vehicle", "fahrzeug"):
        return {
            "program": "Rocrail",
            "text": f"Signal: {base}; modes as in the list (0=Off)",
        }
    return {"program": "Rocrail", "text": f"Output: {base}"}


def default_config() -> AppConfig:
    return AppConfig()


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        return default_config()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("Configuration must be a YAML object")
    return AppConfig.model_validate(raw)


def _omit_empty_channels(payload: Any) -> Any:
    """Do not write empty `channels: null` into YAML – that used to block startup."""
    if not isinstance(payload, dict):
        return payload
    signals = payload.get("signals")
    if isinstance(signals, dict):
        for signal in signals.values():
            if not isinstance(signal, dict):
                continue
            aspects = signal.get("aspects")
            if not isinstance(aspects, dict):
                continue
            for aspect in aspects.values():
                if isinstance(aspect, dict) and not aspect.get("channels"):
                    aspect.pop("channels", None)
                    aspect.pop("anteile", None)
    for vehicle in (payload.get("vehicles") or {}).values():
        if not isinstance(vehicle, dict):
            continue
        for channel in (vehicle.get("channels") or {}).values():
            if isinstance(channel, dict) and channel.get("steps") in (None, "auto"):
                channel.pop("steps", None)
    for ctrl in payload.get("controller") or []:
        if isinstance(ctrl, dict) and not ctrl.get("names"):
            ctrl.pop("names", None)
    return payload


_omit_empty_anteile = _omit_empty_channels


def save_config(path: Path, config: AppConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)
    payload = _omit_empty_channels(config.model_dump(by_alias=False, exclude_none=True))
    text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, default_flow_style=False)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
