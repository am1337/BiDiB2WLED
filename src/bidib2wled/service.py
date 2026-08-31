"""Dienst-Orchestrierung."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from zeroconf.asyncio import AsyncZeroconf

from bidib2wled.adapters import uid_to_hex
from bidib2wled.adapters.netbidib import NetBidibAdapter
from bidib2wled.config import AppConfig, ControllerConfig, host_setup_info, load_config, save_config
from bidib2wled.core import Engine
from bidib2wled.wled import WledPool, normalize_mac
from bidib2wled.wled.discovery import WledDiscovery, advertise_bidib_node, advertise_http

log = logging.getLogger(__name__)


class Service:
    def __init__(self, config_path: Path, simulate: bool = False) -> None:
        self.config_path = config_path
        self.simulate = simulate
        self.config = load_config(config_path)
        self.pool = WledPool(simulate=simulate)
        self.engine = Engine(self.pool)
        self.discovery = WledDiscovery(self.pool, enabled=self.config.erkennung.mdns)
        self.bidib = NetBidibAdapter(self.engine, config_path, save_cb=self._save)
        self._aiozc: AsyncZeroconf | None = None
        self._bind_task: asyncio.Task | None = None
        self._watch_task: asyncio.Task | None = None
        self._mtime: float = 0.0

    def _save(self) -> None:
        self.config.adapter.netbidib = self.bidib.net_cfg
        save_config(self.config_path, self.config)
        if self.config_path.exists():
            self._mtime = self.config_path.stat().st_mtime

    def status(self) -> dict:
        bound = []
        for ctrl in self.config.controller:
            device = self.pool.get(ctrl.name)
            info = device.info if device else None
            ip = (info.ip if info else None) or ctrl.ip
            port = (info.port if info else None) or ctrl.port
            outputs = [item.to_dict() for item in info.outputs] if info and info.outputs else []
            if not outputs:
                total = (info.led_count if info else None) or ctrl.leds or 0
                outputs = [
                    {
                        "id": 0,
                        "start": 0,
                        "len": total,
                        "pin": None,
                        "label": f"Ausgang 1 ({total} LEDs)",
                    }
                ]
            bound.append(
                {
                    "name": ctrl.name,
                    "mac": ctrl.mac,
                    "mdns": ctrl.mdns,
                    "ip": ip,
                    "port": port,
                    "url": f"http://{ip}:{port}/" if ip else None,
                    "leds": info.led_count if info else ctrl.leds,
                    "outputs": outputs,
                    "reachable": info.reachable if info else False,
                    "simulate": self.simulate,
                    "effects": list(info.effects) if info else [],
                    "palettes": list(info.palettes) if info else [],
                    "warnings": list(info.warnings) if info else [],
                }
            )
        kind_labels = {
            "lampe": "Lampe",
            "haus": "Haus",
            "fenster": "Fenster",
            "gruppe": "Gruppe",
            "sequenz": "Sequenz",
            "signal": "Signal",
            "spezial": "Spezial",
            "fahrzeug": "Fahrzeug",
        }
        acc_map = self.bidib.accessory_map()
        acc_rev = {obj: anum for anum, obj in acc_map.items()}
        objects = []
        for obj_id in self.config.all_object_ids():
            st = self.engine.state_of(obj_id)
            kind = self.config.object_kind(obj_id) or "objekt"
            reported = st.reported_aspect()
            anum = acc_rev.get(obj_id)
            item = {
                "id": obj_id,
                "kind": kind,
                "kind_label": kind_labels.get(kind, kind),
                "on": bool(reported),
                "state": reported,
                "in_progress": st.in_progress,
                "error": st.error,
                "states": None,
                "accessory": anum,
                "address": anum,
                "info": host_setup_info(kind, anum),
            }
            if kind == "signal":
                begriffe = self.config.signale[obj_id].begriffe
                item["states"] = [{"value": key, "name": val.name} for key, val in sorted(begriffe.items())]
                item["on"] = None
            elif kind == "fahrzeug":
                modi = self.config.fahrzeuge[obj_id].resolved_modi()
                item["states"] = [{"value": key, "name": val.name} for key, val in sorted(modi.items())]
                item["on"] = None
            objects.append(item)
        pending = None
        if self.bidib.pending_pairing:
            pending = {
                "uid": self.bidib.pending_pairing.peer_uid,
                "prod": self.bidib.pending_pairing.prod,
                "user": self.bidib.pending_pairing.user,
            }
        peers = [
            {
                "uid": s.peer_hex,
                "prod": s.peer_prod,
                "user": s.peer_user,
                "paired": s.link_paired,
                "logged_on": s.logged_on,
                "rx": s.last_rx[:80].hex(),
                "rx_types": [f"0x{t:02x}" for t in s.rx_types[-12:]],
            }
            for s in self.bidib.sessions
        ]
        return {
            "config_path": str(self.config_path),
            "wizard": len(self.config.controller) == 0,
            "bidib": {
                "aktiv": self.config.adapter.netbidib.aktiv,
                "modus": self.config.adapter.netbidib.modus,
                "port": self.config.adapter.netbidib.port,
                "knotenname": self.config.adapter.netbidib.knotenname,
                "unique_id": uid_to_hex(self.bidib.uid),
                "logged_on": self.bidib.logged_session is not None,
                "sessions": len(self.bidib.sessions),
                "trusted": list(self.bidib.trusted),
                "pairing_open": self.bidib.pairing_open,
                "pending": pending,
                "peers": peers,
                "accessories": {str(k): v for k, v in self.bidib.accessory_map().items()},
            },
            "controllers": bound,
            "objects": objects,
            "usage": {
                "leds": self.config.led_usage(),
                "channels": self.config.led_channel_usage(),
                "objects": self.config.object_usage(),
            },
        }

    def unbound_controllers(self):
        bound = {c.mac for c in self.config.controller if c.mac}
        return self.discovery.unbound(bound)

    async def start(self) -> None:
        self.engine.load(self.config)
        self.bidib.configure(self.config)
        changed = self.config.ensure_accessories()
        if not self.config.adapter.netbidib.unique_id:
            self.config.adapter.netbidib.unique_id = uid_to_hex(self.bidib.uid)
            changed = True
        if changed:
            self._save()
        await self.pool.start()
        await self.discovery.start()
        await self._bind_all()
        await self.bidib.start()
        try:
            self._aiozc = AsyncZeroconf()
            await advertise_http(self._aiozc, self.config.web.port)
            if self.config.adapter.netbidib.aktiv and self.config.adapter.netbidib.modus == "server":
                await advertise_bidib_node(
                    self._aiozc,
                    instance=self.config.adapter.netbidib.knotenname,
                    port=self.config.adapter.netbidib.port,
                    uid_hex=uid_to_hex(self.bidib.uid),
                    user=self.config.adapter.netbidib.knotenname,
                    prod="BiDiB2WLED",
                )
        except Exception:
            log.exception("mDNS-Anzeige fehlgeschlagen")
        self._bind_task = asyncio.create_task(self._rebind_loop())
        self._mtime = self.config_path.stat().st_mtime if self.config_path.exists() else 0.0
        self._watch_task = asyncio.create_task(self._watch_loop())

    async def stop(self) -> None:
        for task in (self._bind_task, self._watch_task):
            if task:
                task.cancel()
        await self.bidib.stop()
        await self.discovery.stop()
        if self._aiozc:
            await self._aiozc.async_close()
        await self.pool.close()

    async def _bind_all(self) -> None:
        for ctrl in self.config.controller:
            await self._bind_one(ctrl)

    async def _bind_one(self, ctrl: ControllerConfig) -> None:
        found = self.discovery.match_controller(ctrl.mdns, ctrl.mac, ctrl.ip)
        ip = (found.ip if found else None) or ctrl.ip
        port = (found.port if found else None) or ctrl.port
        mac = (found.mac if found else None) or ctrl.mac or ""
        leds = (found.led_count if found else None) or ctrl.leds or 0
        if not ip:
            log.warning("Controller %s: keine IP (mDNS/Fallback)", ctrl.name)
            existing = self.pool.get(ctrl.name)
            if existing:
                existing.info.reachable = False
            return
        device = self.pool.bind(
            ctrl.name,
            ip=ip,
            port=port,
            mac=mac,
            leds=leds,
            mdns=ctrl.mdns,
            wled_name=found.name if found else ctrl.name,
        )
        try:
            await device.fetch_info()
        except Exception as exc:
            device.info.reachable = False
            log.warning("Controller %s Info: %s", ctrl.name, exc)
        changed = False
        if device.info.mac and ctrl.mac != device.info.mac:
            ctrl.mac = device.info.mac
            changed = True
        if device.info.ip and ctrl.ip != device.info.ip:
            ctrl.ip = device.info.ip
            changed = True
        if device.info.led_count and ctrl.leds != device.info.led_count:
            ctrl.leds = device.info.led_count
            changed = True
        if changed:
            self._save()

    async def _rebind_loop(self) -> None:
        while True:
            await asyncio.sleep(self.config.erkennung.interval_s)
            try:
                await self._bind_all()
            except Exception:
                log.exception("Rebind")

    async def _watch_loop(self) -> None:
        while True:
            await asyncio.sleep(2)
            if not self.config_path.exists():
                continue
            mtime = self.config_path.stat().st_mtime
            if mtime > self._mtime + 0.05:
                self._mtime = mtime
                try:
                    await self.reload_from_disk()
                    log.info("Konfiguration von Disk neu geladen")
                except Exception:
                    log.exception("Reload der YAML fehlgeschlagen, alte Konfiguration bleibt")

    async def reload_from_disk(self) -> None:
        config = load_config(self.config_path)
        await self.apply_config(config)

    async def replace_config(self, payload: dict) -> dict:
        config = AppConfig.model_validate(payload)
        config.ensure_accessories()
        save_config(self.config_path, config)
        self._mtime = self.config_path.stat().st_mtime
        await self.apply_config(config)
        return config.model_dump(by_alias=True)

    async def set_object_address(self, object_id: str, address: int) -> dict:
        self.config.set_accessory(object_id, address)
        self._save()
        self.bidib.configure(self.config)
        return self.status()

    def _output_info(self, controller: str, output: int) -> tuple[object, int, dict]:
        ctrl = self.config.controller_by_name(controller)
        if ctrl is None:
            raise ValueError(f"Unbekannter Controller: {controller}")
        device = self.pool.get(controller)
        wled_count = (device.info.led_count if device and device.info.led_count else None) or ctrl.leds or 0
        outputs = [item.to_dict() for item in device.info.outputs] if device and device.info.outputs else []
        if not outputs:
            outputs = [{"id": 0, "start": 0, "len": wled_count}]
        out = next((item for item in outputs if int(item["id"]) == int(output)), None)
        if out is None:
            raise ValueError(f"Ausgang {output} existiert nicht")
        return ctrl, int(wled_count), out

    def _led_delta(self, controller: str, wled_count: int) -> dict[str, int]:
        span = self.config.max_led_index(controller) + 1
        return {
            "wled_leds": int(wled_count),
            "config_leds": max(span, 0),
            "delta": max(span, 0) - int(wled_count),
        }

    async def insert_leds(self, controller: str, output: int, after: int, count: int) -> dict:
        """Fügt `count` LEDs nach lokaler LED `after` (0-basiert) ein und schiebt Folgeadressen."""
        _ctrl, wled_count, out = self._output_info(controller, output)
        length = int(out["len"] or 0)
        start = int(out["start"] or 0)
        if after < -1 or (length and after >= length):
            raise ValueError("LED liegt nicht auf diesem Ausgang")
        first_shifted = start + after + 1
        shifted = self.config.shift_controller_leds(controller, first_shifted, count, int(wled_count))
        self._save()
        self.engine.load(self.config)
        return {
            "ok": True,
            "controller": controller,
            "first_shifted": first_shifted,
            "count": count,
            "shifted": shifted,
            **self._led_delta(controller, wled_count),
        }

    async def delete_leds(self, controller: str, output: int, start_at: int, count: int) -> dict:
        """Entfernt `count` LEDs ab lokaler LED `start_at` (0-basiert) und zählt Folgeadressen herunter."""
        _ctrl, wled_count, out = self._output_info(controller, output)
        start = int(out["start"] or 0)
        if start_at < 0:
            raise ValueError("Bitte die erste zu löschende LED wählen")
        first_removed = start + start_at
        result = self.config.delete_controller_leds(controller, first_removed, count)
        self._save()
        self.engine.load(self.config)
        return {
            "ok": True,
            "controller": controller,
            "first_removed": first_removed,
            "count": count,
            "shifted": result["shifted"],
            "dropped": result["dropped"],
            **self._led_delta(controller, wled_count),
        }

    async def apply_config(self, config: AppConfig) -> None:
        old_port = self.config.adapter.netbidib.port
        old_mode = self.config.adapter.netbidib.modus
        old_aktiv = self.config.adapter.netbidib.aktiv
        self.config = config
        filled = self.config.ensure_accessories()
        self.engine.load(config)
        net_changed = (
            config.adapter.netbidib.port != old_port
            or config.adapter.netbidib.modus != old_mode
            or config.adapter.netbidib.aktiv != old_aktiv
        )
        if net_changed:
            await self.bidib.restart(config)
        else:
            self.bidib.configure(config)
        if filled:
            self._save()
        await self._bind_all()

    async def claim_controller(
        self,
        name: str,
        mac: str | None = None,
        mdns: str | None = None,
        ip: str | None = None,
        port: int = 80,
        leds: int | None = None,
    ) -> None:
        name = name.strip()
        if not name:
            raise ValueError("Name darf nicht leer sein")
        existing = self.config.controller_by_name(name)
        mac_n = normalize_mac(mac) if mac else None
        if existing:
            if mac_n:
                existing.mac = mac_n
            if mdns:
                existing.mdns = mdns
            if ip:
                existing.ip = ip
            existing.port = port
            if leds:
                existing.leds = leds
        else:
            self.config.controller.append(
                ControllerConfig(name=name, mac=mac_n, mdns=mdns, ip=ip, port=port, leds=leds)
            )
        self._save()
        ctrl = self.config.controller_by_name(name)
        assert ctrl is not None
        await self._bind_one(ctrl)
