"""Map legacy German YAML/API keys and enum values to English before validation."""

from __future__ import annotations

from typing import Any

_TOP = {
    "lampen": "lamps",
    "haeuser": "houses",
    "gruppen": "groups",
    "sequenzen": "sequences",
    "signale": "signals",
    "spezial": "special",
    "fahrzeuge": "vehicles",
    "erkennung": "discovery",
}

_NETBIDIB = {
    "aktiv": "enabled",
    "modus": "mode",
    "knotenname": "node_name",
}

_CLIENT = {
    "aktiv": "enabled",
    "id-praefix": "id_prefix",
    "id_praefix": "id_prefix",
}

_DISCOVERY = {
    "intervall": "interval",
}

_LAMP = {
    "farbe": "color",
    "helligkeit": "brightness",
    "anteil": "channel",
}

_HOUSE = {
    "fenster": "windows",
    "einschalten": "turn_on",
    "verzoegerung": "delay",
    "nacht-wahrscheinlichkeit": "night_probability",
    "nacht_wahrscheinlichkeit": "night_probability",
}

_GROUP = {
    "mitglieder": "members",
}

_SEQUENCE = {
    "gruppen": "groups",
    "reihenfolge": "order",
    "verzoegerung": "delay",
}

_SIGNAL = {
    "begriffe": "aspects",
}

_ASPECT = {
    "anteile": "channels",
}

_VEHICLE = {
    "kanaele": "channels",
    "modi": "modes",
    "blink_periode": "blink_period",
    "rundum_schritt": "beacon_step",
}

_VEHICLE_CHANNEL = {
    "anteil": "channel",
    "farbe": "color",
    "helligkeit": "brightness",
    "art": "type",
    "schritte": "steps",
}

_VEHICLE_MODE = {
    "kanaele": "channels",
}

_SPECIAL = {
    "effekt": "effect",
    "geschwindigkeit": "speed",
    "intensitaet": "intensity",
    "farbe": "color",
    "helligkeit": "brightness",
    "anteil": "channel",
}

_CONTROLLER = {
    "namen": "names",
}

_LED_NAME = {
    "von": "start",
    "bis": "end",
    "anteil": "channel",
}

_TURN_ON = {
    "sofort": "immediate",
    "nacheinander": "sequential",
    "zufaellig": "random",
    "zufällig": "random",
    "immediate": "immediate",
    "sequential": "sequential",
    "random": "random",
}

_ORDER = {
    "definiert": "defined",
    "zufaellig": "random",
    "zufällig": "random",
    "defined": "defined",
    "random": "random",
}

_LIGHT_TYPE = {
    "dauer": "continuous",
    "dauerlicht": "continuous",
    "continuous": "continuous",
    "steady": "continuous",
    "blinker": "blinker",
    "warnblinker": "blinker",
    "rundum": "beacon",
    "rundumlicht": "beacon",
    "beacon": "beacon",
    "blitz": "strobe",
    "strobe": "strobe",
    "doppelblitz": "double_strobe",
    "double": "double_strobe",
    "double_strobe": "double_strobe",
}

_STEPS = {
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


def _rename(data: Any, mapping: dict[str, str]) -> Any:
    if not isinstance(data, dict):
        return data
    out: dict[str, Any] = {}
    for key, value in data.items():
        out[mapping.get(str(key), key)] = value
    return out


def _map_objects(data: Any, mapper) -> Any:
    if not isinstance(data, dict):
        return data
    return {key: mapper(value) for key, value in data.items()}


def _lamp(item: Any) -> Any:
    return _rename(item, _LAMP)


def _window(item: Any) -> Any:
    return _rename(item, _LAMP)


def _house(item: Any) -> Any:
    item = _rename(item, _HOUSE)
    if not isinstance(item, dict):
        return item
    if "windows" in item:
        item["windows"] = _map_objects(item["windows"], _window)
    if isinstance(item.get("turn_on"), str):
        item["turn_on"] = _TURN_ON.get(item["turn_on"].strip().lower().replace("ä", "ae"), item["turn_on"])
    return item


def _group(item: Any) -> Any:
    return _rename(item, _GROUP)


def _sequence(item: Any) -> Any:
    item = _rename(item, _SEQUENCE)
    if not isinstance(item, dict):
        return item
    order = item.get("order")
    if isinstance(order, str):
        item["order"] = _ORDER.get(order.strip().lower().replace("ä", "ae"), order)
    return item


def _aspect(item: Any) -> Any:
    item = _rename(item, _ASPECT)
    if isinstance(item, dict) and item.get("channels") is None:
        item.pop("channels", None)
    return item


def _signal(item: Any) -> Any:
    item = _rename(item, _SIGNAL)
    if not isinstance(item, dict):
        return item
    aspects = item.get("aspects")
    if isinstance(aspects, dict):
        item["aspects"] = {key: _aspect(value) for key, value in aspects.items()}
    return item


def _vehicle_channel(item: Any) -> Any:
    item = _rename(item, _VEHICLE_CHANNEL)
    if not isinstance(item, dict):
        return item
    if isinstance(item.get("type"), str):
        raw = item["type"].strip().lower().replace("ü", "ue")
        item["type"] = _LIGHT_TYPE.get(raw, raw)
    if isinstance(item.get("steps"), str):
        raw = item["steps"].strip().lower().replace("ä", "ae")
        item["steps"] = _STEPS.get(raw, raw)
    return item


def _vehicle_mode(item: Any) -> Any:
    return _rename(item, _VEHICLE_MODE)


def _vehicle(item: Any) -> Any:
    item = _rename(item, _VEHICLE)
    if not isinstance(item, dict):
        return item
    if "channels" in item:
        item["channels"] = _map_objects(item["channels"], _vehicle_channel)
    modes = item.get("modes")
    if isinstance(modes, dict):
        item["modes"] = {key: _vehicle_mode(value) for key, value in modes.items()}
    return item


def _special(item: Any) -> Any:
    return _rename(item, _SPECIAL)


def _led_name(item: Any) -> Any:
    item = _rename(item, _LED_NAME)
    if not isinstance(item, dict):
        return item
    if "led" in item and "start" not in item:
        led = item.pop("led")
        item["start"] = led
        item.setdefault("end", led)
    return item


def _controller(item: Any) -> Any:
    item = _rename(item, _CONTROLLER)
    if not isinstance(item, dict):
        return item
    names = item.get("names")
    if isinstance(names, list):
        item["names"] = [_led_name(value) for value in names]
    return item


def migrate_legacy_config(data: Any) -> Any:
    """Rewrite German keys/values from older configs into the English schema."""
    if not isinstance(data, dict):
        return data
    data = dict(data)
    data = _rename(data, _TOP)
    adapter = data.get("adapter")
    if isinstance(adapter, dict):
        adapter = dict(adapter)
        if "rocrail" in adapter and "client" not in adapter:
            adapter["client"] = adapter.pop("rocrail")
        elif "rocrail" in adapter:
            adapter.pop("rocrail", None)
        if isinstance(adapter.get("netbidib"), dict):
            adapter["netbidib"] = _rename(adapter["netbidib"], _NETBIDIB)
        if isinstance(adapter.get("client"), dict):
            adapter["client"] = _rename(adapter["client"], _CLIENT)
        data["adapter"] = adapter
    if "discovery" in data:
        data["discovery"] = _rename(data["discovery"], _DISCOVERY)
    if isinstance(data.get("controller"), list):
        data["controller"] = [_controller(item) for item in data["controller"]]
    data["lamps"] = _map_objects(data.get("lamps") or {}, _lamp)
    data["houses"] = _map_objects(data.get("houses") or {}, _house)
    data["groups"] = _map_objects(data.get("groups") or {}, _group)
    data["sequences"] = _map_objects(data.get("sequences") or {}, _sequence)
    data["signals"] = _map_objects(data.get("signals") or {}, _signal)
    data["special"] = _map_objects(data.get("special") or {}, _special)
    data["vehicles"] = _map_objects(data.get("vehicles") or {}, _vehicle)
    return data
