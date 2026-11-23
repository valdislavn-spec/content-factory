"""The automated Pinterest publisher must only send traffic through /r/{code}."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from scripts.post_pins import is_tracked_link as post_pins_tracked


ROOT = Path(__file__).resolve().parents[1]
AUTO_PUBLISH = ROOT / "growth-funnel" / "auto_publish.py"


def _auto_publish_module():
    spec = importlib.util.spec_from_file_location("growth_auto_publish", AUTO_PUBLISH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_pinterest_queue_uses_tracked_links():
    queue = json.loads((ROOT / "growth-funnel" / "queue.json").read_text(encoding="utf-8"))
    pinterest = [item for item in queue if item.get("platform") == "pinterest"]
    assert pinterest, "expected at least one Pinterest queue item"
    for item in pinterest:
        assert post_pins_tracked(item["link"]), item["id"]


def test_tracked_link_guard():
    assert post_pins_tracked("https://links-tracker.valdislav-n.workers.dev/r/pin-en-09-hotel-price")
    assert not post_pins_tracked("https://aviasales.tpk.ro/abc123")
    assert not post_pins_tracked("")
    assert not post_pins_tracked("https://valdislavn-spec.github.io/content-factory/go/x.html")


def test_auto_publish_rejects_direct_affiliate_link():
    module = _auto_publish_module()
    result = module.post_pinterest(
        {"link": "https://aviasales.tpk.ro/abc123", "board_id_env": "PINTEREST_BOARD_ID"},
        {"PINTEREST_ACCESS_TOKEN": "token", "PINTEREST_BOARD_ID": "42"},
    )
    assert result["ok"] is False
    assert "tracked" in result["error"]


def test_auto_publish_accepts_tracked_link_before_image_validation():
    module = _auto_publish_module()
    result = module.post_pinterest(
        {"link": "https://links-tracker.valdislav-n.workers.dev/r/pin-en-09-hotel-price",
         "board_id_env": "PINTEREST_BOARD_ID", "image": "missing.png"},
        {"PINTEREST_ACCESS_TOKEN": "token", "PINTEREST_BOARD_ID": "42"},
    )
    assert result["ok"] is False
    assert "картинка не найдена" in result["error"]


def test_affiliate_pin_sidecars_use_tracked_links():
    pins = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (ROOT / "docs" / "assets" / "pins").glob("*.json")
        if path.name != "index.json"
    ]
    affiliate = [pin for pin in pins if pin.get("affiliate")]
    assert affiliate, "expected affiliate pin sidecars"
    for pin in affiliate:
        link = (pin.get("pin") or {}).get("link", "")
        assert post_pins_tracked(link), pin.get("image_url", "")


def test_pin_config_uses_tracked_links():
    text = (ROOT / "config" / "pins.yaml").read_text(encoding="utf-8")
    assert "/r/tf-pin-" in text
    assert "/go/" not in text


def test_travel_finds_meta_and_publisher_guard_are_tracked():
    from scripts.pinterest_travel_finds import is_tracked_link
    entries = json.loads((ROOT / "docs" / "travel-finds" / "pins" / "meta.json").read_text(encoding="utf-8"))
    assert entries
    for entry in entries:
        link = (entry.get("payload") or {}).get("link", "")
        assert is_tracked_link(link), entry.get("slug")
    assert is_tracked_link("https://aviasales.tpk.ro/abc") is False
    assert is_tracked_link("https://valdislavn-spec.github.io/content-factory/go/x.html") is False
