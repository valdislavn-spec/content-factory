import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pinterest_conversions", ROOT / "scripts" / "pinterest_conversions.py"
)
pc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pc)


def test_sha256_hex_known_value():
    assert pc.sha256_hex("test@example.com") == hashlib.sha256(b"test@example.com").hexdigest()


def test_build_user_data_normalizes_and_hashes_email():
    data = pc.build_user_data(email="  Test@Example.COM ")
    assert len(data["em"]) == 1
    assert data["em"][0] == pc.sha256_hex("test@example.com")


def test_build_user_data_keeps_epik_raw():
    data = pc.build_user_data(click_id="epik_abc123")
    assert data == {"click_id": "epik_abc123"}


def test_build_user_data_requires_identifier():
    with pytest.raises(ValueError):
        pc.build_user_data()


def test_build_event_contains_required_fields():
    event = pc.build_event(
        event_name="lead",
        email="a@b.com",
        external_id="tg:1",
        event_id="evt-1",
        event_time=1700000000,
        source_url="https://example.com",
        value="9.5",
        currency="usd",
    )
    assert event["event_name"] == "lead"
    assert event["action_source"] == "web"
    assert event["event_time"] == 1700000000
    assert event["event_id"] == "evt-1"
    assert event["user_data"]["em"]
    assert event["custom_data"] == {"value": "9.50", "currency": "USD"}


def test_build_event_rejects_unknown_name():
    with pytest.raises(ValueError):
        pc.build_event(event_name="purchase", email="a@b.com")


def test_send_events_dry_run_returns_payload():
    event = pc.build_event(event_name="signup", email="a@b.com", event_id="evt-2")
    result = pc.send_events([event], dry_run=True)
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["payload"]["data"][0]["event_id"] == "evt-2"
