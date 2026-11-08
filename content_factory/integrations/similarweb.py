"""Similarweb: бесплатные оценки трафика сайтов (endpoint расширения).

Публичный (недокументированный) endpoint, который использует Chrome-расширение
Similarweb; API-ключи не нужны:

    https://data.similarweb.com/api/v1/data?domain=<domain>

Отдаёт оценку визитов в месяц, глобальный/страновой/категорийный рейтинг,
вовлечённость (отказы, страницы за визит, время на сайте), категорию,
доли стран и источники трафика.

Особенности:
* endpoint отдаёт 403 из РФ (CloudFront geo-block) — запускайте из GitHub
  Actions (US) или через VPN; для этого и написан ``scripts/competitor_traffic.py``;
* лимиты запросов не документированы: не больше ~1 запроса в 2–3 секунды
  и небольшими пачками доменов.

Модуль намеренно не бросает исключения наружу: каждая строка результата
содержит либо данные, либо поле ``error``.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

API_ENDPOINT = "https://data.similarweb.com/api/v1/data?domain={domain}"
DEFAULT_TIMEOUT = 20.0
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Группы конкурентов по темам каналов завода (можно переопределить в CLI).
DEFAULT_COMPETITORS: Dict[str, List[str]] = {
    "ai": [
        "techcrunch.com",
        "theverge.com",
        "wired.com",
        "mit.edu",
        "venturebeat.com",
        "arstechnica.com",
    ],
    "crypto": [
        "cointelegraph.com",
        "coindesk.com",
        "decrypt.co",
        "theblock.co",
        "bitcoinmagazine.com",
        "blockworks.co",
    ],
    "sports": [
        "espn.com",
        "cbssports.com",
        "si.com",
        "theathletic.com",
        "sportingnews.com",
        "bleacherreport.com",
    ],
}


# ---------------------------------------------------------------------------
# вспомогательные форматтеры
# ---------------------------------------------------------------------------


def _fmt_int(value: Any) -> str:
    try:
        return f"{int(float(value)):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_pages(value: Any) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_duration(value: Any) -> str:
    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        return "—"
    if seconds <= 0:
        return "—"
    minutes, sec = divmod(seconds, 60)
    return f"{minutes}м {sec:02d}с"


# ---------------------------------------------------------------------------
# домены и запрос
# ---------------------------------------------------------------------------


def normalize_domain(value: str) -> str:
    """``https://www.CoinDesk.com/rss`` → ``coindesk.com``."""
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if "//" in text:
        text = urllib.parse.urlparse(text).netloc or text
    text = text.split("/", 1)[0].split("?", 1)[0].strip()
    if text.startswith("www."):
        text = text[4:]
    return text


def endpoint(domain: str) -> str:
    return API_ENDPOINT.format(domain=urllib.parse.quote(domain))


def _http_get_json(url: str, timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.similarweb.com/",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:  # 403 из РФ, 429 при лимите
        raise RuntimeError(f"HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"network: {getattr(exc, 'reason', exc)}") from exc
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("ответ не JSON") from exc
    if not isinstance(data, dict):
        raise RuntimeError("неожиданный формат ответа")
    return data


# ---------------------------------------------------------------------------
# разбор ответа
# ---------------------------------------------------------------------------


def _first_number(*values: Any) -> Optional[float]:
    for value in values:
        if isinstance(value, bool):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        return number
    return None


def _rank_value(block: Any) -> Optional[float]:
    """Rank приходит как ``{"Rank": 123}``, число или строка."""
    if isinstance(block, dict):
        return _first_number(block.get("Rank"), block.get("rank"))
    return _first_number(block)


def _last_monthly_visits(block: Any) -> Optional[float]:
    if not isinstance(block, dict) or not block:
        return None
    try:
        key = max(block.keys())
    except (TypeError, ValueError):
        return None
    return _first_number(block.get(key))


def _top_countries(block: Any, limit: int = 3) -> List[Dict[str, Any]]:
    if not isinstance(block, list):
        return []
    rows: List[Dict[str, Any]] = []
    for item in block:
        if not isinstance(item, dict):
            continue
        shares = _first_number(item.get("Value"), item.get("value"), item.get("Share"))
        if shares is None:
            continue
        rows.append({"country": item.get("Country") or item.get("country") or "?", "share": shares})
    rows.sort(key=lambda row: row["share"], reverse=True)
    return rows[:limit]


def _traffic_sources(block: Any) -> Dict[str, float]:
    if not isinstance(block, dict):
        return {}
    result: Dict[str, float] = {}
    for name, value in block.items():
        share = _first_number(value)
        if share is not None:
            result[str(name)] = share
    return result


def parse_payload(domain: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Приводит сырой ответ Similarweb к плоской строке отчёта."""
    engagements = data.get("Engagements") if isinstance(data.get("Engagements"), dict) else {}
    visits = _first_number(
        engagements.get("Visits"),
        data.get("Visits"),
    ) or _last_monthly_visits(data.get("EstimatedMonthlyVisits"))

    row: Dict[str, Any] = {
        "domain": domain,
        "visits": visits,
        "global_rank": _rank_value(data.get("GlobalRank")),
        "country_rank": _rank_value(data.get("CountryRank")),
        "category_rank": _rank_value(data.get("CategoryRank")),
        "category": (data.get("Category") or "") if isinstance(data.get("Category"), str) else "",
        "bounce_rate": _first_number(engagements.get("BounceRate")),
        "pages_per_visit": _first_number(engagements.get("PagePerVisit")),
        "time_on_site": _first_number(engagements.get("TimeOnSite")),
        "top_countries": _top_countries(data.get("TopCountryShares")),
        "traffic_sources": _traffic_sources(data.get("TrafficSources")),
    }
    return row


def fetch_domain(domain: str, timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Данные по одному домену; при ошибке — ``{"domain": ..., "error": ...}``."""
    normalized = normalize_domain(domain)
    if not normalized:
        return {"domain": str(domain), "error": "пустой домен"}
    try:
        payload = _http_get_json(endpoint(normalized), timeout=timeout)
    except Exception as exc:  # noqa: BLE001 — CLI не должен падать из-за одного домена
        logger.warning("similarweb %s: %s", normalized, exc)
        return {"domain": normalized, "error": str(exc)}
    return parse_payload(normalized, payload)


def fetch_many(domains: Iterable[str], delay: float = 2.5, timeout: float = DEFAULT_TIMEOUT) -> List[Dict[str, Any]]:
    """Пачка доменов с паузой между запросами (бережём лимиты Similarweb)."""
    rows: List[Dict[str, Any]] = []
    items = [item for item in domains if str(item or "").strip()]
    for index, domain in enumerate(items):
        if index:
            time.sleep(max(0.0, delay))
        rows.append(fetch_domain(domain, timeout=timeout))
    return rows


# ---------------------------------------------------------------------------
# вывод
# ---------------------------------------------------------------------------


def format_markdown(rows: Iterable[Dict[str, Any]], title: str = "Конкуренты — Similarweb") -> str:
    rows = [row for row in rows if isinstance(row, dict)]
    ok = [row for row in rows if not row.get("error")]
    errors = [row for row in rows if row.get("error")]
    lines = [f"## {title}", ""]
    if not ok:
        lines.append("_Нет данных: endpoint недоступен (из РФ отдаёт 403 — запускайте из GitHub Actions)._")
    else:
        lines.append("| Домен | Визиты/мес | Глоб. ранг | Отказы | Стр./визит | Время | Категория |")
        lines.append("|---|---:|---:|---:|---:|---:|---|")
        for row in sorted(ok, key=lambda item: item.get("visits") or 0, reverse=True):
            lines.append(
                "| {domain} | {visits} | {rank} | {bounce} | {pages} | {time} | {category} |".format(
                    domain=row.get("domain", "—"),
                    visits=_fmt_int(row.get("visits")),
                    rank=_fmt_int(row.get("global_rank")),
                    bounce=_fmt_pct(row.get("bounce_rate")),
                    pages=_fmt_pages(row.get("pages_per_visit")),
                    time=_fmt_duration(row.get("time_on_site")),
                    category=row.get("category") or "—",
                )
            )
    if errors:
        lines.append("")
        lines.append("Ошибки: " + ", ".join(f"{row.get('domain')} ({row.get('error')})" for row in errors))
    return "\n".join(lines).strip() + "\n"


def format_telegram(rows: Iterable[Dict[str, Any]], limit: int = 5) -> str:
    ok = [row for row in rows if isinstance(row, dict) and not row.get("error")]
    lines = ["<b>Конкуренты — Similarweb</b>"]
    for row in sorted(ok, key=lambda item: item.get("visits") or 0, reverse=True)[:limit]:
        lines.append(
            "• {domain}: {visits} визитов/мес, ранг {rank}".format(
                domain=row.get("domain", "—"),
                visits=_fmt_int(row.get("visits")),
                rank=_fmt_int(row.get("global_rank")),
            )
        )
    if not ok:
        lines.append("нет данных (endpoint отдаёт 403 из РФ — нужно запускать в Actions)")
    return "\n".join(lines)
