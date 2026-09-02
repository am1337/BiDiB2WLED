import json
from pathlib import Path

import pytest

from bidib2wled.config import (
    AppConfig,
    ControllerConfig,
    VehicleConfig,
    format_led_name_line,
    load_config,
    normalize_mac,
    parse_delay_range,
    parse_duration,
    parse_led_name_line,
    save_config,
)


def test_mac_from_wled():
    assert normalize_mac("4cc382c3d6e0") == "4c:c3:82:c3:d6:e0"
    assert normalize_mac("4C:C3:82:C3:D6:E0") == "4c:c3:82:c3:d6:e0"
    assert ControllerConfig(name="dorf", mac="4cc382c3d6e0").mac == "4c:c3:82:c3:d6:e0"


def test_duration():
    assert parse_duration("10s") == 10
    assert parse_duration(2.5) == 2.5
    assert parse_delay_range(["2s", "8s"]) == (2.0, 8.0)


def test_example_config(tmp_path):
    text = """
adapter:
  netbidib:
    aktiv: true
    knotenname: Test
controller:
  - name: dorf
    ip: 127.0.0.1
    leds: 20
lampen:
  laterne-1: { controller: dorf, leds: [0], farbe: "FFB060" }
haeuser:
  haus-a:
    controller: dorf
    fenster:
      wz: { leds: [2, 3] }
gruppen:
  strasse:
    mitglieder: [laterne-1, haus-a]
sequenzen:
  seq-nacht:
    gruppen: [strasse]
    verzoegerung: [0.01s, 0.02s]
signale:
  sig:
    controller: dorf
    begriffe:
      0: { name: Halt, leds: { 5: "FF0000" } }
      1: { name: Fahrt, leds: { 6: "00FF00" } }
spezial:
  kamin:
    controller: dorf
    leds: [8, 9]
    effekt: 10
    palette: 0
    geschwindigkeit: 90
    intensitaet: 180
    farbe: "FF6A00"
fahrzeuge:
  pkw-rot:
    controller: dorf
    kanaele:
      licht: { leds: [12], anteil: rgb, farbe: "FFFFCC", art: dauer }
      blinker-l: { leds: [13], anteil: r, farbe: "FF8000", art: blinker }
      blinker-r: { leds: [13], anteil: g, farbe: "FF8000", art: blinker }
"""
    path = tmp_path / "c.yaml"
    path.write_text(text, encoding="utf-8")
    cfg = load_config(path)
    assert cfg.lampen["laterne-1"].farbe == "FFB060"
    assert "haus-a.wz" in cfg.all_object_ids()
    assert cfg.object_kind("laterne-1") == "lamp"
    assert cfg.object_kind("haus-a") == "house"
    assert cfg.object_kind("haus-a.wz") == "window"
    assert cfg.object_kind("sig") == "signal"
    assert cfg.object_kind("kamin") == "special"
    assert cfg.object_kind("pkw-rot") == "vehicle"
    assert cfg.aspect_count("sig") == 2
    assert cfg.aspect_count("pkw-rot") == 3
    assert "kamin" in cfg.switchable_object_ids()
    assert "pkw-rot" in cfg.switchable_object_ids()
    usage = cfg.led_usage()
    assert usage["dorf"]["0"] == ["laterne-1"]
    assert "kamin" in usage["dorf"]["8"]
    assert "pkw-rot" in usage["dorf"]["12"]
    assert "pkw-rot" in usage["dorf"]["13"]
    assert cfg.object_usage()["laterne-1"] == ["strasse"]
    assert cfg.object_usage()["strasse"] == ["seq-nacht"]


def test_accessory_map_keeps_fixed_and_fills_new():
    cfg = AppConfig.model_validate(
        {
            "adapter": {"netbidib": {"accessories": {0: "laterne-1"}}},
            "controller": [{"name": "dorf", "ip": "127.0.0.1", "leds": 20}],
            "lampen": {"laterne-1": {"controller": "dorf", "leds": [0]}},
            "haeuser": {
                "haus-a": {"controller": "dorf", "fenster": {"wz": {"leds": [2]}}},
            },
            "signale": {
                "sig": {
                    "controller": "dorf",
                    "begriffe": {0: {"name": "Halt", "leds": {5: "FF0000"}}},
                }
            },
        }
    )
    mapping = cfg.accessory_map()
    assert mapping[0] == "laterne-1"
    assert mapping[1] == "haus-a"
    assert mapping[2] == "sig"
    assert "haus-a.wz" not in mapping.values()
    cfg.ensure_accessories()
    assert cfg.adapter.netbidib.accessories[2] == "sig"


def test_set_accessory_swaps():
    cfg = AppConfig.model_validate(
        {
            "controller": [{"name": "dorf", "ip": "127.0.0.1", "leds": 8}],
            "lampen": {
                "lampe-a": {"controller": "dorf", "leds": [0]},
                "lampe-b": {"controller": "dorf", "leds": [1]},
            },
        }
    )
    cfg.ensure_accessories()
    assert cfg.adapter.netbidib.accessories == {0: "lampe-a", 1: "lampe-b"}
    cfg.set_accessory("lampe-b", 0)
    assert cfg.adapter.netbidib.accessories[0] == "lampe-b"
    assert cfg.adapter.netbidib.accessories[1] == "lampe-a"
    cfg.set_accessory("lampe-b", 4)
    assert cfg.adapter.netbidib.accessories[4] == "lampe-b"
    assert cfg.adapter.netbidib.accessories[1] == "lampe-a"


def test_host_setup_info_rocrail_uses_plus_one():
    from bidib2wled.config import host_setup_info

    lamp = host_setup_info("lamp", 0)
    assert lamp[0]["program"] == "Rocrail"
    assert "address 1 (address+1)" in lamp[0]["text"]
    signal = host_setup_info("signal", 2)
    assert signal[0]["text"].startswith("Signal:")
    assert "address 3 (address+1)" in signal[0]["text"]
    window = host_setup_info("window", None)
    assert "house" in window[0]["text"].lower()
    vehicle = host_setup_info("vehicle", 4)
    assert vehicle[0]["text"].startswith("Signal:")
    assert "modes" in vehicle[0]["text"].lower()
    assert "address 5 (address+1)" in vehicle[0]["text"]


def test_adapter_client_replaces_rocrail():
    cfg = AppConfig.model_validate(
        {
            "adapter": {
                "rocrail": {"aktiv": False, "host": "10.0.0.2", "port": 8051, "id-praefix": "wled-"},
            }
        }
    )
    assert not hasattr(cfg.adapter, "rocrail")
    assert cfg.adapter.client.host == "10.0.0.2"
    dumped = cfg.model_dump(by_alias=True)
    assert "client" in dumped["adapter"]
    assert "rocrail" not in dumped["adapter"]


def test_unknown_controller_rejected():
    try:
        AppConfig.model_validate({"lampen": {"x": {"controller": "nein", "leds": [0]}}})
    except Exception as exc:
        assert "unknown controller" in str(exc)
    else:
        raise AssertionError("sollte fehlschlagen")


def test_vehicle_anteil_and_default_modi():
    from bidib2wled.config import VehicleConfig, default_vehicle_modi

    cfg = AppConfig.model_validate(
        {
            "controller": [{"name": "dorf", "ip": "127.0.0.1", "leds": 40}],
            "fahrzeuge": {
                "lf": {
                    "controller": "dorf",
                    "kanaele": {
                        "licht": {"leds": [1], "anteil": "rot", "art": "dauerlicht"},
                        "blinker": {"leds": [1], "anteil": "g", "art": "warnblinker"},
                        "rundum": {"leds": [2], "anteil": "alle", "art": "rundumlicht"},
                    },
                }
            },
        }
    )
    vehicle = cfg.fahrzeuge["lf"]
    assert vehicle.kanaele["licht"].anteil == "r"
    assert vehicle.kanaele["licht"].art == "continuous"
    assert vehicle.kanaele["blinker"].art == "blinker"
    assert vehicle.kanaele["rundum"].anteil == "rgb"
    modi = vehicle.resolved_modi()
    assert modi[0].name == "Off"
    assert modi[1].name == "Lights"
    assert modi[2].name == "Hazards"
    assert modi[3].name == "Emergency"
    assert "rundum" in modi[3].kanaele
    assert default_vehicle_modi(vehicle.kanaele)[2].kanaele == ["licht", "blinker"]


def test_vehicle_rundum_schritte_aliases_and_yaml_omit_auto(tmp_path: Path):
    cfg = AppConfig.model_validate(
        {
            "controller": [{"name": "dorf", "ip": "127.0.0.1", "leds": 8}],
            "fahrzeuge": {
                "fw": {
                    "controller": "dorf",
                    "kanaele": {
                        "klein": {
                            "leds": [1],
                            "anteil": "rgb",
                            "art": "rundum",
                            "schritte": "anteile",
                        },
                        "balken": {"leds": [2, 3], "art": "rundum"},
                    },
                }
            },
        }
    )
    assert cfg.fahrzeuge["fw"].kanaele["klein"].schritte == "channels"
    assert cfg.fahrzeuge["fw"].kanaele["balken"].schritte == "auto"
    save_config(tmp_path / "c.yaml", cfg)
    text = (tmp_path / "c.yaml").read_text(encoding="utf-8")
    assert "steps: channels" in text
    assert "steps: auto" not in text
    assert "schritte:" not in text
    assert "kanaele:" not in text


def test_vehicle_unknown_mode_channel_rejected():
    try:
        VehicleConfig.model_validate(
            {
                "controller": "dorf",
                "kanaele": {"licht": {"leds": [0], "art": "dauer"}},
                "modi": {1: {"name": "Licht", "kanaele": ["gibt-es-nicht"]}},
            }
        )
    except Exception as exc:
        assert "unknown channel" in str(exc)
    else:
        raise AssertionError("sollte fehlschlagen")


def test_lamp_anteil_rot_parses():
    cfg = AppConfig.model_validate(
        {
            "controller": [{"name": "c", "ip": "127.0.0.1", "leds": 8}],
            "lampen": {"l1": {"controller": "c", "leds": [0], "anteil": "rot"}},
        }
    )
    assert cfg.lampen["l1"].anteil == "r"
    usage = cfg.led_channel_usage()
    assert usage["c"]["0"]["r"] == ["l1"]
    assert usage["c"]["0"]["g"] == []


def test_shift_leds_after_fifth_inserts_three():
    cfg = AppConfig.model_validate(
        {
            "controller": [{"name": "c", "ip": "127.0.0.1", "leds": 7}],
            "lampen": {
                "l1": {"controller": "c", "leds": [0]},
                "l5": {"controller": "c", "leds": [4]},
                "l6": {"controller": "c", "leds": [5]},
                "l7": {"controller": "c", "leds": [6]},
            },
            "haeuser": {
                "h1": {
                    "controller": "c",
                    "fenster": {"f": {"leds": [5], "anteil": "g"}},
                }
            },
            "signale": {
                "s1": {
                    "controller": "c",
                    "begriffe": {
                        0: {
                            "name": "Hp0",
                            "leds": {5: "FF0000"},
                            "anteile": {5: "r"},
                        }
                    },
                }
            },
            "spezial": {"sp1": {"controller": "c", "leds": [5], "anteil": "b"}},
            "fahrzeuge": {
                "v1": {
                    "controller": "c",
                    "kanaele": {"k": {"leds": [6], "anteil": "r"}},
                }
            },
        }
    )
    shifted = cfg.shift_controller_leds("c", first_shifted=5, count=3, wled_count=10)
    assert shifted == 6
    assert cfg.lampen["l1"].leds == [0]
    assert cfg.lampen["l5"].leds == [4]
    assert cfg.lampen["l6"].leds == [8]
    assert cfg.lampen["l7"].leds == [9]
    assert cfg.haeuser["h1"].fenster["f"].leds == [8]
    assert cfg.signale["s1"].begriffe[0].leds[8] == "FF0000"
    assert cfg.signale["s1"].begriffe[0].anteile[8] == "r"
    assert 5 not in cfg.signale["s1"].begriffe[0].leds
    assert 5 not in cfg.signale["s1"].begriffe[0].anteile
    assert cfg.spezial["sp1"].leds == [8]
    assert cfg.fahrzeuge["v1"].kanaele["k"].leds == [9]
    usage = cfg.led_usage()
    assert "5" not in usage["c"]
    assert "8" in usage["c"]
    assert "9" in usage["c"]


def test_shift_leds_rejected_when_wled_too_small():
    cfg = AppConfig.model_validate(
        {
            "controller": [{"name": "c", "ip": "127.0.0.1", "leds": 7}],
            "lampen": {"l6": {"controller": "c", "leds": [5]}},
        }
    )
    with pytest.raises(ValueError, match="WLED"):
        cfg.shift_controller_leds("c", first_shifted=5, count=3, wled_count=7)


def test_shift_leds_at_start():
    cfg = AppConfig.model_validate(
        {
            "controller": [{"name": "c", "ip": "127.0.0.1", "leds": 4}],
            "lampen": {"l1": {"controller": "c", "leds": [0, 1]}},
        }
    )
    shifted = cfg.shift_controller_leds("c", first_shifted=0, count=2, wled_count=6)
    assert shifted == 2
    assert cfg.lampen["l1"].leds == [2, 3]


def test_delete_leds_after_fifth_removes_three():
    cfg = AppConfig.model_validate(
        {
            "controller": [{"name": "c", "ip": "127.0.0.1", "leds": 10}],
            "lampen": {
                "l1": {"controller": "c", "leds": [0]},
                "l5": {"controller": "c", "leds": [4]},
                "l6": {"controller": "c", "leds": [8]},
                "l7": {"controller": "c", "leds": [9]},
            },
            "haeuser": {
                "h1": {"controller": "c", "fenster": {"f": {"leds": [8], "anteil": "g"}}}
            },
            "signale": {
                "s1": {
                    "controller": "c",
                    "begriffe": {0: {"name": "Hp0", "leds": {8: "FF0000"}, "anteile": {8: "r"}}},
                }
            },
            "spezial": {"sp1": {"controller": "c", "leds": [8], "anteil": "b"}},
            "fahrzeuge": {
                "v1": {"controller": "c", "kanaele": {"k": {"leds": [9], "anteil": "r"}}}
            },
        }
    )
    result = cfg.delete_controller_leds("c", first_removed=5, count=3)
    assert result["shifted"] == 6
    assert result["dropped"] == 0
    assert cfg.lampen["l1"].leds == [0]
    assert cfg.lampen["l5"].leds == [4]
    assert cfg.lampen["l6"].leds == [5]
    assert cfg.lampen["l7"].leds == [6]
    assert cfg.haeuser["h1"].fenster["f"].leds == [5]
    assert cfg.signale["s1"].begriffe[0].leds[5] == "FF0000"
    assert cfg.signale["s1"].begriffe[0].anteile[5] == "r"
    assert 8 not in cfg.signale["s1"].begriffe[0].leds
    assert cfg.spezial["sp1"].leds == [5]
    assert cfg.fahrzeuge["v1"].kanaele["k"].leds == [6]


def test_delete_leds_allowed_when_wled_already_smaller():
    cfg = AppConfig.model_validate(
        {
            "controller": [{"name": "c", "ip": "127.0.0.1", "leds": 10}],
            "lampen": {
                "l6": {"controller": "c", "leds": [8]},
                "l7": {"controller": "c", "leds": [9]},
            },
        }
    )
    result = cfg.delete_controller_leds("c", first_removed=5, count=2)
    assert result["shifted"] == 2
    assert cfg.lampen["l6"].leds == [6]
    assert cfg.lampen["l7"].leds == [7]
    result = cfg.delete_controller_leds("c", first_removed=8, count=1)
    assert cfg.lampen["l6"].leds == [6]
    assert cfg.lampen["l7"].leds == [7]


def test_delete_leds_rejected_when_object_would_be_empty():
    cfg = AppConfig.model_validate(
        {
            "controller": [{"name": "c", "ip": "127.0.0.1", "leds": 7}],
            "lampen": {"l6": {"controller": "c", "leds": [5]}},
        }
    )
    with pytest.raises(ValueError, match="no LED left"):
        cfg.delete_controller_leds("c", first_removed=5, count=3)
    assert cfg.lampen["l6"].leds == [5]


def test_delete_leds_drops_only_removed_indices():
    cfg = AppConfig.model_validate(
        {
            "controller": [{"name": "c", "ip": "127.0.0.1", "leds": 10}],
            "lampen": {"mix": {"controller": "c", "leds": [4, 5, 8]}},
        }
    )
    result = cfg.delete_controller_leds("c", first_removed=5, count=3)
    assert cfg.lampen["mix"].leds == [4, 5]
    assert result["dropped"] == 1
    assert result["shifted"] == 1

def test_empty_signal_anteile_omitted_from_dump():
    cfg = AppConfig.model_validate(
        {
            "controller": [{"name": "c", "ip": "127.0.0.1", "leds": 8}],
            "signale": {
                "s1": {
                    "controller": "c",
                    "begriffe": {0: {"name": "Halt", "leds": {1: "FF0000"}}},
                }
            },
        }
    )
    dumped = cfg.model_dump(by_alias=False, exclude_none=True)
    aspect = dumped["signals"]["s1"]["aspects"][0]
    assert aspect.get("channels") in (None, {})


def test_yaml_null_anteile_loads_signal_with_space_in_id(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
controller:
  - name: dorf
    ip: 127.0.0.1
    leds: 20
signale:
  signal 2:
    controller: dorf
    begriffe:
      0:
        name: Halt
        leds:
          12: "FF0000"
        anteile:
      1:
        name: Fahrt
        leds:
          14: "00FF00"
        anteile: null
""",
        encoding="utf-8",
    )
    cfg = load_config(path)
    halt = cfg.signale["signal 2"].begriffe[0]
    fahrt = cfg.signale["signal 2"].begriffe[1]
    assert halt.name == "Halt"
    assert halt.anteile == {}
    assert fahrt.name == "Fahrt"
    assert fahrt.anteile == {}
    save_config(path, cfg)
    text = path.read_text(encoding="utf-8")
    assert "anteile:" not in text
    assert "signale:" not in text
    assert "signals:" in text
    again = load_config(path)
    assert again.signale["signal 2"].begriffe[0].leds[12] == "FF0000"


def test_config_roundtrip_allows_null_signal_anteile_when_saving_special():
    """GET dump serializes empty anteile as null; Speichern muss das wieder einlesen."""
    cfg = AppConfig.model_validate(
        {
            "controller": [{"name": "dorf", "ip": "127.0.0.1", "leds": 20}],
            "signale": {
                "sig": {
                    "controller": "dorf",
                    "begriffe": {0: {"name": "Halt", "leds": {5: "FF0000"}}},
                }
            },
        }
    )
    dumped = json.loads(json.dumps(cfg.model_dump(by_alias=False)))
    dumped["signals"]["sig"]["aspects"]["0"]["channels"] = None
    dumped["special"] = {
        "kamin": {
            "controller": "dorf",
            "leds": [8],
            "effect": 10,
            "palette": 0,
            "speed": 128,
            "intensity": 180,
            "color": "FF6A00",
            "channel": "rgb",
        }
    }
    again = AppConfig.model_validate(dumped)
    assert again.signale["sig"].begriffe[0].anteile == {}
    assert again.spezial["kamin"].effekt == 10


def test_signal_same_led_two_color_channels_roundtrip():
    cfg = AppConfig.model_validate(
        {
            "controller": [{"name": "c", "ip": "127.0.0.1", "leds": 8}],
            "signale": {
                "s1": {
                    "controller": "c",
                    "begriffe": {
                        0: {
                            "name": "Halt",
                            "leds": {5: "FF0000"},
                            "anteile": {5: "r"},
                        },
                        1: {
                            "name": "Fahrt",
                            "leds": {5: "00FF00"},
                            "anteile": {5: "g"},
                        },
                    },
                }
            },
        }
    )
    halt = cfg.signale["s1"].begriffe[0]
    fahrt = cfg.signale["s1"].begriffe[1]
    assert halt.leds[5] == "FF0000"
    assert halt.anteile[5] == "r"
    assert fahrt.leds[5] == "00FF00"
    assert fahrt.anteile[5] == "g"
    dumped = cfg.model_dump(by_alias=False, exclude_none=True)
    aspects = dumped["signals"]["s1"]["aspects"]
    assert aspects[0]["leds"][5] == "FF0000"
    assert aspects[0]["channels"][5] == "r"
    assert aspects[1]["leds"][5] == "00FF00"
    assert aspects[1]["channels"][5] == "g"
    again = AppConfig.model_validate(dumped)
    assert again.signale["s1"].begriffe[0].anteil_of(5) == "r"
    assert again.signale["s1"].begriffe[1].anteil_of(5) == "g"


def test_parse_led_name_lines():
    assert parse_led_name_line("LED1 = Straßenlaterne") == (1, 1, "rgb", "Straßenlaterne")
    assert parse_led_name_line("3-7 Haus3") == (3, 7, "rgb", "Haus3")
    assert parse_led_name_line("LED3-7=Haus3") == (3, 7, "rgb", "Haus3")
    assert parse_led_name_line("12r=Halt") == (12, 12, "r", "Halt")
    assert parse_led_name_line("12 rot = Halt") == (12, 12, "r", "Halt")
    assert parse_led_name_line("12g:Fahrt") == (12, 12, "g", "Fahrt")
    assert parse_led_name_line("# Kommentar") is None
    assert parse_led_name_line("") is None
    assert format_led_name_line(1, 1, "rgb", "Straßenlaterne") == "1 = Straßenlaterne"
    assert format_led_name_line(3, 7, "rgb", "Haus3") == "3-7 = Haus3"
    assert format_led_name_line(12, 12, "r", "Halt") == "12r = Halt"


def test_led_names_yaml_and_labels(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
controller:
  - name: dorf
    ip: 127.0.0.1
    leds: 20
    namen:
      - { led: 0, name: Straßenlaterne }
      - { von: 2, bis: 6, name: Haus3 }
      - { led: 11, anteil: r, name: Halt }
      - { led: 11, anteil: g, name: Fahrt }
lampen:
  laterne: { controller: dorf, leds: [0] }
""",
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.led_label("dorf", 0) == "Straßenlaterne"
    assert cfg.led_label("dorf", 4) == "Haus3"
    assert cfg.led_label("dorf", 11, "r") == "Halt / Fahrt"
    assert cfg.led_label("dorf", 11, "g") == "Halt / Fahrt"
    assert cfg.led_label("dorf", 11, "rgb") == "Halt / Fahrt"
    assert cfg.led_label("dorf", 11, "b") == "Halt / Fahrt"
    save_config(path, cfg)
    text = path.read_text(encoding="utf-8")
    assert "Straßenlaterne" in text
    again = load_config(path)
    assert again.led_label("dorf", 0) == "Straßenlaterne"


def test_led_names_move_with_insert_and_delete():
    cfg = AppConfig.model_validate(
        {
            "controller": [
                {
                    "name": "c",
                    "ip": "127.0.0.1",
                    "leds": 20,
                    "namen": [
                        {"led": 0, "name": "Laterne"},
                        {"von": 2, "bis": 6, "name": "Haus3"},
                        {"led": 11, "anteil": "r", "name": "Halt"},
                    ],
                }
            ],
            "lampen": {"l": {"controller": "c", "leds": [0]}},
        }
    )
    cfg.shift_controller_leds("c", first_shifted=1, count=2, wled_count=22)
    names = {(item.von, item.bis, item.anteil, item.name) for item in cfg.controller[0].namen}
    assert (0, 0, "rgb", "Laterne") in names
    assert (4, 8, "rgb", "Haus3") in names
    assert (13, 13, "r", "Halt") in names
    cfg.shift_controller_leds("c", first_shifted=6, count=1, wled_count=23)
    haus = next(item for item in cfg.controller[0].namen if item.name == "Haus3")
    assert (haus.von, haus.bis) == (4, 9)
    cfg.delete_controller_leds("c", first_removed=4, count=2)
    names = {(item.von, item.bis, item.anteil, item.name) for item in cfg.controller[0].namen}
    assert (0, 0, "rgb", "Laterne") in names
    assert (4, 7, "rgb", "Haus3") in names
    assert (12, 12, "r", "Halt") in names
    cfg.delete_controller_leds("c", first_removed=12, count=1)
    names = {(item.von, item.bis, item.name) for item in cfg.controller[0].namen}
    assert (0, 0, "Laterne") in names
    assert (4, 7, "Haus3") in names
    assert all(item.name != "Halt" for item in cfg.controller[0].namen)


def test_language_files_cover_the_same_keys():
    from bidib2wled.web import STATIC_DIR

    en = json.loads((STATIC_DIR / "i18n" / "en.json").read_text(encoding="utf-8"))
    de = json.loads((STATIC_DIR / "i18n" / "de.json").read_text(encoding="utf-8"))
    assert set(en) == set(de)
    assert en and de


def test_legacy_german_yaml_saves_english_keys(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
adapter:
  netbidib:
    aktiv: true
    modus: server
    knotenname: Test
controller:
  - name: dorf
    ip: 127.0.0.1
    leds: 20
    namen:
      - { led: 0, name: Straßenlaterne }
lampen:
  laterne-1: { controller: dorf, leds: [0], farbe: "FFB060", anteil: rgb }
haeuser:
  haus-a:
    controller: dorf
    einschalten: nacheinander
    fenster:
      wz: { leds: [2], farbe: "FFFFFF" }
fahrzeuge:
  pkw:
    controller: dorf
    kanaele:
      licht: { leds: [4], art: dauer }
      rundum: { leds: [5], art: rundum, schritte: kanaele }
""",
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.lamps["laterne-1"].color == "FFB060"
    assert cfg.houses["haus-a"].turn_on == "sequential"
    assert cfg.vehicles["pkw"].channels["licht"].type == "continuous"
    assert cfg.vehicles["pkw"].channels["rundum"].steps == "channels"
    save_config(path, cfg)
    text = path.read_text(encoding="utf-8")
    for german in (
        "lampen:",
        "haeuser:",
        "fahrzeuge:",
        "kanaele:",
        "einschalten:",
        "fenster:",
        "aktiv:",
        "knotenname:",
        "namen:",
        "farbe:",
        "anteil:",
        "schritte:",
        "nacheinander",
        "dauer",
    ):
        assert german not in text, german
    assert "lamps:" in text
    assert "houses:" in text
    assert "vehicles:" in text
    assert "channels:" in text
    assert "turn_on: sequential" in text
    assert "type: continuous" in text
    assert "type: beacon" in text
    assert "steps: channels" in text
    assert "enabled: true" in text
    assert "node_name: Test" in text
    assert "names:" in text
    assert "color: FFB060" in text
    assert "Straßenlaterne" in text


