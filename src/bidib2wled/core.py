"""Protokollneutraler Kern: Schalten von Lampen, Häusern, Gruppen, Sequenzen, Signalen, Fahrzeugen."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from bidib2wled.config import AppConfig
from bidib2wled.pixels import clear_components, ensure_pixel, expand_anteil, set_components
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
            if vehicle_id not in config.vehicles:
                self._vehicle_aspects.pop(vehicle_id, None)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        self._ensure_vehicle_ticker()

    def state_of(self, object_id: str) -> ObjectState:
        return self.states.setdefault(object_id, ObjectState())

    async def switch(self, object_id: str, aspect: int, *, source: str = "local") -> None:
        log.info("Switch %s → %s (from %s)", object_id, aspect, source)
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
            if object_id in self.config.lamps:
                await self._switch_lamp(object_id, aspect)
            elif object_id in self.config.houses:
                await self._switch_house(object_id, aspect)
            elif object_id in self.config.groups:
                await self._switch_group(object_id, aspect)
            elif object_id in self.config.sequences:
                await self._switch_sequence(object_id, aspect)
            elif object_id in self.config.signals:
                await self._switch_signal(object_id, aspect)
            elif object_id in self.config.special:
                await self._switch_special(object_id, aspect)
            elif object_id in self.config.vehicles:
                await self._switch_vehicle(object_id, aspect)
            elif "." in object_id:
                await self._switch_window(object_id, aspect)
            else:
                raise KeyError(f"Unknown object: {object_id}")
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
            log.exception("Switching %s failed", object_id)
            await self._emit(object_id, aspect, False)
            raise

    async def identify_led(self, controller: str, index: int, output: int = 0) -> None:
        device = self.pool.get(controller)
        if device is None:
            raise KeyError(f"Controller {controller} is not bound")
        await device.blink(device.global_index(output, index))

    async def _switch_lamp(self, lamp_id: str, aspect: int) -> None:
        lamp = self.config.lamps[lamp_id]
        color = rgb_from_hex(lamp.color, lamp.brightness) if aspect else None
        await self._apply_channels(lamp.controller, [(lamp.leds, lamp.channel, color)])
        self.state_of(lamp_id).aspect = 1 if aspect else 0

    async def _switch_window(self, object_id: str, aspect: int) -> None:
        house_id, window_id = object_id.split(".", 1)
        house = self.config.houses[house_id]
        window = house.windows[window_id]
        color = rgb_from_hex(window.color, window.brightness) if aspect else None
        await self._apply_channels(house.controller, [(window.leds, window.channel, color)])
        self.state_of(object_id).aspect = 1 if aspect else 0

    async def _switch_house(self, house_id: str, aspect: int) -> None:
        house = self.config.houses[house_id]
        windows = list(house.windows.items())
        if aspect:
            chosen = []
            for window_id, window in windows:
                if random.random() <= house.night_probability:
                    chosen.append((window_id, window))
            if not chosen and windows:
                chosen = [random.choice(windows)]
            if house.turn_on == "random":
                random.shuffle(chosen)
            delay = house.delay_range
            first = True
            for window_id, window in chosen:
                if not first and house.turn_on != "immediate":
                    await asyncio.sleep(random.uniform(*delay) if delay[1] else 0)
                first = False
                color = rgb_from_hex(window.color, window.brightness)
                await self._apply_channels(house.controller, [(window.leds, window.channel, color)])
                self.state_of(f"{house_id}.{window_id}").aspect = 1
            off_windows = [item for item in windows if item not in chosen]
            if off_windows:
                await self._apply_channels(
                    house.controller,
                    [(window.leds, window.channel, None) for _, window in off_windows],
                )
                for window_id, _window in off_windows:
                    self.state_of(f"{house_id}.{window_id}").aspect = 0
        else:
            order = list(reversed(windows))
            if house.turn_on == "random":
                random.shuffle(order)
            delay = house.delay_range
            first = True
            for window_id, window in order:
                if not first and house.turn_on != "immediate":
                    await asyncio.sleep(random.uniform(*delay) if delay[1] else 0)
                first = False
                await self._apply_channels(house.controller, [(window.leds, window.channel, None)])
                self.state_of(f"{house_id}.{window_id}").aspect = 0

    async def _switch_group(self, group_id: str, aspect: int) -> None:
        group = self.config.groups[group_id]
        for member in group.members:
            await self.switch(member, aspect, source=f"group:{group_id}")

    async def _switch_sequence(self, seq_id: str, aspect: int) -> None:
        seq = self.config.sequences[seq_id]
        members: list[str] = []
        for group_id in seq.groups:
            members.extend(self.config.groups[group_id].members)
        if isinstance(seq.order, list):
            ordered = [item for item in seq.order if item in members]
            for item in members:
                if item not in ordered:
                    ordered.append(item)
            members = ordered
        elif seq.order == "random":
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
        signal = self.config.signals[signal_id]
        aspect_cfg = signal.aspects.get(aspect)
        if aspect_cfg is None:
            raise ValueError(f"Signal {signal_id}: aspect {aspect} unknown")
        assignments: list[tuple[list[int], str, tuple[int, int, int] | None]] = []
        for other in signal.aspects.values():
            for idx in other.leds:
                assignments.append(([idx], other.channel_of(idx), None))
        for idx, color in aspect_cfg.leds.items():
            assignments.append(([idx], aspect_cfg.channel_of(idx), rgb_from_hex(color, 255)))
        await self._apply_channels(signal.controller, assignments)

    async def _switch_special(self, object_id: str, aspect: int) -> None:
        spec = self.config.special[object_id]
        device = self.pool.get(spec.controller)
        if device is None:
            raise KeyError(f"Controller {spec.controller} is not connected")
        if aspect:
            bri = spec.brightness if spec.brightness is not None else 255
            await device.apply_effect(
                ActiveEffect(
                    object_id=object_id,
                    leds=tuple(spec.leds),
                    fx=spec.effect,
                    pal=spec.palette,
                    sx=spec.speed,
                    ix=spec.intensity,
                    color=rgb_from_hex(spec.color, bri),
                    bri=bri,
                )
            )
        else:
            await device.clear_effect(object_id)
            await self._apply_channels(spec.controller, [(spec.leds, spec.channel, None)], force=True)
        self.state_of(object_id).aspect = 1 if aspect else 0

    async def _switch_vehicle(self, vehicle_id: str, aspect: int) -> None:
        vehicle = self.config.vehicles[vehicle_id]
        modes = vehicle.resolved_modes()
        if aspect not in modes and aspect:
            raise ValueError(f"Vehicle {vehicle_id}: mode {aspect} unknown")
        mode = modes.get(aspect)
        if mode is None or not mode.channels:
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
            vehicle = self.config.vehicles.get(vehicle_id)
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
                    log.exception("Vehicle animation")
        finally:
            self._vehicle_task = None

    async def _tick_vehicles(self, force_ids: tuple[str, ...] = ()) -> None:
        ids = set(self._vehicle_aspects) | set(force_ids)
        if not ids:
            return
        now = self.now()
        by_controller: dict[str, list[str]] = {}
        for vehicle_id in ids:
            vehicle = self.config.vehicles.get(vehicle_id)
            if vehicle is None:
                continue
            by_controller.setdefault(vehicle.controller, []).append(vehicle_id)
        for controller, vehicle_ids in by_controller.items():
            device = self.pool.get(controller)
            if device is None:
                if force_ids:
                    raise KeyError(f"Controller {controller} is not connected")
                continue
            working = list(device.pixels)
            touched: set[int] = set()
            for vehicle_id in sorted(vehicle_ids):
                vehicle = self.config.vehicles[vehicle_id]
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

    async def _apply_channels(
        self,
        controller: str,
        assignments: list[tuple[list[int], str, tuple[int, int, int] | None]],
        force: bool = False,
    ) -> None:
        """Setzt oder löscht RGB-Anteile, ohne andere Kanäle desselben Pixels zu überschreiben."""
        device = self.pool.get(controller)
        if device is None:
            raise KeyError(f"Controller {controller} is not connected")
        working = list(device.pixels)
        touched: set[int] = set()
        for leds, anteil, color in assignments:
            components = expand_anteil(anteil)
            for idx in leds:
                ensure_pixel(working, idx)
                touched.add(idx)
                if color is None:
                    working[idx] = clear_components(working[idx], components)
                else:
                    working[idx] = set_components(working[idx], components, color)
        updates: dict[int, tuple[int, int, int]] = {}
        for idx in touched:
            previous = device.pixels[idx] if idx < len(device.pixels) else (0, 0, 0)
            if force or working[idx] != previous:
                updates[idx] = working[idx]
        if updates:
            await self._set_leds(controller, updates)

    async def _set_leds(self, controller: str, updates: dict[int, tuple[int, int, int]]) -> None:
        device = self.pool.get(controller)
        if device is None:
            raise KeyError(f"Controller {controller} is not connected")
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
