from bidib2wled.pixels import (
    clear_components,
    delete_index_range,
    delete_led_range,
    expand_anteil,
    set_components,
    shift_index,
    shift_index_map,
    shift_led_list,
)


def test_expand_anteil():
    assert expand_anteil("r") == ("r",)
    assert expand_anteil("g") == ("g",)
    assert expand_anteil("b") == ("b",)
    assert expand_anteil("rgb") == ("r", "g", "b")
    assert expand_anteil("") == ("r", "g", "b")


def test_set_and_clear_components_preserve_others():
    pixel = (9, 8, 7)
    merged = set_components(pixel, ("r",), (255, 0, 0))
    assert merged[0] == 255
    assert merged[1] == 8
    assert merged[2] == 7
    cleared = clear_components(merged, ("r",))
    assert cleared == (0, 8, 7)


def test_rgb_keeps_true_color():
    assert set_components((9, 8, 7), ("r", "g", "b"), (0, 255, 0)) == (0, 255, 0)


def test_single_channel_uses_brightness_of_any_color():
    merged = set_components((0, 0, 0), ("r",), (0, 200, 0))
    assert merged[0] == 200
    assert merged[1] == 0


def test_shift_helpers():
    assert shift_index(4, 5, 3) == 4
    assert shift_index(5, 5, 3) == 8
    leds, changed = shift_led_list([0, 4, 5, 6], 5, 3)
    assert leds == [0, 4, 8, 9]
    assert changed == 2
    mapping, n = shift_index_map({4: "a", 5: "b"}, 5, 3)
    assert mapping == {4: "a", 8: "b"}
    assert n == 1


def test_delete_led_range():
    leds, shifted, dropped = delete_led_range([0, 4, 8, 9], 5, 3)
    assert leds == [0, 4, 5, 6]
    assert shifted == 2
    assert dropped == 0
    leds, shifted, dropped = delete_led_range([0, 5, 8], 5, 3)
    assert leds == [0, 5]
    assert shifted == 1
    assert dropped == 1
    mapping, shifted, dropped = delete_index_range({4: "a", 5: "b", 8: "c"}, 5, 3)
    assert mapping == {4: "a", 5: "c"}
    assert shifted == 1
    assert dropped == 1
