import pytest

from bidib2wled.config import AppConfig, load_config, save_config
from bidib2wled.service import Service


@pytest.mark.asyncio
async def test_insert_leds_via_service(tmp_path):
    cfg = AppConfig.model_validate(
        {
            "controller": [{"name": "dorf", "ip": "127.0.0.1", "leds": 10}],
            "lampen": {
                "l1": {"controller": "dorf", "leds": [0]},
                "l6": {"controller": "dorf", "leds": [5]},
                "l7": {"controller": "dorf", "leds": [6]},
            },
        }
    )
    path = tmp_path / "config.yaml"
    save_config(path, cfg)
    svc = Service(path, simulate=True)
    svc.pool.bind("dorf", ip="127.0.0.1", leds=10)
    result = await svc.insert_leds("dorf", 0, 4, 3)
    assert result["ok"] is True
    assert result["first_shifted"] == 5
    assert result["shifted"] == 2
    assert svc.config.lampen["l1"].leds == [0]
    assert svc.config.lampen["l6"].leds == [8]
    assert svc.config.lampen["l7"].leds == [9]
    reloaded = load_config(path)
    assert reloaded.lampen["l6"].leds == [8]
    with pytest.raises(ValueError, match="WLED"):
        await svc.insert_leds("dorf", 0, 4, 8)


@pytest.mark.asyncio
async def test_delete_leds_via_service_ignores_smaller_wled(tmp_path):
    cfg = AppConfig.model_validate(
        {
            "controller": [{"name": "dorf", "ip": "127.0.0.1", "leds": 10}],
            "lampen": {
                "l1": {"controller": "dorf", "leds": [0]},
                "l6": {"controller": "dorf", "leds": [8]},
                "l7": {"controller": "dorf", "leds": [9]},
            },
        }
    )
    path = tmp_path / "config.yaml"
    save_config(path, cfg)
    svc = Service(path, simulate=True)
    svc.pool.bind("dorf", ip="127.0.0.1", leds=7)
    result = await svc.delete_leds("dorf", 0, 5, 3)
    assert result["ok"] is True
    assert result["first_removed"] == 5
    assert result["shifted"] == 2
    assert result["wled_leds"] == 7
    assert svc.config.lampen["l1"].leds == [0]
    assert svc.config.lampen["l6"].leds == [5]
    assert svc.config.lampen["l7"].leds == [6]
    assert result["config_leds"] == 7
    assert result["delta"] == 0
    reloaded = load_config(path)
    assert reloaded.lampen["l6"].leds == [5]
