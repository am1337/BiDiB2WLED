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


class LampConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    controller: str
    leds: list[int] = Field(min_length=1)
    farbe: str = "FFFFFF"
    helligkeit: int = Field(default=180, ge=0, le=255)

    @field_validator("farbe")
    @classmethod
    def _color(cls, value: str) -> str:
        cleaned = value.strip().lstrip("#").upper()
        if not re.fullmatch(r"[0-9A-F]{6}", cleaned):
            raise ValueError(f"Farbe muss RRGGBB sein: {value!r}")
        return cleaned


class FensterConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    leds: list[int] = Field(min_length=1)
    farbe: str = "FFFFFF"
    helligkeit: int = Field(default=180, ge=0, le=255)

    @field_validator("farbe")
    @classmethod
    def _color(cls, value: str) -> str:
        return LampConfig._color(value)


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

    @field_validator("leds")
    @classmethod
    def _colors(cls, value: dict[int, str]) -> dict[int, str]:
        return {int(idx): LampConfig._color(color) for idx, color in value.items()}


class SignalConfig(BaseModel):
    controller: str
    begriffe: dict[int, SignalAspectConfig]


class ControllerConfig(BaseModel):
    name: str
    mdns: str | None = None
    mac: str | None = None
    ip: str | None = None
    leds: int | None = None
    port: int = 80

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


class RocrailConfig(BaseModel):
    aktiv: bool = False
    host: str = "127.0.0.1"
    port: int = 8051
    id_praefix: str = Field(default="wled-", alias="id-praefix")


class AdapterConfig(BaseModel):
    netbidib: NetBidibConfig = Field(default_factory=NetBidibConfig)
    rocrail: RocrailConfig = Field(default_factory=RocrailConfig)


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
        known = set(self.lampen) | set(self.haeuser) | set(self.gruppen) | set(self.sequenzen) | set(self.signale)
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

    def switchable_object_ids(self) -> list[str]:
        """Objekte mit eigener BiDiB-Accessory-Nummer (Fenster nur nach Handzuweisung)."""
        return list(self.lampen) + list(self.haeuser) + list(self.gruppen) + list(self.sequenzen) + list(self.signale)

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
        return 2


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


def save_config(path: Path, config: AppConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)
    payload = config.model_dump(by_alias=True, exclude_none=True)
    text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, default_flow_style=False)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
