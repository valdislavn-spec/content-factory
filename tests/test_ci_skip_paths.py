"""SKIP вместо падения, когда внешний сервис/аккаунт недоступен.

Регрессия: `flights-digest` падал каждый день при отсутствии секрета
TRAVELPAYOUTS_TOKEN (код 2), а `Mastodon growth` — с трейсбеком на 401,
когда аккаунт заблокирован страйком. CI не должен краснеть из-за
известного состояния конфигурации.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from content_factory.utils import account_unavailable

ROOT = Path(__file__).resolve().parents[1]


def _clean_env(*drop: str) -> dict:
    env = {key: value for key, value in os.environ.items() if key not in drop}
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def test_account_unavailable_detects_strike_and_auth() -> None:
    strike = '{"mastodon": {"ok": false, "error": "HTTP 401 mastodon.social: {\\"error\\":\\"Login is currently disabled.\\"}"}}'
    assert account_unavailable(strike) is True
    assert account_unavailable("HTTP 403 forbidden") is True
    assert account_unavailable("invalid access token") is True
    assert account_unavailable("сеть недоступна mastodon.social: timed out") is False
    assert account_unavailable("") is False
    assert account_unavailable(None) is False


def test_flights_digest_skips_without_token() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "flights_digest.py"), "--origin", "ALA", "--top", "1"],
        cwd=str(ROOT), env=_clean_env("TRAVELPAYOUTS_TOKEN"), capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "SKIP" in result.stdout


def test_mastodon_growth_skips_without_credentials() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mastodon_growth.py"), "--all"],
        cwd=str(ROOT), env=_clean_env("MASTODON_BASE_URL", "MASTODON_TOKEN"),
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "SKIP" in result.stdout
