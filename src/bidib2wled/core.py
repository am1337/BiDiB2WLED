"""Protokollneutraler Kern: Schalten von Lampen, Häusern, Gruppen, Sequenzen, Signalen, Fahrzeugen."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from bidib2wled.config import AppConfig
from bidib2wled.vehicles import apply_vehicle_to_pixels, vehicle_has_animation
from bidib2wled.wled import ActiveEffect, WledPool, rgb_from_hex

log = logging.getLogger(__name__)

StatusCallback = Callable[[str, int, bool], Awaitable[None]]
# object_id, aspect, in_progress


@dataclass
class ObjectState:
    aspect: int = 0
    in_progress: bool = False
    pending_aspect: int | None = None
    error: str | None = None

    def reported_aspect(self) -> int:
        if self.in_progress and self.pending_aspect is not None:
            return self.pending_aspect
        return self.aspect


class Engine:
    def __init__(self, pool: WledPool) -> None:
        self.pool = pool
        self.config = AppConfig()
        self.states: dict[str, ObjectState] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._status: list[StatusCallback] = []
        self._lock = asyncio.Lock()
        self._vehicle_aspects: dict[str, int] = {}
        self._vehicle_task: asyncio.Task | None = None
        self.now = time.monotonic

    def on_status(self, callback: StatusCallback) -> None:
        self._status.append(callback)

    def load(self, config: AppConfig) -> None:
        self.config = config
        for obj_id in config.all_object_ids():
            self.states.setdefault(obj_id, ObjectState())
        for vehicle_id in list(self._vehicle_aspects):
            if vehicle_id not in config.fahrzeuge:
                self._vehicle_aspects.pop(vehicle_id, None)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        self._ensure_vehicle_ticker()

    def state_of(self, object_id: str) -> ObjectState:
        return self.states.setdefault(object_id, ObjectState())

    async def switch(self, object_id: str, aspect: int, *, source: str = "local") -> None:
        log.info("Schaltbefehl %s → %s (von %s)", object_id, aspect, source)
        await self._cancel(object_id)
        task = asyncio.create_task(self._run_switch(object_id, aspect), name=f"switch:{object_id}")
        self._tasks[object_id] = task
        try:
            await task
        except asyncio.CancelledError:
            raise
        finally:
            self._tasks.pop(object_id, None)

    async def _run_switch(self, object_id: str, aspect: int) -> None:
        st = self.state_of(object_id)
        st.in_progress = True
        st.pending_aspect = aspect
        st.error = None
        await self._emit(object_id, aspect, True)
        try:
            if object_id in self.config.lampen:
                await self._switch_lamp(object_id, aspect)
            elif object_id in self.config.haeuser:
                await self._switch_house(object_id, aspect)
            elif object_id in self.config.gruppen:
                await self._switch_group(object_id, aspect)
            elif object_id in self.config.sequenzen:
                await self._switch_sequence(object_id, aspect)
            elif object_id in self.config.signale:
                await self._switch_signal(object_id, aspect)
            elif object_id in self.config.spezial:
                await self._switch_special(object_id, aspect)
            elif object_id in self.config.fahrzeuge:
                await self._switch_vehicle(object_id, aspect)
            elif "." in object_id:
                await self._switch_window(object_id, aspect)
            else:
                raise KeyError(f"Unbekanntes Objekt: {object_id}")
            st.aspect = aspect
            st.pending_aspect = None
            st.in_progress = False
            await self._emit(object_id, aspect, False)
        except asyncio.CancelledError:
            st.in_progress = False
            st.pending_aspect = None
            raise
        except Exception as exc:
            st.in_progress = False
            st.pending_aspect = None
            st.error = str(exc)
            log.exception("Schalten von %s fehlgeschlagen", object_id)
            await self._emit(object_id, aspect, False)
            raise

    async def identify_led(self, controller: str, index: int, output: int = 0) -> None:
        device = self.pool.get(controller)
        if device is None:
            raise KeyError(f"Controller {controller} nicht gebunden")
        await device.blink(device.global_index(output, index))

    async def _switch_lamp(self, lamp_id: str, aspect: int) -> None:
        lamp = self.config.lampen[lamp_id]
        color = rgb_from_hex(lamp.farbe, lamp.helligkeit) if aspect else (0, 0, 0)
        await self._set_leds(lamp.controller, {idx: color for idx in lamp.leds})
        self.state_of(lamp_id).aspect = 1 if aspect else 0

    async def _switch_window(self, object_id: str, aspect: int) -> None:
        house_id, window_id = object_id.split(".", 1)
        house = self.config.haeuser[house_id]
        window = house.fenster[window_id]
        color = rgb_from_hex(window.farbe, window.helligkeit) if aspect else (0, 0, 0)
        await self._set_leds(house.controller, {idx: color for idx in window.leds})
        self.state_of(object_id).aspect = 1 if aspect else 0

    async def _switch_house(self, house_id: str, aspect: int) -> None:
        house = self.config.haeuser[house_id]
        windows = list(house.fenster.items())
        if aspect:
            chosen = []
            for window_id, window in windows:
                if random.random() <= house.nacht_wahrscheinlichkeit:
                    chosen.append((window_id, window))
            if not chosen and windows:
                chosen = [random.choice(windows)]
            if house.einschalten == "zufaellig":
                random.shuffle(chosen)
            delay = house.delay_range
            first = True
            for window_id, window in chosen:
                if not first and house.einschalten != "sofort":
                    await asyncio.sleep(random.uniform(*delay) if delay[1] else 0)
                first = False
                color = rgb_from_hex(window.farbe, window.helligkeit)
                await self._set_leds(house.controller, {idx: color for idx in window.leds})
                self.state_of(f"{house_id}.{window_id}").aspect = 1
            off_windows = [item for item in windows if item not in chosen]
            updates: dict[int, tuple[int, int, int]] = {}
            for window_id, window in off_windows:
                for idx in window.leds:
                    updates[idx] = (0, 0, 0)
                self.state_of(f"{house_id}.{window_id}").aspect = 0
            if updates:
                await self._set_leds(house.controller, updates)
        else:
            order = list(reversed(windows))
            if house.einschalten == "zufaellig":
                random.shuffle(order)
            delay = house.delay_range
            first = True
            for window_id, window in order:
                if not first and house.einschalten != "sofort":
                    await asyncio.sleep(random.uniform(*delay) if delay[1] else 0)
                first = False
                await self._set_leds(house.controller, {idx: (0, 0, 0) for idx in window.leds})
                self.state_of(f"{house_id}.{window_id}").aspect = 0

    async def _switch_group(self, group_id: str, aspect: int) -> None:
        group = self.config.gruppen[group_id]
        for member in group.mitglieder:
            await self.switch(member, aspect, source=f"group:{group_id}")

    async def _switch_sequence(self, seq_id: str, aspect: int) -> None:
        seq = self.config.sequenzen[seq_id]
        members: list[str] = []
        for group_id in seq.gruppen:
            members.extend(self.config.gruppen[group_id].mitglieder)
        if isinstance(seq.reihenfolge, list):
            ordered = [item for item in seq.reihenfolge if item in members]
            for item in members:
                if item not in ordered:
                    ordered.append(item)
            members = ordered
        elif seq.reihenfolge == "zufaellig":
            random.shuffle(members)
        if not aspect:
            members = list(reversed(members))
        delay = seq.delay_range
        first = True
        for member in members:
            if not first:
                await asyncio.sleep(random.uniform(*delay) if delay[1] else delay[0])
            first = False
            await self.switch(member, 1 if aspect else 0, source=f"seq:{seq_id}")

    async def _switch_signal(self, signal_id: str, aspect: int) -> None:
        signal = self.config.signale[signal_id]
        all_leds: set[int] = set()
        for begriff in signal.begriffe.values():
            all_leds.update(begriff.leds)
        updates = {idx: (0, 0, 0) for idx in all_leds}
        begriff = signal.begriffe.get(aspect)
        if begriff is None:
            raise ValueError(f"Signal {signal_id}: Aspekt {aspect} unbekannt")
        for idx, color in begriff.leds.items():
            updates[idx] = rgb_from_hex(color, 255)
        await self._set_leds(signal.controller, updates)

    async def _switch_special(self, object_id: str, aspect: int) -> None:
        spec = self.config.spezial[object_id]
        device = self.pool.get(spec.controller)
        if device is None:
            raise KeyError(f"Controller {spec.controller} nicht verbunden")
        if aspect:
            bri = spec.helligkeit if spec.helligkeit is not None else 255
            await device.apply_effect(
                ActiveEffect(
                    object_id=object_id,
                    leds=tuple(spec.leds),
                    fx=spec.effekt,
                    pal=spec.palette,
                    sx=spec.geschwindigkeit,
                    ix=spec.intensitaet,
                    color=rgb_from_hex(spec.farbe, bri),
                    bri=bri,
                )
            )
        else:
            await device.clear_effect(object_id)
            await self._set_leds(spec.controller, {idx: (0, 0, 0) for idx in spec.leds})
        self.state_of(object_id).aspect = 1 if aspect else 0

    async def _switch_vehicle(self, vehicle_id: str, aspect: int) -> None:
        vehicle = self.config.fahrzeuge[vehicle_id]
        modi = vehicle.resolved_modi()
        if aspect not in modi and aspect:
            raise ValueError(f"Fahrzeug {vehicle_id}: Modus {aspect} unbekannt")
        mode = modi.get(aspect)
        if mode is None or not mode.kanaele:
            self._vehicle_aspects.pop(vehicle_id, None)
        else:
            self._vehicle_aspects[vehicle_id] = aspect
        await self._tick_vehicles(force_ids=(vehicle_id,))
        self._ensure_vehicle_ticker()

    def _ensure_vehicle_ticker(self) -> None:
        if not self._vehicle_needs_ticker():
            return
        task = self._vehicle_task
        if task is None or task.done():
            self._vehicle_task = asyncio.create_task(self._vehicle_ticker(), name="vehicle-ticker")

    def _vehicle_needs_ticker(self) -> bool:
        for vehicle_id, aspect in self._vehicle_aspects.items():
            vehicle = self.config.fahrzeuge.get(vehicle_id)
            if vehicle and vehicle_has_animation(vehicle, aspect):
                return True
        return False

    async def _vehicle_ticker(self) -> None:
        try:
            while self._vehicle_needs_ticker():
                await asyncio.sleep(0.05)
                try:
                    await self._tick_vehicles()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("Fahrzeug-Animation")
        finally:
            self._vehicle_task = None

    async def _tick_vehicles(self, force_ids: tuple[str, ...] = ()) -> None:
        ids = set(self._vehicle_aspects) | set(force_ids)
        if not ids:
            return
        now = self.now()
        by_controller: dict[str, list[str]] = {}
        for vehicle_id in ids:
            vehicle = self.config.fahrzeuge.get(vehicle_id)
            if vehicle is None:
                continue
            by_controller.setdefault(vehicle.controller, []).append(vehicle_id)
        for controller, vehicle_ids in by_controller.items():
            device = self.pool.get(controller)
            if device is None:
                if force_ids:
                    raise KeyError(f"Controller {controller} nicht verbunden")
                continue
            working = list(device.pixels)
            touched: set[int] = set()
            for vehicle_id in sorted(vehicle_ids):
                vehicle = self.config.fahrzeuge[vehicle_id]
                aspect = self._vehicle_aspects.get(vehicle_id, 0)
                touched |= apply_vehicle_to_pixels(working, vehicle, vehicle_id, aspect, now)
            updates: dict[int, tuple[int, int, int]] = {}
            for index in touched:
                if index >= len(working):
                    continue
                previous = device.pixels[index] if index < len(device.pixels) else (0, 0, 0)
                if working[index] != previous:
                    updates[index] = working[index]
            if updates:
                await self._set_leds(controller, updates)

    async def _set_leds(self, controller: str, updates: dict[int, tuple[int, int, int]]) -> None:
        device = self.pool.get(controller)
        if device is None:
            raise KeyError(f"Controller {controller} nicht verbunden")
        await device.apply_pixels(updates)

    async def _emit(self, object_id: str, aspect: int, in_progress: bool) -> None:
        for callback in list(self._status):
            try:
                await callback(object_id, aspect, in_progress)
            except Exception:
                log.exception("Status-Callback")

    async def _cancel(self, object_id: str) -> None:
        task = self._tasks.get(object_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
