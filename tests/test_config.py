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

