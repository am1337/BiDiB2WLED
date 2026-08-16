"""mDNS-Erkennung von WLED-Controllern (_wled._tcp)."""

from __future__ import annotations

import asyncio
import logging
import socket
from typing import Callable

from zeroconf import ServiceBrowser, ServiceInfo, ServiceStateChange, Zeroconf
from zeroconf.asyncio import AsyncZeroconf

from bidib2wled.wled import WledInfo, WledPool, normalize_mac

log = logging.getLogger(__name__)

WLED_TYPE = "_wled._tcp.local."
BIDIB_TYPE = "_bidib._tcp.local."


class WledDiscovery:
    def __init__(self, pool: WledPool, enabled: bool = True) -> None:
        self.pool = pool
        self.enabled = enabled
        self.found: dict[str, WledInfo] = {}  # mac -> info
        self._aiozc: AsyncZeroconf | None = None
        self._browser: ServiceBrowser | None = None
        self._unbound: dict[str, WledInfo] = {}
        self._listeners: list[Callable[[], None]] = []

    def on_change(self, callback: Callable[[], None]) -> None:
        self._listeners.append(callback)

    def _notify(self) -> None:
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:
                log.exception("Discovery-Listener")

    async def start(self) -> None:
        if not self.enabled:
            return
        self._aiozc = AsyncZeroconf()
        loop = asyncio.get_running_loop()

        def _on_change(
            zeroconf: Zeroconf,
            service_type: str,
            name: str,
            state_change: ServiceStateChange,
        ) -> None:
            asyncio.run_coroutine_threadsafe(
                self._handle(zeroconf, service_type, name, state_change), loop
            )

        self._browser = ServiceBrowser(
            self._aiozc.zeroconf, [WLED_TYPE], handlers=[_on_change]
        )
        log.info("mDNS-Suche nach %s gestartet", WLED_TYPE)

    async def stop(self) -> None:
        if self._browser:
            self._browser.cancel()
            self._browser = None
        if self._aiozc:
            await self._aiozc.async_close()
            self._aiozc = None

    async def _handle(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        if state_change is ServiceStateChange.Removed:
            return
        try:
            service = await self._aiozc.async_get_service_info(service_type, name)
        except Exception:
            service = zeroconf.get_service_info(service_type, name)
        if service is None:
            return
        ip = _first_ip(service)
        if not ip:
            return
        port = service.port or 80
        probed = await self.pool.probe(ip, port)
        if probed is None:
            mdns_name = name.split(".")[0]
            probed = WledInfo(name=mdns_name, mac="", ip=ip, port=port, mdns=mdns_name)
        else:
            probed.mdns = name.split(".")[0]
            probed.ip = ip
            probed.port = port
        if probed.mac:
            self.found[probed.mac] = probed
            self._unbound[probed.mac] = probed
            log.info("WLED gefunden: %s %s (%s LEDs)", probed.name, ip, probed.led_count)
            self._notify()

    def unbound(self, bound_macs: set[str]) -> list[WledInfo]:
        bound = {normalize_mac(mac) for mac in bound_macs if mac}
        return [info for mac, info in self.found.items() if mac not in bound]

    def match_controller(self, mdns: str | None, mac: str | None, ip: str | None) -> WledInfo | None:
        if mac:
            info = self.found.get(normalize_mac(mac))
            if info:
                return info
        if mdns:
            needle = mdns.lower().removesuffix(".local")
            for info in self.found.values():
                if (info.mdns or "").lower() == needle or info.name.lower() == needle:
                    return info
        if ip:
            for info in self.found.values():
                if info.ip == ip:
                    return info
        return None


def _first_ip(service: ServiceInfo) -> str | None:
    parsed = service.parsed_addresses()
    for addr in parsed:
        if ":" not in addr:
            return addr
    return parsed[0] if parsed else None


async def advertise_bidib_node(
    aiozc: AsyncZeroconf,
    *,
    instance: str,
    port: int,
    uid_hex: str,
    user: str,
    prod: str,
) -> ServiceInfo:
    hostname = socket.gethostname().split(".")[0]
    info = ServiceInfo(
        BIDIB_TYPE,
        f"{instance}.{BIDIB_TYPE}",
        port=port,
        properties={
            "uid": uid_hex,
            "prod": prod,
            "user": user,
            "node": "1",
        },
        server=f"{hostname}.local.",
    )
    await aiozc.async_register_service(info)
    return info


async def advertise_http(aiozc: AsyncZeroconf, port: int) -> ServiceInfo:
    hostname = socket.gethostname().split(".")[0]
    info = ServiceInfo(
        "_http._tcp.local.",
        "BiDiB2WLED._http._tcp.local.",
        port=port,
        properties={"path": "/"},
        server=f"{hostname}.local.",
    )
    await aiozc.async_register_service(info)
    return info
