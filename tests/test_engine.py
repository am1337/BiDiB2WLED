import pytest

from bidib2wled.config import AppConfig
from bidib2wled.core import Engine
from bidib2wled.wled import WledPool


@pytest.fixture
def engine():
    pool = WledPool(simulate=True)
    pool.bind("dorf", ip="127.0.0.1", leds=20, mac="aa:bb:cc:dd:ee:ff")
    cfg = AppConfig.model_validate(
        {
            "controller": [{"name": "dorf", "ip": "127.0.0.1", "leds": 20}],
            "lampen": {"laterne-1": {"controller": "dorf", "leds": [0], "farbe": "FFB060"}},
            "haeuser": {
                "haus-a": {
                    "controller": "dorf",
                    "einschalten": "sofort",
                    "nacht-wahrscheinlichkeit": 1,
                    "fenster": {"wz": {"leds": [2, 3], "farbe": "FFFFFF"}},
                }
            },
            "gruppen": {"g1": {"mitglieder": ["laterne-1", "haus-a"]}},
            "sequenzen": {
                "seq": {"gruppen": ["g1"], "reihenfolge": "definiert", "verzoegerung": [0, 0]}
            },
            "signale": {
                "sig": {
                    "controller": "dorf",
                    "begriffe": {
                        0: {"name": "Halt", "leds": {5: "FF0000"}},
                        1: {"name": "Fahrt", "leds": {6: "00FF00"}},
                    },
                }
            },
            "spezial": {
                "kamin": {
                    "controller": "dorf",
                    "leds": [8, 9],
                    "effekt": 10,
                    "palette": 2,
                    "geschwindigkeit": 90,
                    "intensitaet": 180,
                    "farbe": "FF6A00",
                }
            },
        }
    )
    eng = Engine(pool)
    eng.load(cfg)
    return eng


@pytest.mark.asyncio
async def test_lamp_on_off(engine):
    await engine.switch("laterne-1", 1)
    pix = engine.pool.get("dorf").pixels
    assert pix[0] != (0, 0, 0)
    await engine.switch("laterne-1", 0)
    assert pix[0] == (0, 0, 0)


@pytest.mark.asyncio
async def test_house_and_window(engine):
    await engine.switch("haus-a", 1)
    pix = engine.pool.get("dorf").pixels
    assert pix[2] != (0, 0, 0)
    await engine.switch("haus-a.wz", 0)
    assert pix[2] == (0, 0, 0)


@pytest.mark.asyncio
async def test_signal_atomic(engine):
    await engine.switch("sig", 1)
    pix = engine.pool.get("dorf").pixels
    assert pix[5] == (0, 0, 0)
    assert pix[6] == (0, 255, 0)
    await engine.switch("sig", 0)
    assert pix[5] == (255, 0, 0)
    assert pix[6] == (0, 0, 0)


@pytest.mark.asyncio
async def test_sequence(engine):
    await engine.switch("seq", 1)
    pix = engine.pool.get("dorf").pixels
    assert pix[0] != (0, 0, 0)
    assert pix[2] != (0, 0, 0)
    await engine.switch("seq", 0)
    assert pix[0] == (0, 0, 0)
    assert pix[2] == (0, 0, 0)


@pytest.mark.asyncio
async def test_special_on_off(engine):
    device = engine.pool.get("dorf")
    await engine.switch("kamin", 1)
    assert "kamin" in device.active_effects
    effect = device.active_effects["kamin"]
    assert effect.fx == 10
    assert effect.pal == 2
    assert effect.sx == 90
    overlay = [seg for seg in device.state_body()["seg"] if seg.get("frz") is False]
    assert overlay and overlay[0]["fx"] == 10
    await engine.switch("kamin", 0)
    assert "kamin" not in device.active_effects
    assert device.pixels[8] == (0, 0, 0)
    assert device.pixels[9] == (0, 0, 0)
    assert device.posted_overlay_ids == []
    assert all(seg.get("frz") is not False for seg in device.state_body()["seg"])
