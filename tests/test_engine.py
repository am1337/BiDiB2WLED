import asyncio
import contextlib

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
            "fahrzeuge": {
                "pkw-a": {
                    "controller": "dorf",
                    "kanaele": {
                        "licht": {"leds": [12], "anteil": "r", "farbe": "FFFFCC", "art": "dauer"},
                        "rueck": {"leds": [12], "anteil": "g", "farbe": "FF0000", "art": "dauer"},
                        "blinker-l": {"leds": [13], "anteil": "r", "farbe": "FF8000", "art": "blinker"},
                        "blinker-r": {"leds": [13], "anteil": "g", "farbe": "FF8000", "art": "blinker"},
                    },
                },
                "feuerwehr": {
                    "controller": "dorf",
                    "rundum_schritt": "0.12s",
                    "kanaele": {
                        "scheinwerfer": {"leds": [16], "anteil": "rgb", "farbe": "FFFFCC", "art": "dauer"},
                        "rundum": {"leds": [17], "anteil": "rgb", "farbe": "0000FF", "art": "rundum"},
                    },
                },
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
async def test_lamp_anteil_keeps_other_channels(engine):
    from bidib2wled.config import LampConfig

    engine.config.lampen["rot-kanal"] = LampConfig(
        controller="dorf", leds=[4], farbe="FF0000", anteil="r"
    )
    engine.config.lampen["gruen-kanal"] = LampConfig(
        controller="dorf", leds=[4], farbe="00FF00", anteil="g"
    )
    engine.pool.get("dorf").pixels[4] = (9, 9, 9)
    await engine.switch("rot-kanal", 1)
    pix = engine.pool.get("dorf").pixels[4]
    assert pix[0] > 0
    assert pix[1] == 9
    await engine.switch("gruen-kanal", 1)
    pix = engine.pool.get("dorf").pixels[4]
    assert pix[0] > 0 and pix[1] > 0
    await engine.switch("rot-kanal", 0)
    pix = engine.pool.get("dorf").pixels[4]
    assert pix[0] == 0
    assert pix[1] > 0


@pytest.mark.asyncio
async def test_window_anteil_keeps_other_channels(engine):
    from bidib2wled.config import HouseConfig

    engine.config.haeuser["chip"] = HouseConfig.model_validate(
        {
            "controller": "dorf",
            "einschalten": "sofort",
            "nacht-wahrscheinlichkeit": 1,
            "fenster": {
                "rot": {"leds": [7], "farbe": "FF0000", "anteil": "r"},
                "blau": {"leds": [7], "farbe": "0000FF", "anteil": "b"},
            },
        }
    )
    await engine.switch("chip.rot", 1)
    pix = engine.pool.get("dorf").pixels[7]
    assert pix[0] > 0
    assert pix[2] == 0
    await engine.switch("chip.blau", 1)
    pix = engine.pool.get("dorf").pixels[7]
    assert pix[0] > 0 and pix[2] > 0
    await engine.switch("chip.rot", 0)
    pix = engine.pool.get("dorf").pixels[7]
    assert pix[0] == 0
    assert pix[2] > 0


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
async def test_signal_same_led_halt_fahrt_channels():
    pool = WledPool(simulate=True)
    pool.bind("dorf", ip="127.0.0.1", leds=8, mac="aa:bb:cc:dd:ee:ff")
    cfg = AppConfig.model_validate(
        {
            "controller": [{"name": "dorf", "ip": "127.0.0.1", "leds": 8}],
            "signale": {
                "sig": {
                    "controller": "dorf",
                    "begriffe": {
                        0: {"name": "Halt", "leds": {3: "FF0000"}, "anteile": {3: "r"}},
                        1: {"name": "Fahrt", "leds": {3: "00FF00"}, "anteile": {3: "g"}},
                    },
                }
            },
        }
    )
    eng = Engine(pool)
    eng.load(cfg)
    await eng.switch("sig", 0)
    pix = eng.pool.get("dorf").pixels
    assert pix[3] == (255, 0, 0)
    await eng.switch("sig", 1)
    assert pix[3] == (0, 255, 0)
    await eng.switch("sig", 0)
    assert pix[3] == (255, 0, 0)


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


async def _stop_vehicle_anim(engine: Engine) -> None:
    engine._vehicle_aspects.clear()
    task = engine._vehicle_task
    if task and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


@pytest.mark.asyncio
async def test_vehicle_dauer_merge_and_off(engine):
    await engine.switch("pkw-a", 1)
    pix = engine.pool.get("dorf").pixels
    assert pix[12][0] > 0
    assert pix[12][1] > 0
    assert pix[12][2] == 0
    assert pix[13] == (0, 0, 0)
    await engine.switch("pkw-a", 0)
    assert pix[12] == (0, 0, 0)


@pytest.mark.asyncio
async def test_vehicle_rundum_and_ticker(engine):
    from bidib2wled.vehicles import vehicle_timing

    vehicle = engine.config.fahrzeuge["feuerwehr"]
    _, phase = vehicle_timing("feuerwehr", vehicle.blink_period_s)
    engine.now = lambda: -phase + 0.001
    await engine.switch("feuerwehr", 2)
    pix = engine.pool.get("dorf").pixels
    assert pix[16] != (0, 0, 0)
    assert pix[17][0] > 0
    assert pix[17][1] == 0
    assert pix[17][2] == 0
    engine.now = lambda: -phase + 0.13
    await engine._tick_vehicles()
    assert pix[17][0] == 0
    assert pix[17][1] > 0
    await engine.switch("feuerwehr", 0)
    assert pix[16] == (0, 0, 0)
    assert pix[17] == (0, 0, 0)
    await _stop_vehicle_anim(engine)


@pytest.mark.asyncio
async def test_vehicle_warnblinker_starts_animation(engine):
    await engine.switch("pkw-a", 2)
    assert engine._vehicle_task is not None
    assert not engine._vehicle_task.done()
    await engine.switch("pkw-a", 0)
    pix = engine.pool.get("dorf").pixels
    assert pix[13] == (0, 0, 0)
    await _stop_vehicle_anim(engine)

