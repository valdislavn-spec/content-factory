"""Active partner-link resolution, validation and (optional) live checks.

Pins, cards and CSV imports must never ship dead or placeholder URLs: a pin with
a broken destination wastes the impression and violates Pinterest's link
quality rules.  This module is the single source of truth for:

* program → partner URL resolution from ``config/affiliate_links.yaml``
  (``programs.<name>.partner_url``);
* offline validation (https, no whitespace, no placeholder hosts such as
  ``is.gd`` / ``example.com``);
* optional live checks (HTTP status after redirects) — offline by default so
  tests stay deterministic.

Usage::

    from content_factory.integrations.partner_links import (
        load_partner_links, resolve_program_link, validate_link, check_link_live,
    )

    links = load_partner_links()
    url = resolve_program_link("aviasales", links, fallback="https://example.org/")
    assert validate_link(url) == []
    check_link_live(url)   # -> LinkCheck(ok=True, status=200, final_url=...)
"""
from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LINKS_FILE = ROOT / "config" / "affiliate_links.yaml"

#: Hosts that are placeholders / dead in practice: a pin must not point there.
PLACEHOLDER_HOSTS = frozenset(
    {
        "is.gd",
        "v.gd",
        "example.com",
        "example.org",
        "example.net",
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
    }
)

#: Hard limits for a pin destination URL.
MAX_URL_LENGTH = 500
USER_AGENT = "Mozilla/5.0 (compatible; content-factory-link-check/1.0)"


@dataclass(frozen=True)
class LinkCheck:
    """Result of a link validation/check."""

    url: str
    ok: bool
    reason: str = ""
    status: int = 0
    final_url: str = ""

    def as_dict(self) -> Dict[str, object]:
        return {
            "url": self.url,
            "ok": self.ok,
            "reason": self.reason,
            "status": self.status,
            "final_url": self.final_url,
        }


def host_of(url: str) -> str:
    """Lower-case hostname without scheme/port/path (``""`` when unparseable)."""
    value = str(url or "").strip()
    if "://" not in value:
        return ""
    rest = value.split("://", 1)[1]
    host = rest.split("/", 1)[0].split("@")[-1].split(":", 1)[0]
    return host.strip().lower().rstrip(".")


def validate_link(url: str, *, allow_http: bool = False) -> List[str]:
    """Offline validation. Returns a list of problems (empty = link is OK)."""
    problems: List[str] = []
    value = str(url or "").strip()
    if not value:
        return ["пустая ссылка"]
    if len(value) > MAX_URL_LENGTH:
        problems.append("ссылка длиннее %d символов" % MAX_URL_LENGTH)
    if any(char.isspace() for char in value):
        problems.append("ссылка содержит пробелы")
    schemes = ("http://", "https://") if allow_http else ("https://",)
    if not value.startswith(schemes):
        problems.append("ссылка должна начинаться с https://")
    host = host_of(value)
    if not host:
        problems.append("не удалось определить домен")
    elif host in PLACEHOLDER_HOSTS:
        problems.append("заглушка вместо рабочей ссылки: %s" % host)
    return problems


def load_partner_links(path: Optional[Path] = None) -> Dict[str, str]:
    """Read ``program → partner_url`` from ``config/affiliate_links.yaml``."""
    import yaml  # локальный импорт: модуль остаётся импортируемым без PyYAML

    config_path = Path(path) if path else DEFAULT_LINKS_FILE
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    programs = data.get("programs") or {}
    result: Dict[str, str] = {}
    for name, program in programs.items():
        if not isinstance(program, dict):
            continue
        url = str(program.get("partner_url") or program.get("url") or "").strip()
        if url:
            result[str(name)] = url
    return result


def resolve_program_link(
    program: str,
    links: Optional[Dict[str, str]] = None,
    fallback: str = "",
    *,
    allow_http: bool = False,
) -> str:
    """Partner URL for ``program``; ``fallback`` when unknown/invalid."""
    program = str(program or "").strip()
    resolved = (links or {}).get(program, "")
    if resolved and not validate_link(resolved, allow_http=allow_http):
        return resolved
    fallback = str(fallback or "").strip()
    if fallback and not validate_link(fallback, allow_http=allow_http):
        return fallback
    return ""


def check_link_live(url: str, timeout: float = 12.0) -> LinkCheck:
    """Live check: GET (redirects followed) and record the final status."""
    problems = validate_link(url)
    if problems:
        return LinkCheck(url=url, ok=False, reason="; ".join(problems))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - проверка своих ссылок
            status = int(getattr(response, "status", 0) or response.getcode() or 0)
            final_url = str(response.geturl() or url)
    except urllib.error.HTTPError as error:
        status = int(getattr(error, "code", 0) or 0)
        final_url = str(getattr(error, "url", "") or url)
        # 3xx без пригодного Location (или с заголовком, который urllib не
        # переварил) — ссылка жива, редирект существует: считаем активной.
        ok = 300 <= status < 400
        return LinkCheck(
            url=url,
            ok=ok,
            reason="" if ok else "HTTP %d" % status,
            status=status,
            final_url=final_url,
        )
    except (urllib.error.URLError, OSError, ValueError) as error:
        return LinkCheck(url=url, ok=False, reason="нет соединения: %s" % error)
    ok = 200 <= status < 400
    return LinkCheck(
        url=url,
        ok=ok,
        reason="" if ok else "HTTP %d" % status,
        status=status,
        final_url=final_url,
    )


def check_links_live(urls: Iterable[str], timeout: float = 12.0) -> List[LinkCheck]:
    """Check unique URLs sequentially; returns one result per unique URL."""
    seen = set()
    results: List[LinkCheck] = []
    for url in urls:
        value = str(url or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        results.append(check_link_live(value, timeout=timeout))
    return results
