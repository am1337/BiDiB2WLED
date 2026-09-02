from bidib2wled.config import VehicleConfig
from bidib2wled.vehicles import (
    apply_vehicle_to_pixels,
    pattern_active,
    rundum_steps,
    vehicle_timing,
)


def _vehicle(payload: dict) -> VehicleConfig:
    return VehicleConfig.model_validate(payload)


def test_rundum_steps_single_ws2811():
    assert rundum_steps([7], "rgb") == [(7, ("r",)), (7, ("g",)), (7, ("b",))]
    assert rundum_steps([4, 5, 6], "rgb") == [(4, ("r", "g", "b")), (5, ("r", "g", "b")), (6, ("r", "g", "b"))]
    assert rundum_steps([4, 5], "r") == [(4, ("r",)), (5, ("r",))]
    assert rundum_steps([7], "rgb", "leds") == [(7, ("r", "g", "b"))]
    assert rundum_steps([4, 5], "rgb", "kanaele") == [
        (4, ("r",)),
        (4, ("g",)),
        (4, ("b",)),
        (5, ("r",)),
        (5, ("g",)),
        (5, ("b",)),
    ]


def test_blink_periods_differ_per_vehicle():
    period_a, phase_a = vehicle_timing("pkw-a", 0.75)
    period_b, phase_b = vehicle_timing("pkw-b", 0.75)
    assert period_a != period_b
    differ = False
    for step in range(400):
        now = step * 0.02
        on_a = pattern_active("blinker", now + phase_a, period_a)
        on_b = pattern_active("blinker", now + phase_b, period_b)
        if on_a != on_b:
            differ = True
            break
    assert differ


def test_same_vehicle_blinkers_stay_in_sync():
    vehicle = _vehicle(
        {
            "controller": "dorf",
            "kanaele": {
                "links": {"leds": [1], "anteil": "r", "farbe": "FF8000", "art": "blinker"},
                "rechts": {"leds": [1], "anteil": "g", "farbe": "FF8000", "art": "blinker"},
            },
            "modi": {
                0: {"name": "Aus", "kanaele": []},
                2: {"name": "Warnblinker", "kanaele": ["links", "rechts"]},
            },
        }
    )
    period, phase = vehicle_timing("bus-1", vehicle.blink_period_s)
    for step in range(40):
        now = step * 0.05
        pixels = [(0, 0, 0)] * 4
        apply_vehicle_to_pixels(pixels, vehicle, "bus-1", 2, now)
        left_on = pixels[1][0] > 0
        right_on = pixels[1][1] > 0
        assert left_on == right_on
        expected = pattern_active("blinker", now + phase, period)
        assert left_on is expected


def test_channel_merge_on_one_ws2811():
    vehicle = _vehicle(
        {
            "controller": "dorf",
            "kanaele": {
                "scheinwerfer": {"leds": [10], "anteil": "r", "farbe": "FFFFCC", "art": "dauer"},
                "ruecklicht": {"leds": [10], "anteil": "g", "farbe": "FF0000", "art": "dauer"},
            },
        }
    )
    pixels = [(9, 9, 9)] * 12
    apply_vehicle_to_pixels(pixels, vehicle, "lkw", 1, 0.0)
    red, green, blue = pixels[10]
    assert red > 0 and green > 0
    assert blue == 9
    apply_vehicle_to_pixels(pixels, vehicle, "lkw", 0, 0.0)
    assert pixels[10][0] == 0
    assert pixels[10][1] == 0
    assert pixels[10][2] == 9


def test_rundum_cycles_rgb_of_one_pixel():
    vehicle = _vehicle(
        {
            "controller": "dorf",
            "kanaele": {
                "licht": {"leds": [0], "anteil": "rgb", "farbe": "FFFFFF", "art": "dauer"},
                "rundum": {"leds": [3], "anteil": "rgb", "farbe": "0000FF", "art": "rundum"},
            },
            "rundum_schritt": "0.12s",
        }
    )
    _, phase = vehicle_timing("feuerwehr", vehicle.blink_period_s)
    modi = vehicle.resolved_modi()
    einsatz = max(key for key, mode in modi.items() if "rundum" in mode.kanaele)
    for index, component in enumerate(("r", "g", "b")):
        now = -phase + 0.12 * index + 0.01
        pixels = [(0, 0, 0)] * 8
        apply_vehicle_to_pixels(pixels, vehicle, "feuerwehr", einsatz, now)
        red, green, blue = pixels[3]
        assert (red > 0) is (component == "r")
        assert (green > 0) is (component == "g")
        assert (blue > 0) is (component == "b")
        assert pixels[0] != (0, 0, 0)


def test_rundum_kanaele_walks_each_channel_of_two_pixels():
    vehicle = _vehicle(
        {
            "controller": "dorf",
            "kanaele": {
                "rundum": {
                    "leds": [2, 3],
                    "anteil": "rgb",
                    "farbe": "0000FF",
                    "art": "rundum",
                    "schritte": "kanaele",
                }
            },
            "rundum_schritt": "0.10s",
        }
    )
    _, phase = vehicle_timing("turm", vehicle.blink_period_s)
    expected = [(2, 0), (2, 1), (2, 2), (3, 0), (3, 1), (3, 2)]
    for index, (led, component) in enumerate(expected):
        now = -phase + 0.10 * index + 0.01
        pixels = [(0, 0, 0)] * 5
        apply_vehicle_to_pixels(pixels, vehicle, "turm", 1, now)
        for idx, pixel in enumerate(pixels):
            if idx != led:
                assert pixel == (0, 0, 0)
            else:
                assert pixel[component] > 0
                assert pixel[(component + 1) % 3] == 0
                assert pixel[(component + 2) % 3] == 0
