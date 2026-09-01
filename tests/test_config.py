import pytest

from bidib2wled.config import (
    AppConfig,
    ControllerConfig,
    VehicleConfig,
    load_config,
    normalize_mac,
    parse_delay_range,
    parse_duration,
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
    assert cfg.object_kind("laterne-1") == "lampe"
    assert cfg.object_kind("haus-a") == "haus"
    assert cfg.object_kind("haus-a.wz") == "fenster"
    assert cfg.object_kind("sig") == "signal"
    assert cfg.object_kind("kamin") == "spezial"
    assert cfg.object_kind("pkw-rot") == "fahrzeug"
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

    lamp = host_setup_info("lampe", 0)
    assert lamp[0]["program"] == "Rocrail"
    assert "Adresse 1 (Adresse+1)" in lamp[0]["text"]
    signal = host_setup_info("signal", 2)
    assert signal[0]["text"].startswith("Signal:")
    assert "Adresse 3 (Adresse+1)" in signal[0]["text"]
    window = host_setup_info("fenster", None)
    assert "Haus" in window[0]["text"]
    vehicle = host_setup_info("fahrzeug", 4)
    assert vehicle[0]["text"].startswith("Signal:")
    assert "Modi" in vehicle[0]["text"]
    assert "Adresse 5 (Adresse+1)" in vehicle[0]["text"]


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
        assert "unbekannter Controller" in str(exc)
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
    assert vehicle.kanaele["licht"].art == "dauer"
    assert vehicle.kanaele["blinker"].art == "blinker"
    assert vehicle.kanaele["rundum"].anteil == "rgb"
    modi = vehicle.resolved_modi()
    assert modi[0].name == "Aus"
    assert modi[1].name == "Licht"
    assert modi[2].name == "Warnblinker"
    assert modi[3].name == "Einsatz"
    assert "rundum" in modi[3].kanaele
    assert default_vehicle_modi(vehicle.kanaele)[2].kanaele == ["licht", "blinker"]


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
        assert "unbekannter Kanal" in str(exc)
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
    with pytest.raises(ValueError, match="keine LED mehr"):
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
    dumped = cfg.model_dump(by_alias=True, exclude_none=True)
    begriff = dumped["signale"]["s1"]["begriffe"][0]
    assert "anteile" not in begriff or begriff["anteile"] is None


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
    dumped = cfg.model_dump(by_alias=True, exclude_none=True)
    begriffe = dumped["signale"]["s1"]["begriffe"]
    assert begriffe[0]["leds"][5] == "FF0000"
    assert begriffe[0]["anteile"][5] == "r"
    assert begriffe[1]["leds"][5] == "00FF00"
    assert begriffe[1]["anteile"][5] == "g"
    again = AppConfig.model_validate(dumped)
    assert again.signale["s1"].begriffe[0].anteil_of(5) == "r"
    assert again.signale["s1"].begriffe[1].anteil_of(5) == "g"

