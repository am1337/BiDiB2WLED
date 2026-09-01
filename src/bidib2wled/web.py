"""FastAPI-Weboberfläche und Konfigurations-API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

STATIC_DIR = Path(__file__).resolve().parent / "static"


class ClaimBody(BaseModel):
    name: str
    mac: str | None = None
    mdns: str | None = None
    ip: str | None = None
    port: int = 80
    leds: int | None = None


class SwitchBody(BaseModel):
    object_id: str
    aspect: int = 1


class IdentifyBody(BaseModel):
    controller: str
    index: int
    output: int = 0


class AddressBody(BaseModel):
    object_id: str
    address: int = Field(ge=0, le=255)


class InsertLedsBody(BaseModel):
    controller: str
    output: int = 0
    after: int = Field(ge=-1, description="Lokaler 0-basierter Index der LED, nach der eingefügt wird")
    count: int = Field(ge=1, le=255)


class DeleteLedsBody(BaseModel):
    controller: str
    output: int = 0
    start: int = Field(ge=0, description="Lokaler 0-basierter Index der ersten zu löschenden LED")
    count: int = Field(ge=1, le=255)


def create_app(service: "Service") -> FastAPI:
    app = FastAPI(title="BiDiB2WLED", version="0.1.0")

    @app.get("/api/status")
    async def status() -> dict[str, Any]:
        return service.status()

    @app.get("/api/config")
    async def get_config() -> dict[str, Any]:
        return service.config.model_dump(by_alias=True, exclude_none=True)

    @app.put("/api/config")
    async def put_config(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return await service.replace_config(payload)
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/reload")
    async def reload() -> dict[str, Any]:
        try:
            await service.reload_from_disk()
            return {"ok": True}
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/discovery")
    async def discovery() -> dict[str, Any]:
        return {"unbound": [item.__dict__ for item in service.unbound_controllers()]}

    @app.post("/api/controllers/claim")
    async def claim(body: ClaimBody) -> dict[str, Any]:
        try:
            await service.claim_controller(
                name=body.name, mac=body.mac, mdns=body.mdns, ip=body.ip, port=body.port, leds=body.leds
            )
            return {"ok": True}
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/controllers/manual")
    async def manual(body: ClaimBody) -> dict[str, Any]:
        try:
            await service.claim_controller(
                name=body.name, mac=body.mac, mdns=body.mdns, ip=body.ip, port=body.port, leds=body.leds
            )
            return {"ok": True}
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/switch")
    async def switch(body: SwitchBody) -> dict[str, Any]:
        try:
            await service.engine.switch(body.object_id, body.aspect, source="ui")
            return {"ok": True}
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/identify")
    async def identify(body: IdentifyBody) -> dict[str, Any]:
        try:
            await service.engine.identify_led(body.controller, body.index, body.output)
            return {"ok": True}
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/address")
    async def set_address(body: AddressBody) -> dict[str, Any]:
        try:
            return await service.set_object_address(body.object_id, body.address)
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/leds/insert")
    async def insert_leds(body: InsertLedsBody) -> dict[str, Any]:
        try:
            result = await service.insert_leds(body.controller, body.output, body.after, body.count)
            result["status"] = service.status()
            return result
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/leds/delete")
    async def delete_leds(body: DeleteLedsBody) -> dict[str, Any]:
        try:
            result = await service.delete_leds(body.controller, body.output, body.start, body.count)
            result["status"] = service.status()
            return result
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/pairing/accept")
    async def pairing_accept() -> dict[str, str]:
        await service.bidib.accept_pairing()
        return {"ok": "pairing"}

    @app.post("/api/pairing/reject")
    async def pairing_reject() -> dict[str, str]:
        await service.bidib.reject_pairing()
        return {"ok": "rejected"}

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
