"""Pixel-Anteile eines WS2811 (R/G/B) und Adressverschiebung."""

from __future__ import annotations


def expand_anteil(anteil: str) -> tuple[str, ...]:
    key = (anteil or "rgb").strip().lower()
    if key == "r":
        return ("r",)
    if key == "g":
        return ("g",)
    if key == "b":
        return ("b",)
    return ("r", "g", "b")


def component_value(
    color: tuple[int, int, int],
    component: str,
    *,
    allow_max_fallback: bool = True,
) -> int:
    """Helligkeit für einen WS2811-Pin.

    Bei nur einem Anteil (r/g/b) zählt die Helligkeit der Farbe – auch wenn sie
    in einem anderen Kanal steckt (weiß oder einfarbig auf einem Pin).
    Bei RGB bleiben die Kanäle unverändert, damit Grün nicht Rot und Blau füllt.
    """
    cr, cg, cb = color
    if component == "r":
        chosen = cr
    elif component == "g":
        chosen = cg
    elif component == "b":
        chosen = cb
    else:
        chosen = 0
    if chosen or not allow_max_fallback:
        return chosen
    return max(cr, cg, cb)


def set_components(
    pixel: tuple[int, int, int],
    components: tuple[str, ...],
    color: tuple[int, int, int],
) -> tuple[int, int, int]:
    red, green, blue = pixel
    fallback = len(components) == 1
    for component in components:
        value = component_value(color, component, allow_max_fallback=fallback)
        if component == "r":
            red = value
        elif component == "g":
            green = value
        else:
            blue = value
    return (red, green, blue)


def clear_components(
    pixel: tuple[int, int, int], components: tuple[str, ...] | set[str]
) -> tuple[int, int, int]:
    red, green, blue = pixel
    if "r" in components:
        red = 0
    if "g" in components:
        green = 0
    if "b" in components:
        blue = 0
    return (red, green, blue)


def ensure_pixel(pixels: list[tuple[int, int, int]], index: int) -> None:
    while len(pixels) <= index:
        pixels.append((0, 0, 0))


def shift_index(index: int, first_shifted: int, count: int) -> int:
    return index + count if index >= first_shifted else index


def shift_led_list(leds: list[int], first_shifted: int, count: int) -> tuple[list[int], int]:
    """Gibt die neue Liste und die Anzahl verschobener Einträge zurück."""
    changed = 0
    out: list[int] = []
    for led in leds:
        if led >= first_shifted:
            out.append(led + count)
            changed += 1
        else:
            out.append(led)
    return out, changed


def shift_index_map(mapping: dict[int, object], first_shifted: int, count: int) -> tuple[dict[int, object], int]:
    changed = 0
    out: dict[int, object] = {}
    for key, value in mapping.items():
        if key >= first_shifted:
            out[key + count] = value
            changed += 1
        else:
            out[int(key)] = value
    return out, changed
