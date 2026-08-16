"""Einstieg: bidib2wled / python -m bidib2wled"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import uvicorn
from platformdirs import user_config_dir

from bidib2wled.config import save_config
from bidib2wled.service import Service
from bidib2wled.web import create_app


def default_config_path() -> Path:
    cwd = Path.cwd() / "config.yaml"
    if cwd.exists():
        return cwd
    return Path(user_config_dir("bidib2wled", appauthor=False)) / "config.yaml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BiDiB2WLED – BiDiB-Knoten für WLED")
    parser.add_argument("--config", type=Path, default=None, help="Pfad zur config.yaml")
    parser.add_argument("--host", default=None, help="Web-Bind-Adresse (Standard aus YAML / 0.0.0.0)")
    parser.add_argument("--port", type=int, default=None, help="Web-Port (Standard 8080)")
    parser.add_argument("--simulate", action="store_true", help="Kein echtes WLED, nur Log/Simulation")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config_path = args.config or default_config_path()
    if not config_path.exists():
        logging.getLogger(__name__).info("Leere Konfiguration wird angelegt: %s", config_path)
        from bidib2wled.config import default_config

        save_config(config_path, default_config())

    service = Service(config_path, simulate=args.simulate)
    if args.host:
        service.config.web.host = args.host
    if args.port:
        service.config.web.port = args.port

    host = service.config.web.host
    port = service.config.web.port
    app = create_app(service)

    @app.on_event("startup")
    async def _startup() -> None:
        await service.start()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await service.stop()

    if host in ("0.0.0.0", "::"):
        logging.getLogger(__name__).info(
            "Weboberfläche lauscht auf allen Netzwerkschnittstellen (%s:%s). "
            "Im Browser z. B. http://127.0.0.1:%s – von anderen Rechnern über die LAN-IP dieses Hosts.",
            host,
            port,
            port,
        )
    else:
        logging.getLogger(__name__).info("Weboberfläche: http://%s:%s", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
