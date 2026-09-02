"""YAML-Konfiguration (Pydantic). Deutsche Schlüssel wie im Konzept."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
        raise ValueError(f"Ungültige MAC: {value!r}")
    return ":".join(hexdigits[i : i + 2].lower() for i in range(0, 12, 2))


def parse_duration(value: Any) -> float:
    """'10s', 10 oder 10.5 → Sekunden."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = _DURATION_RE.match(value)
        if match:
            return float(match.group(1))
    raise ValueError(f"Ungültige Dauer: {value!r} (erwartet z. B. 10 oder '10s')")


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


def parse_anteil(value: Any) -> str:
    raw = str(value or "rgb").strip().lower()
    mapped = _ANTEIL_ALIASES.get(raw)
    if mapped is None:
        raise ValueError(f"anteil muss r, g, b oder rgb sein: {value!r}")
    return mapped


_SCHRITTE_ALIASES = {
    "auto": "auto",
    "automatisch": "auto",
    "leds": "leds",
    "led": "leds",
    "pixel": "leds",
    "pixeln": "leds",
    "kanaele": "kanaele",
    "kanäle": "kanaele",
    "anteile": "kanaele",
    "channels": "kanaele",
    "rgb": "kanaele",
}


def parse_schritte(value: Any) -> str:
    raw = str(value or "auto").strip().lower().replace("ä", "ae")
    mapped = _SCHRITTE_ALIASES.get(raw)
    if mapped is None:
        raise ValueError(f"schritte muss auto, leds oder kanaele sein: {value!r}")
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
    farbe: str = "FFFFFF"
    helligkeit: int = Field(default=180, ge=0, le=255)
    anteil: Literal["r", "g", "b", "rgb"] = "rgb"

    @field_validator("farbe")
    @classmethod
    def _color(cls, value: str) -> str:
        cleaned = value.strip().lstrip("#").upper()
        if not re.fullmatch(r"[0-9A-F]{6}", cleaned):
            raise ValueError(f"Farbe muss RRGGBB sein: {value!r}")
        return cleaned

    @field_validator("anteil", mode="before")
    @classmethod
    def _anteil(cls, value: Any) -> str:
        return parse_anteil(value)


class FensterConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    leds: list[int] = Field(min_length=1)
    farbe: str = "FFFFFF"
    helligkeit: int = Field(default=180, ge=0, le=255)
    anteil: Literal["r", "g", "b", "rgb"] = "rgb"

    @field_validator("farbe")
    @classmethod
    def _color(cls, value: str) -> str:
        return LampConfig._color(value)

    @field_validator("anteil", mode="before")
    @classmethod
    def _anteil(cls, value: Any) -> str:
        return parse_anteil(value)


class HouseConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    controller: str
    fenster: dict[str, FensterConfig]
    einschalten: Literal["sofort", "nacheinander", "zufaellig"] = "zufaellig"
    verzoegerung: Any = Field(default=["2s", "8s"])
    nacht_wahrscheinlichkeit: float = Field(default=1.0, ge=0.0, le=1.0, alias="nacht-wahrscheinlichkeit")

    @property
    def delay_range(self) -> tuple[float, float]:
        return parse_delay_range(self.verzoegerung)


class GroupConfig(BaseModel):
    mitglieder: list[str] = Field(min_length=1)


class SequenceConfig(BaseModel):
    gruppen: list[str] = Field(min_length=1)
    reihenfolge: Literal["definiert", "zufaellig"] | list[str] = "zufaellig"
    verzoegerung: Any = Field(default=["10s", "120s"])

    @property
    def delay_range(self) -> tuple[float, float]:
        return parse_delay_range(self.verzoegerung)


class SignalAspectConfig(BaseModel):
    name: str
    leds: dict[int, str] = Field(default_factory=dict)
    anteile: dict[int, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _drop_null_anteile(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("anteile") is None:
            data = dict(data)
            data.pop("anteile", None)
        return data

    @field_validator("leds")
    @classmethod
    def _colors(cls, value: dict[int, str]) -> dict[int, str]:
        return {int(idx): LampConfig._color(color) for idx, color in value.items()}

    @field_validator("anteile", mode="before")
    @classmethod
    def _anteile(cls, value: Any) -> dict[int, str]:
        if not value:
            return {}
        if not isinstance(value, dict):
            raise ValueError("anteile muss ein Objekt sein")
        return {int(idx): parse_anteil(anteil) for idx, anteil in value.items()}

    def anteil_of(self, led: int) -> str:
        return self.anteile.get(int(led), "rgb")


class SignalConfig(BaseModel):
    controller: str
    begriffe: dict[int, SignalAspectConfig]


VEHICLE_ARTS = ("dauer", "blinker", "rundum", "blitz", "doppelblitz")
VEHICLE_EINSATZ_ARTS = ("rundum", "blitz", "doppelblitz")
_ART_ALIASES = {
    "dauerlicht": "dauer",
    "warnblinker": "blinker",
    "blinker-links": "blinker",
    "blinker-rechts": "blinker",
    "blinker_links": "blinker",
    "blinker_rechts": "blinker",
    "rundumlicht": "rundum",
    "beacon": "rundum",
    "strobe": "blitz",
    "double": "doppelblitz",
    "doppelblitz": "doppelblitz",
}


class VehicleChannelConfig(BaseModel):
    """Ein Lichtkanal eines Fahrzeugs (Scheinwerfer, Blinker, Rundumlicht, …)."""

    model_config = ConfigDict(populate_by_name=True)
    leds: list[int] = Field(min_length=1)
    anteil: Literal["r", "g", "b", "rgb"] = "rgb"
    farbe: str = "FFFFFF"
    helligkeit: int = Field(default=180, ge=0, le=255)
    art: Literal["dauer", "blinker", "rundum", "blitz", "doppelblitz"] = "dauer"
    schritte: Literal["auto", "leds", "kanaele"] = "auto"

    @field_validator("anteil", mode="before")
    @classmethod
    def _anteil(cls, value: Any) -> str:
        return parse_anteil(value)

    @field_validator("schritte", mode="before")
    @classmethod
    def _schritte(cls, value: Any) -> str:
        return parse_schritte(value)

    @field_validator("art", mode="before")
    @classmethod
    def _art(cls, value: Any) -> str:
        raw = str(value or "dauer").strip().lower().replace("ü", "ue")
        raw = _ART_ALIASES.get(raw, raw)
        if raw not in VEHICLE_ARTS:
            raise ValueError(f"Unbekannte Beleuchtungsart: {value!r}")
        return raw

    @field_validator("farbe")
    @classmethod
    def _color(cls, value: str) -> str:
        return LampConfig._color(value)


class VehicleModeConfig(BaseModel):
    name: str
    kanaele: list[str] = Field(default_factory=list)


def default_vehicle_modi(kanaele: dict[str, VehicleChannelConfig]) -> dict[int, VehicleModeConfig]:
    """Aus / Licht / Warnblinker / Einsatz, je nachdem welche Kanalarten existieren."""
    dauer = [name for name, ch in kanaele.items() if ch.art == "dauer"]
    blinker = [name for name, ch in kanaele.items() if ch.art == "blinker"]
    einsatz = [name for name, ch in kanaele.items() if ch.art in VEHICLE_EINSATZ_ARTS]
    modi: dict[int, VehicleModeConfig] = {0: VehicleModeConfig(name="Aus", kanaele=[])}
    next_n = 1
    if dauer:
        modi[next_n] = VehicleModeConfig(name="Licht", kanaele=list(dauer))
        next_n += 1
    if blinker:
        modi[next_n] = VehicleModeConfig(name="Warnblinker", kanaele=list(dauer) + blinker)
        next_n += 1
    if einsatz:
        modi[next_n] = VehicleModeConfig(name="Einsatz", kanaele=list(dauer) + einsatz)
        next_n += 1
    if len(modi) == 1:
        modi[1] = VehicleModeConfig(name="An", kanaele=list(kanaele))
    return modi


class VehicleConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    controller: str
    kanaele: dict[str, VehicleChannelConfig] = Field(min_length=1)
    modi: dict[int, VehicleModeConfig] = Field(default_factory=dict)
    blink_periode: Any = Field(default="0.75s")
    rundum_schritt: Any = Field(default="0.12s")

    @property
    def blink_period_s(self) -> float:
        return parse_duration(self.blink_periode)

    @property
    def rundum_step_s(self) -> float:
        return parse_duration(self.rundum_schritt)

    def resolved_modi(self) -> dict[int, VehicleModeConfig]:
        return self.modi if self.modi else default_vehicle_modi(self.kanaele)

    def all_leds(self) -> set[int]:
        leds: set[int] = set()
        for channel in self.kanaele.values():
            leds.update(channel.leds)
        return leds

    @model_validator(mode="after")
    def _mode_refs(self) -> VehicleConfig:
        known = set(self.kanaele)
        for mode_id, mode in self.modi.items():
            for name in mode.kanaele:
                if name not in known:
                    raise ValueError(f"Modus {mode_id}: unbekannter Kanal {name!r}")
        return self


class SpecialConfig(BaseModel):
    """WLED-Effekt auf zusammenhängenden LED-Bereichen (Objekttyp Spezial)."""

    model_config = ConfigDict(populate_by_name=True)
    controller: str
    leds: list[int] = Field(min_length=1)
    effekt: int = Field(default=0, ge=0)
    palette: int = Field(default=0, ge=0)
    geschwindigkeit: int = Field(default=128, ge=0, le=255)
    intensitaet: int = Field(default=128, ge=0, le=255)
    farbe: str = "FFFFFF"
    helligkeit: int | None = Field(default=None, ge=1, le=255)
    anteil: Literal["r", "g", "b", "rgb"] = "rgb"

    @field_validator("farbe")
    @classmethod
    def _color(cls, value: str) -> str:
        return LampConfig._color(value)

    @field_validator("anteil", mode="before")
    @classmethod
    def _anteil(cls, value: Any) -> str:
        return parse_anteil(value)


class LedNameConfig(BaseModel):
    """Anzeigename für eine LED, einen RGB-Anteil oder einen Bereich (0-basierte Indizes)."""

    model_config = ConfigDict(populate_by_name=True)
    name: str = Field(min_length=1)
    von: int = Field(ge=0)
    bis: int = Field(ge=0)
    anteil: Literal["r", "g", "b", "rgb"] = "rgb"

    @model_validator(mode="before")
    @classmethod
    def _led_alias(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "led" in data and "von" not in data:
            data = dict(data)
            led = data.pop("led")
            data["von"] = led
            data.setdefault("bis", led)
        return data

    @field_validator("anteil", mode="before")
    @classmethod
    def _anteil(cls, value: Any) -> str:
        return parse_anteil(value)

    @model_validator(mode="after")
    def _order(self) -> LedNameConfig:
        if self.bis < self.von:
            self.von, self.bis = self.bis, self.von
        return self

    def covers(self, index: int) -> bool:
        return self.von <= int(index) <= self.bis


class ControllerConfig(BaseModel):
    name: str
    mdns: str | None = None
    mac: str | None = None
    ip: str | None = None
    leds: int | None = None
    port: int = 80
    namen: list[LedNameConfig] = Field(default_factory=list)

    @field_validator("mac")
    @classmethod
    def _mac(cls, value: str | None) -> str | None:
        return normalize_mac(value)


class NetBidibConfig(BaseModel):
    aktiv: bool = True
    modus: Literal["server", "client"] = "server"
    port: int = 62875
    host: str | None = None
    knotenname: str = "BiDiB2WLED"
    unique_id: str | None = None
    trusted: list[str] = Field(default_factory=list)
    pairing_timeout: float = 30.0
    accessories: dict[int, str] = Field(default_factory=dict)


class ClientConfig(BaseModel):
    """Zukünftiger Steuerungs-Client (nicht netBiDiB). Alter YAML-Schlüssel: rocrail."""

    aktiv: bool = False
    host: str = "127.0.0.1"
    port: int = 8051
    id_praefix: str = Field(default="wled-", alias="id-praefix")


class AdapterConfig(BaseModel):
    netbidib: NetBidibConfig = Field(default_factory=NetBidibConfig)
    client: ClientConfig = Field(default_factory=ClientConfig)

    @model_validator(mode="before")
    @classmethod
    def _migrate_rocrail(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "rocrail" not in data:
            return data
        data = dict(data)
        legacy = data.pop("rocrail")
        if "client" not in data:
            data["client"] = legacy
        return data


class DiscoveryConfig(BaseModel):
    mdns: bool = True
    intervall: Any = "30s"
    timeout: Any = "90s"

    @property
    def interval_s(self) -> float:
        return parse_duration(self.intervall)

    @property
    def timeout_s(self) -> float:
        return parse_duration(self.timeout)


class WebConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080


class AppConfig(BaseModel):
    adapter: AdapterConfig = Field(default_factory=AdapterConfig)
    erkennung: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    controller: list[ControllerConfig] = Field(default_factory=list)
    lampen: dict[str, LampConfig] = Field(default_factory=dict)
    haeuser: dict[str, HouseConfig] = Field(default_factory=dict)
    gruppen: dict[str, GroupConfig] = Field(default_factory=dict)
    sequenzen: dict[str, SequenceConfig] = Field(default_factory=dict)
    signale: dict[str, SignalConfig] = Field(default_factory=dict)
    spezial: dict[str, SpecialConfig] = Field(default_factory=dict)
    fahrzeuge: dict[str, VehicleConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _refs(self) -> AppConfig:
        names = {item.name for item in self.controller}
        for lamp_id, lamp in self.lampen.items():
            if lamp.controller not in names:
                raise ValueError(f"Lampe {lamp_id}: unbekannter Controller {lamp.controller!r}")
        for house_id, house in self.haeuser.items():
            if house.controller not in names:
                raise ValueError(f"Haus {house_id}: unbekannter Controller {house.controller!r}")
        for signal_id, signal in self.signale.items():
            if signal.controller not in names:
                raise ValueError(f"Signal {signal_id}: unbekannter Controller {signal.controller!r}")
        for spec_id, spec in self.spezial.items():
            if spec.controller not in names:
                raise ValueError(f"Spezial {spec_id}: unbekannter Controller {spec.controller!r}")
        for vehicle_id, vehicle in self.fahrzeuge.items():
            if vehicle.controller not in names:
                raise ValueError(f"Fahrzeug {vehicle_id}: unbekannter Controller {vehicle.controller!r}")
        known = (
            set(self.lampen)
            | set(self.haeuser)
            | set(self.gruppen)
            | set(self.sequenzen)
            | set(self.signale)
            | set(self.spezial)
            | set(self.fahrzeuge)
        )
        for house_id, house in self.haeuser.items():
            for window_id in house.fenster:
                known.add(f"{house_id}.{window_id}")
        for group_id, group in self.gruppen.items():
            for member in group.mitglieder:
                if member not in known and member not in self.gruppen:
                    raise ValueError(f"Gruppe {group_id}: unbekanntes Mitglied {member!r}")
        for seq_id, seq in self.sequenzen.items():
            for group_id in seq.gruppen:
                if group_id not in self.gruppen:
                    raise ValueError(f"Sequenz {seq_id}: unbekannte Gruppe {group_id!r}")
        for anum, obj_id in self.adapter.netbidib.accessories.items():
            if obj_id not in known:
                raise ValueError(f"Accessory {anum}: unbekanntes Objekt {obj_id!r}")
        return self

    def controller_by_name(self, name: str) -> ControllerConfig | None:
        for item in self.controller:
            if item.name == name:
                return item
        return None

    def led_label(self, controller: str, index: int, anteil: str = "rgb") -> str:
        """Anzeigename für eine LED in den Listen, sonst leer."""
        ctrl = self.controller_by_name(controller)
        if ctrl is None:
            return ""
        covering = [item for item in ctrl.namen if item.covers(index)]
        if not covering:
            return ""
        want = parse_anteil(anteil)

        def smallest(items: list[LedNameConfig]) -> LedNameConfig:
            return min(items, key=lambda item: (item.bis - item.von, item.name))

        if want in ("r", "g", "b"):
            exact = [item for item in covering if item.anteil == want]
            if exact:
                return smallest(exact).name
        channels = [item for item in covering if item.anteil in ("r", "g", "b")]
        rgb = [item for item in covering if item.anteil == "rgb"]
        if want == "rgb" and channels:
            parts: list[str] = []
            for component in ("r", "g", "b"):
                hits = [item for item in channels if item.anteil == component]
                if hits:
                    parts.append(smallest(hits).name)
            if parts:
                extra = smallest(rgb).name if rgb else ""
                return f"{extra} ({' / '.join(parts)})" if extra else " / ".join(parts)
        if rgb:
            return smallest(rgb).name
        if channels:
            return smallest(channels).name
        return ""

    def switchable_object_ids(self) -> list[str]:
        """Objekte mit eigener BiDiB-Accessory-Nummer (Fenster nur nach Handzuweisung)."""
        return (
            list(self.lampen)
            + list(self.haeuser)
            + list(self.gruppen)
            + list(self.sequenzen)
            + list(self.signale)
            + list(self.spezial)
            + list(self.fahrzeuge)
        )

    def all_object_ids(self) -> list[str]:
        ids = self.switchable_object_ids()
        for house_id, house in self.haeuser.items():
            ids.extend(f"{house_id}.{window_id}" for window_id in house.fenster)
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
            raise ValueError(f"Unbekanntes Objekt: {object_id}")
        if accessory < 0 or accessory > 255:
            raise ValueError("Adresse muss zwischen 0 und 255 liegen")
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
        if object_id in self.lampen:
            return "lampe"
        if object_id in self.haeuser:
            return "haus"
        if object_id in self.gruppen:
            return "gruppe"
        if object_id in self.sequenzen:
            return "sequenz"
        if object_id in self.signale:
            return "signal"
        if object_id in self.spezial:
            return "spezial"
        if object_id in self.fahrzeuge:
            return "fahrzeug"
        if "." in object_id:
            house_id, window_id = object_id.split(".", 1)
            house = self.haeuser.get(house_id)
            if house and window_id in house.fenster:
                return "fenster"
        return None

    def aspect_count(self, object_id: str) -> int:
        if object_id in self.signale:
            begriffe = self.signale[object_id].begriffe
            return max(begriffe) + 1 if begriffe else 2
        if object_id in self.fahrzeuge:
            modi = self.fahrzeuge[object_id].resolved_modi()
            return max(modi) + 1 if modi else 2
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

        for lamp_id, lamp in self.lampen.items():
            add(lamp.controller, lamp.leds, lamp_id, lamp.anteil)
        for house_id, house in self.haeuser.items():
            for window_id, window in house.fenster.items():
                add(house.controller, window.leds, f"{house_id}.{window_id}", window.anteil)
        for signal_id, signal in self.signale.items():
            for begriff in signal.begriffe.values():
                for idx in begriff.leds:
                    add(signal.controller, [idx], signal_id, begriff.anteil_of(idx))
        for spec_id, spec in self.spezial.items():
            add(spec.controller, spec.leds, spec_id, spec.anteil)
        for vehicle_id, vehicle in self.fahrzeuge.items():
            for channel in vehicle.kanaele.values():
                add(vehicle.controller, channel.leds, vehicle_id, channel.anteil)
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
            raise ValueError("Anzahl muss mindestens 1 sein")
        if first_shifted < 0:
            raise ValueError("Ungültige Einfügeposition")
        if wled_count < 1:
            raise ValueError("WLED-LED-Anzahl unbekannt – Controller zuerst übernehmen")
        current_max = self.max_led_index(controller)
        shifted_max = current_max + count if current_max >= first_shifted else current_max
        last_new = first_shifted + count - 1
        need = max(shifted_max, last_new) + 1
        if need > wled_count:
            raise ValueError(
                f"Nach dem Einfügen wären {need} LEDs nötig, WLED meldet aber nur {wled_count}. "
                f"Zuerst in WLED die LED-Anzahl auf mindestens {need} erhöhen."
            )
        changed = 0
        for lamp in self.lampen.values():
            if lamp.controller != controller:
                continue
            lamp.leds, n = shift_led_list(lamp.leds, first_shifted, count)
            changed += n
        for house in self.haeuser.values():
            if house.controller != controller:
                continue
            for window in house.fenster.values():
                window.leds, n = shift_led_list(window.leds, first_shifted, count)
                changed += n
        for signal in self.signale.values():
            if signal.controller != controller:
                continue
            for begriff in signal.begriffe.values():
                new_leds, n = shift_index_map(dict(begriff.leds), first_shifted, count)
                begriff.leds = {int(k): str(v) for k, v in new_leds.items()}
                changed += n
                if begriff.anteile:
                    new_anteile, _ = shift_index_map(dict(begriff.anteile), first_shifted, count)
                    begriff.anteile = {int(k): str(v) for k, v in new_anteile.items()}
        for spec in self.spezial.values():
            if spec.controller != controller:
                continue
            spec.leds, n = shift_led_list(spec.leds, first_shifted, count)
            changed += n
        for vehicle in self.fahrzeuge.values():
            if vehicle.controller != controller:
                continue
            for channel in vehicle.kanaele.values():
                channel.leds, n = shift_led_list(channel.leds, first_shifted, count)
                changed += n
        ctrl = self.controller_by_name(controller)
        if ctrl and ctrl.namen:
            moved: list[LedNameConfig] = []
            for label in ctrl.namen:
                von, bis = shift_span(label.von, label.bis, first_shifted, count)
                moved.append(label.model_copy(update={"von": von, "bis": bis}))
            ctrl.namen = moved
        return changed

    def delete_controller_leds(self, controller: str, first_removed: int, count: int) -> dict[str, int | list[str]]:
        """Entfernt `count` LEDs ab `first_removed` und zählt Folgeadressen herunter. Keine WLED-Sperre."""
        from bidib2wled.pixels import delete_index_range, delete_led_range, delete_span

        if count < 1:
            raise ValueError("Anzahl muss mindestens 1 sein")
        if first_removed < 0:
            raise ValueError("Ungültige Löschposition")
        emptied: list[str] = []

        def list_empty(obj_id: str, leds: list[int]) -> None:
            kept, _, _ = delete_led_range(leds, first_removed, count)
            if not kept:
                emptied.append(obj_id)

        for lamp_id, lamp in self.lampen.items():
            if lamp.controller == controller:
                list_empty(lamp_id, lamp.leds)
        for house_id, house in self.haeuser.items():
            if house.controller != controller:
                continue
            for window_id, window in house.fenster.items():
                list_empty(f"{house_id}.{window_id}", window.leds)
        for signal_id, signal in self.signale.items():
            if signal.controller != controller:
                continue
            for begriff_id, begriff in signal.begriffe.items():
                kept, _, _ = delete_index_range(dict(begriff.leds), first_removed, count)
                if not kept:
                    emptied.append(f"{signal_id}:{begriff.name or begriff_id}")
        for spec_id, spec in self.spezial.items():
            if spec.controller == controller:
                list_empty(spec_id, spec.leds)
        for vehicle_id, vehicle in self.fahrzeuge.items():
            if vehicle.controller != controller:
                continue
            for channel_id, channel in vehicle.kanaele.items():
                list_empty(f"{vehicle_id}.{channel_id}", channel.leds)
        if emptied:
            names = ", ".join(emptied)
            raise ValueError(
                f"Diese LEDs können nicht entfernt werden, sonst hätten folgende Objekte keine LED mehr: {names}. "
                "Zuerst die Objekte ändern oder löschen."
            )

        shifted = 0
        dropped = 0
        for lamp in self.lampen.values():
            if lamp.controller != controller:
                continue
            lamp.leds, n, d = delete_led_range(lamp.leds, first_removed, count)
            shifted += n
            dropped += d
        for house in self.haeuser.values():
            if house.controller != controller:
                continue
            for window in house.fenster.values():
                window.leds, n, d = delete_led_range(window.leds, first_removed, count)
                shifted += n
                dropped += d
        for signal in self.signale.values():
            if signal.controller != controller:
                continue
            for begriff in signal.begriffe.values():
                new_leds, n, d = delete_index_range(dict(begriff.leds), first_removed, count)
                begriff.leds = {int(k): str(v) for k, v in new_leds.items()}
                shifted += n
                dropped += d
                if begriff.anteile:
                    new_anteile, _, _ = delete_index_range(dict(begriff.anteile), first_removed, count)
                    begriff.anteile = {int(k): str(v) for k, v in new_anteile.items()}
        for spec in self.spezial.values():
            if spec.controller != controller:
                continue
            spec.leds, n, d = delete_led_range(spec.leds, first_removed, count)
            shifted += n
            dropped += d
        for vehicle in self.fahrzeuge.values():
            if vehicle.controller != controller:
                continue
            for channel in vehicle.kanaele.values():
                channel.leds, n, d = delete_led_range(channel.leds, first_removed, count)
                shifted += n
                dropped += d
        ctrl = self.controller_by_name(controller)
        if ctrl and ctrl.namen:
            kept: list[LedNameConfig] = []
            for label in ctrl.namen:
                span = delete_span(label.von, label.bis, first_removed, count)
                if span is None:
                    continue
                kept.append(label.model_copy(update={"von": span[0], "bis": span[1]}))
            ctrl.namen = kept
        return {"shifted": shifted, "dropped": dropped}

    def object_usage(self) -> dict[str, list[str]]:
        """Objekt-ID → Gruppen/Sequenzen, die das Objekt referenzieren."""
        usage: dict[str, list[str]] = {}

        def add(obj_id: str, owner: str) -> None:
            usage.setdefault(obj_id, []).append(owner)

        for group_id, group in self.gruppen.items():
            for member in group.mitglieder:
                add(member, group_id)
        for seq_id, seq in self.sequenzen.items():
            for group_id in seq.gruppen:
                add(group_id, seq_id)
        return usage


def host_setup_info(kind: str, accessory: int | None) -> list[dict[str, str]]:
    """Kurzanleitung je Steuerungssoftware (Info-Spalte). Weitere Programme als Builder ergänzen."""
    builders = (_rocrail_setup,)
    return [row for build in builders if (row := build(kind, accessory))]


def _rocrail_setup(kind: str, accessory: int | None) -> dict[str, str] | None:
    if accessory is None:
        if kind == "fenster":
            return {
                "program": "Rocrail",
                "text": "keine eigene Adresse – das Haus schalten (Ausgang, Port 0, Zubehör an, Protokoll Default)",
            }
        return None
    rocrail = accessory + 1
    base = f"Adresse {rocrail} (Adresse+1), Port 0, Bus 0, Protokoll Default, Zubehör an"
    if kind == "signal":
        return {"program": "Rocrail", "text": f"Signal: {base}; Begriffe wie in der Auswahl"}
    if kind == "fahrzeug":
        return {
            "program": "Rocrail",
            "text": f"Signal: {base}; Modi wie in der Auswahl (0=Aus)",
        }
    return {"program": "Rocrail", "text": f"Ausgang: {base}"}


def default_config() -> AppConfig:
    return AppConfig()


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        return default_config()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("Konfiguration muss ein YAML-Objekt sein")
    return AppConfig.model_validate(raw)


def _omit_empty_anteile(payload: Any) -> Any:
    """YAML darf kein `anteile: null` schreiben – das hat den Start blockiert."""
    if not isinstance(payload, dict):
        return payload
    signale = payload.get("signale")
    if isinstance(signale, dict):
        for signal in signale.values():
            if not isinstance(signal, dict):
                continue
            begriffe = signal.get("begriffe")
            if not isinstance(begriffe, dict):
                continue
            for begriff in begriffe.values():
                if isinstance(begriff, dict) and not begriff.get("anteile"):
                    begriff.pop("anteile", None)
    for vehicle in (payload.get("fahrzeuge") or {}).values():
        if not isinstance(vehicle, dict):
            continue
        for channel in (vehicle.get("kanaele") or {}).values():
            if isinstance(channel, dict) and channel.get("schritte") in (None, "auto"):
                channel.pop("schritte", None)
    for ctrl in payload.get("controller") or []:
        if isinstance(ctrl, dict) and not ctrl.get("namen"):
            ctrl.pop("namen", None)
    return payload


def save_config(path: Path, config: AppConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)
    payload = _omit_empty_anteile(config.model_dump(by_alias=True, exclude_none=True))
    text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, default_flow_style=False)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
