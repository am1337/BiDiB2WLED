from bidib2wled.config import (
    AppConfig,
    ControllerConfig,
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
    assert cfg.aspect_count("sig") == 2


def test_unknown_controller_rejected():
    try:
        AppConfig.model_validate({"lampen": {"x": {"controller": "nein", "leds": [0]}}})
    except Exception as exc:
        assert "unbekannter Controller" in str(exc)
    else:
        raise AssertionError("sollte fehlschlagen")
