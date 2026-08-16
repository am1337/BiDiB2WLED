import pytest

from bidib2wled.core import Engine
from bidib2wled.wled import LedOutput, WledDevice, WledInfo, WledPool, outputs_from_cfg


def test_outputs_from_cfg_two_buses():
    cfg = {
        "hw": {
            "led": {
                "ins": [
                    {"en": True, "start": 0, "len": 30, "pin": [16]},
                    {"en": True, "start": 30, "len": 20, "pin": [2]},
                    {"en": False, "start": 50, "len": 10, "pin": [4]},
                ]
            }
        }
    }
    outs = outputs_from_cfg(cfg, 50)
    assert len(outs) == 2
    assert outs[0].start == 0 and outs[0].length == 30 and outs[0].pin == 16
    assert outs[1].start == 30 and outs[1].length == 20 and outs[1].pin == 2
    assert outs[1].to_dict()["id"] == 1


def test_outputs_from_cfg_fallback():
    outs = outputs_from_cfg({}, 12)
    assert len(outs) == 1
    assert outs[0].start == 0 and outs[0].length == 12


def test_global_index_second_output():
    device = WledDevice(
        info=WledInfo(name="friedhof", mac="", ip="127.0.0.1", led_count=50),
        simulate=True,
    )
    device.info.outputs = outputs_from_cfg(
        {
            "hw": {
                "led": {
                    "ins": [
                        {"en": True, "start": 0, "len": 30, "pin": 16},
                        {"en": True, "start": 30, "len": 20, "pin": 2},
                    ]
                }
            }
        }
    )
    assert device.global_index(0, 0) == 0
    assert device.global_index(1, 0) == 30
    assert device.global_index(1, 19) == 49
    with pytest.raises(ValueError):
        device.global_index(1, 20)
    with pytest.raises(ValueError):
        device.global_index(2, 0)


def test_state_body_covers_full_strip():
    device = WledDevice(
        info=WledInfo(name="friedhof", mac="", ip="127.0.0.1", led_count=9, max_segments=8),
        simulate=True,
    )
    device.ensure_size(9)
    device.pixels[0] = (255, 255, 255)
    device.pixels[4] = (104, 147, 70)
    body = device.state_body({4: (104, 147, 70)})
    assert len(body["seg"]) == 1
    assert body["seg"][0]["start"] == 0
    assert body["seg"][0]["stop"] == 9
    assert body["seg"][0]["i"][0] == "FFFFFF"
    assert body["seg"][0]["i"][4] == "689346"
    assert body["on"] is True
    assert all(seg.get("stop") != 0 for seg in body["seg"])


def test_state_body_two_outputs_off_keeps_other_bus():
    device = WledDevice(
        info=WledInfo(
            name="friedhof",
            mac="",
            ip="127.0.0.1",
            led_count=9,
            max_segments=8,
            outputs=[
                LedOutput(0, 0, 3, 16),
                LedOutput(1, 3, 6, 2),
            ],
        ),
        simulate=True,
    )
    device.ensure_size(9)
    device.pixels[0] = (255, 255, 255)
    device.pixels[1] = (255, 255, 255)
    device.pixels[2] = (255, 255, 255)
    device.pixels[4] = (104, 147, 70)
    body = device.state_body({0: (0, 0, 0), 1: (0, 0, 0), 2: (0, 0, 0)})
    assert len(body["seg"]) == 2
    assert body["seg"][0]["start"] == 0 and body["seg"][0]["stop"] == 3
    assert body["seg"][1]["start"] == 3 and body["seg"][1]["stop"] == 9
    assert body["seg"][0]["i"] == ["000000", "000000", "000000"]
    assert body["seg"][1]["i"][1] == "689346"
    assert body["seg"][0]["frz"] is True
    assert body["seg"][1]["frz"] is True
    assert all("fx" not in seg for seg in body["seg"])
    assert all(seg.get("stop") != 0 for seg in body["seg"])
    assert body["on"] is True


def test_bind_keeps_lit_pixels():
    pool = WledPool(simulate=True)
    first = pool.bind("friedhof", ip="127.0.0.1", leds=9)
    first.info.outputs = [LedOutput(0, 0, 3, 16), LedOutput(1, 3, 6, 2)]
    first.ensure_size(9)
    first.pixels[4] = (104, 147, 70)
    second = pool.bind("friedhof", ip="127.0.0.1", leds=9)
    assert second.pixels[4] == (104, 147, 70)
    assert len(second.info.outputs) == 2
    assert second.info.outputs[1].start == 3


@pytest.mark.asyncio
async def test_identify_second_output():
    pool = WledPool(simulate=True)
    device = pool.bind("friedhof", ip="127.0.0.1", leds=50)
    await device.fetch_info()
    blinked: list[int] = []

    async def fake_blink(index: int, times: int = 4, interval: float = 0.25) -> None:
        blinked.append(index)

    device.blink = fake_blink  # type: ignore[method-assign]
    engine = Engine(pool)
    await engine.identify_led("friedhof", 0, output=1)
    assert device.info.outputs[1].start == 25
    assert blinked == [25]
