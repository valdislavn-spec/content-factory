"""Telegram-здоровье аккаунта: разбор @SpamBot, аудит сессий, скоринг, flood-wait.

Чистые функции без сети — их используют:
    * ``scripts/tg_account_health.py`` (bot- и user-режимы);
    * тесты.

Что важно: user-режим работает только через **официальный MTProto** (Telethon) с
нашей собственной сессией; никаких tdata/чужих сессий, массовых действий и
автоматических сообщений — только чтение и один ``/start`` для @SpamBot.
"""
from __future__ import annotations

import ipaddress
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

CLEAN_PATTERNS = (
    r"no limits",
    r"not limited",
    r"free as a bird",
    r"no restrictions",
    r"can.?t see any restrictions",
    r"нет ограничен",
    r"не ограничен",
    r"ограничений.{0,40}нет",
    r"нет.{0,10}ограничен",
)
LIMITED_PATTERNS = (
    r"limited",
    r"restricted",
    r"restriction",
    r"spam",
    r"suspicious",
    r"abuse",
    r"can.?t send messages",
    r"can.?t write",
    r"ограничен",
    r"спам",
    r"подозр",
)


class TgHealthError(RuntimeError):
    """Ошибка проверки здоровья Telegram-аккаунта."""


# ---------------------------------------------------------------------------
# @SpamBot
# ---------------------------------------------------------------------------


def parse_spambot_reply(text: str) -> Dict[str, Any]:
    """Классифицирует ответ @SpamBot: clean / limited / unknown."""
    value = str(text or "").strip().lower()
    if not value:
        return {"status": "unknown", "details": "пустой ответ"}
    clean = any(re.search(pattern, value) for pattern in CLEAN_PATTERNS)
    # clean-фразы приоритетнее: «нет ограничений» содержит слово «ограничен»
    if clean:
        return {"status": "clean", "details": "ограничений нет"}
    limited = any(re.search(pattern, value) for pattern in LIMITED_PATTERNS)
    if limited:
        # цитата для отчёта — первая строка с ограничением
        line = next(
            (line.strip() for line in str(text).splitlines() if any(re.search(p, line.lower()) for p in LIMITED_PATTERNS)),
            str(text).strip()[:200],
        )
        return {"status": "limited", "details": line[:300]}
    return {"status": "unknown", "details": str(text).strip()[:300]}


# ---------------------------------------------------------------------------
# Сессии/авторизации
# ---------------------------------------------------------------------------


def mask_ip(value: str) -> str:
    """Маскирует IP для отчёта: 1.2.3.4 → 1.2.*.*, IPv6 → префикс /32."""
    text = str(value or "").strip()
    if not text:
        return "—"
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return "—"
    if isinstance(address, ipaddress.IPv4Address):
        parts = str(address).split(".")
        return f"{parts[0]}.{parts[1]}.*.*"
    return str(address).split(":")[0] + ":…"


def _to_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _days_ago(moment: Optional[datetime], now: Optional[datetime] = None) -> Optional[int]:
    if moment is None:
        return None
    current = now or datetime.now(timezone.utc)
    return max(0, int((current - moment).total_seconds() // 86400))


def summarize_auth(raw: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    """Превращает account.GetAuthorizations.authorizations[i] в безопасный словарь."""
    active = _to_datetime(raw.get("date_active") or raw.get("date_created"))
    current = bool(raw.get("current"))
    app_name = str(raw.get("app_name") or "").strip()
    device = str(raw.get("device_model") or "").strip()
    platform = str(raw.get("platform") or "").strip()
    suspicious = False
    reasons: List[str] = []
    if not current and not app_name and not device:
        suspicious = True
        reasons.append("нет названия приложения/устройства")
    if not current and _days_ago(active, now) is not None and _days_ago(active, now) < 30:
        reasons.append("недавняя сторонняя сессия — проверьте")
    return {
        "app": app_name or "—",
        "device": device or "—",
        "platform": platform or "—",
        "country": str(raw.get("country") or "—"),
        "ip": mask_ip(str(raw.get("ip") or "")),
        "current": current,
        "days_ago": _days_ago(active, now),
        "suspicious": suspicious,
        "reasons": reasons,
    }


def sessions_report(raws: Iterable[Dict[str, Any]], now: Optional[datetime] = None) -> Dict[str, Any]:
    sessions = [summarize_auth(raw, now) for raw in raws or []]
    return {
        "total": len(sessions),
        "current": sum(1 for session in sessions if session["current"]),
        "other": sum(1 for session in sessions if not session["current"]),
        "suspicious": sum(1 for session in sessions if session["suspicious"]),
        "sessions": sessions,
    }


# ---------------------------------------------------------------------------
# Скор
# ---------------------------------------------------------------------------


def score_account(
    *,
    spambot_status: str = "unknown",
    sessions: Optional[Dict[str, Any]] = None,
    twofa: Optional[bool] = None,
    bot_ok: bool = True,
) -> Dict[str, Any]:
    """Оценка 0–100 и рекомендации. Не заменяет @SpamBot — только ориентир."""
    score = 100
    reasons: List[str] = []
    if not bot_ok:
        score -= 5
        reasons.append("бот не отвечает/не админ — проверьте Bot API")
    if spambot_status == "limited":
        score -= 60
        reasons.append("@SpamBot сообщает об ограничениях — оспорьте в @SpamBot")
    elif spambot_status != "clean":
        score -= 10
        reasons.append("@SpamBot не дал однозначного ответа — проверьте вручную")
    if twofa is False:
        score -= 10
        reasons.append("не включена 2FA")
    if sessions:
        if sessions.get("suspicious"):
            score -= 15
            reasons.append("есть подозрительные сессии — завершите их")
        if sessions.get("other", 0) > 3:
            score -= 10
            reasons.append("много сторонних сессий — проверьте устройства")
    score = max(0, min(100, score))
    grade = "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 50 else "D"
    return {"score": score, "grade": grade, "reasons": reasons}


# ---------------------------------------------------------------------------
# Flood-wait (Bot API 429)
# ---------------------------------------------------------------------------


def extract_retry_after(payload: Any) -> Optional[float]:
    """Достаёт retry_after из ответа Bot API/Telethon FloodWait."""
    if isinstance(payload, dict):
        params = payload.get("parameters") or {}
        if isinstance(params, dict) and params.get("retry_after") is not None:
            try:
                return float(params["retry_after"])
            except (TypeError, ValueError):
                return None
        for key in ("retry_after", "seconds"):
            if payload.get(key) is not None:
                try:
                    return float(payload[key])
                except (TypeError, ValueError):
                    return None
    return None


# ---------------------------------------------------------------------------
# Вспомогательное
# ---------------------------------------------------------------------------


def looks_like_session_string(value: str) -> bool:
    """Строка Telethon StringSession: длинная base64-подобная строка."""
    text = str(value or "").strip()
    if len(text) < 100 or " " in text or "/" in text or text.endswith(".session"):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_\-=+/]+", text))


def normalize_ref(value: str) -> str:
    """'@SpamBot' / 'SpamBot' / 'https://t.me/SpamBot' → 'SpamBot'."""
    text = str(value or "").strip()
    if "t.me/" in text:
        text = text.split("t.me/", 1)[1]
    text = text.lstrip("@").strip("/")
    match = re.fullmatch(r"([A-Za-z0-9_]{4,})", text)
    return match.group(1) if match else text
