"""OSS Radar: свежие релизы open-source для рубрики «что вышло за сутки».

Источники:
    * **GitHub Releases API** — бесплатно, без ключа (60 запросов/час; с токеном — 5000/час);
    * **libraries.io API** — опционально, бесплатный ключ через GitHub OAuth (60 запросов/мин),
      нужен только для «кросс-экосистемного» фида PyPI/npm/crates.

Что делает:
    1. забирает релизы по списку репозиториев из ``config/oss_radar.yaml``;
    2. отбирает опубликованные за последние N часов (черновики/prerelease — по флагу);
    3. рендерит готовый Telegram-пост (EN/ES): заголовок, ссылки на релизы, хэштеги;
    4. кэширует ответы API в ``data/cache/oss_radar/`` (TTL 1 ч), чтобы не жечь лимит.

Автопубликации нет: скрипт только готовит пост — редактор/пайплайн решает, публиковать ли.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .models import utcnow
from .utils import env

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
LIBRARIES_IO_API = "https://libraries.io/api"
DEFAULT_TIMEOUT = 20.0
DEFAULT_CACHE_TTL = 3600
MAX_RELEASES_PER_REPO = 20
USER_AGENT = "content-factory-oss-radar/1.0 (+https://github.com/librariesio/libraries.io)"


class OSSRadarError(RuntimeError):
    """Ошибка OSS Radar (конфигурация, API, лимиты)."""


class RateLimitError(OSSRadarError):
    """GitHub/libraries.io вернул 403/429 (лимит запросов)."""


# ---------------------------------------------------------------------------
# Модели
# ---------------------------------------------------------------------------


@dataclass
class Release:
    repo: str               # owner/repo или PackageManager:name
    tag: str                # тег/версия
    url: str                # ссылка на релиз/страницу пакета
    published_at: datetime  # awareness UTC
    body: str = ""          # release notes / описание пакета
    name: str = ""
    prerelease: bool = False
    source: str = "github"
    license: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repo": self.repo,
            "tag": self.tag,
            "url": self.url,
            "published_at": self.published_at.astimezone(timezone.utc).isoformat(),
            "name": self.name,
            "prerelease": self.prerelease,
            "source": self.source,
            "license": self.license,
        }


def parse_iso(value: Any) -> Optional[datetime]:
    """Парсит ISO-дату GitHub/libraries.io; None, если пусто/некорректно."""
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    # libraries.io отдаёт "2026-10-09 12:56:54 UTC"
    if normalized.endswith(" UTC"):
        normalized = normalized[:-4].strip() + "+00:00"
    normalized = normalized.replace(" ", "T", 1) if " " in normalized and "T" not in normalized else normalized
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(normalized, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# HTTP и кэш
# ---------------------------------------------------------------------------


def _http_json(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Tuple[Any, Dict[str, str], int]:
    """GET JSON; 403/429 → RateLimitError, 404 → OSSRadarError, сеть → OSSRadarError."""
    request_headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if headers:
        request_headers.update({k: v for k, v in headers.items() if v})
    request = urllib.request.Request(url, headers=request_headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=max(5.0, float(timeout))) as response:
            raw = response.read()
            status = int(getattr(response, "status", 0) or 0)
            response_headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:  # pragma: no cover - нечитаемое тело
            detail = ""
        if exc.code in (403, 429):
            reset = ""
            try:
                reset = str(exc.headers.get("X-RateLimit-Reset") or "")
            except Exception:  # pragma: no cover
                reset = ""
            raise RateLimitError(
                f"лимит запросов (HTTP {exc.code})"
                + (f", сброс в {reset}" if reset else "")
                + f": {detail}"
            ) from exc
        raise OSSRadarError(f"HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise OSSRadarError(f"сеть недоступна: {exc}") from exc
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError as exc:
        raise OSSRadarError("API вернул не JSON") from exc
    return data, response_headers, status


class ResponseCache:
    """Простой файловый кэш JSON-ответов с TTL."""

    def __init__(self, directory: Path, ttl: int = DEFAULT_CACHE_TTL) -> None:
        self.directory = Path(directory)
        self.ttl = max(0, int(ttl))
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
        return self.directory / f"{digest}.json"

    def get(self, key: str, allow_stale: bool = False) -> Optional[Any]:
        path = self._path(key)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        fetched_at = float(payload.get("fetched_at") or 0)
        if not allow_stale and self.ttl and time.time() - fetched_at > self.ttl:
            return None
        return payload.get("data")

    def set(self, key: str, data: Any) -> None:
        path = self._path(key)
        payload = {"fetched_at": time.time(), "key": key, "data": data}
        try:
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:  # кэш не должен ронять сбор
            logger.warning("OSS Radar: не удалось записать кэш %s: %s", path, exc)


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------


class GitHubClient:
    """Клиент GitHub Releases API (токен не обязателен)."""

    def __init__(
        self,
        token: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        cache_ttl: int = DEFAULT_CACHE_TTL,
        timeout: float = DEFAULT_TIMEOUT,
        api_base: str = GITHUB_API,
    ) -> None:
        self.token = str(token or env("GITHUB_TOKEN", "") or env("GH_TOKEN", "") or "").strip()
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout
        self.cache = ResponseCache(Path(cache_dir), cache_ttl) if cache_dir else None
        self.last_headers: Dict[str, str] = {}

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def releases(self, repo: str, per_page: int = MAX_RELEASES_PER_REPO, refresh: bool = False) -> List[Dict[str, Any]]:
        url = f"{self.api_base}/repos/{repo}/releases?per_page={max(1, min(int(per_page), 100))}"
        cache_key = f"github:{repo}:{per_page}"
        if self.cache and not refresh:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return list(cached)
        try:
            data, headers, _status = _http_json(url, headers=self._headers(), timeout=self.timeout)
        except RateLimitError:
            if self.cache:
                stale = self.cache.get(cache_key, allow_stale=True)
                if stale is not None:
                    logger.warning("OSS Radar: лимит GitHub, отдаю устаревший кэш для %s", repo)
                    return list(stale)
            raise
        except OSSRadarError as exc:
            logger.warning("OSS Radar: %s — %s", repo, exc)
            return []
        self.last_headers = headers
        items = data if isinstance(data, list) else []
        if self.cache:
            self.cache.set(cache_key, items)
        return items

    @property
    def remaining(self) -> Optional[int]:
        """Остаток GitHub-лимита из последнего ответа (None — неизвестно)."""
        value = self.last_headers.get("x-ratelimit-remaining")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None


def github_items_to_releases(repo: str, items: Iterable[Dict[str, Any]]) -> List[Release]:
    """Преобразует JSON GitHub Releases в Release для одного репозитория."""
    collected: List[Release] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        published = parse_iso(item.get("published_at") or item.get("created_at"))
        if published is None:
            continue
        collected.append(
            Release(
                repo=str(repo),
                name=str(item.get("name") or ""),
                tag=str(item.get("tag_name") or item.get("name") or ""),
                url=str(item.get("html_url") or f"https://github.com/{repo}/releases"),
                published_at=published,
                body=str(item.get("body") or ""),
                prerelease=bool(item.get("prerelease") or item.get("draft")),
                source="github",
            )
        )
    return collected


def github_releases(
    repos: Sequence[str], client: GitHubClient, per_page: int = MAX_RELEASES_PER_REPO
) -> List[Release]:
    """Собирает Release из списка owner/repo (по одному запросу на репозиторий)."""
    collected: List[Release] = []
    for repo in repos:
        collected.extend(github_items_to_releases(repo, client.releases(repo, per_page=per_page)))
    return collected


# ---------------------------------------------------------------------------
# libraries.io (опционально; нужен бесплатный ключ)
# ---------------------------------------------------------------------------


class LibrariesIOClient:
    """Клиент libraries.io: поиск пакетов, отсортированный по дате релиза."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        cache_ttl: int = DEFAULT_CACHE_TTL,
        timeout: float = DEFAULT_TIMEOUT,
        api_base: str = LIBRARIES_IO_API,
    ) -> None:
        self.api_key = str(api_key or env("LIBRARIES_IO_API_KEY", "") or "").strip()
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout
        self.cache = ResponseCache(Path(cache_dir), cache_ttl) if cache_dir else None

    def search(
        self,
        query: str,
        platforms: Sequence[str] = ("PyPI", "npm"),
        per_page: int = 50,
        page: int = 1,
        refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        if not self.api_key:
            raise OSSRadarError(
                "LIBRARIES_IO_API_KEY не задан: нужен бесплатный ключ libraries.io "
                "(вход через GitHub → Account → API key)"
            )
        params = {
            "q": query,
            "sort": "latest_release_published_at",
            "per_page": str(max(1, min(int(per_page), 100))),
            "page": str(max(1, int(page))),
            "api_key": self.api_key,
        }
        if platforms:
            params["platforms"] = ",".join(platforms)
        url = f"{self.api_base}/search?" + urllib.parse.urlencode(params)
        cache_key = f"libraries_io:{query}:{','.join(platforms)}:{per_page}:{page}"
        if self.cache and not refresh:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return list(cached)
        try:
            data, _headers, _status = _http_json(url, timeout=self.timeout)
        except RateLimitError:
            if self.cache:
                stale = self.cache.get(cache_key, allow_stale=True)
                if stale is not None:
                    logger.warning("OSS Radar: лимит libraries.io, отдаю устаревший кэш «%s»", query)
                    return list(stale)
            raise
        items = data if isinstance(data, list) else []
        if self.cache:
            self.cache.set(cache_key, items)
        return items


def libraries_io_releases(
    items: Iterable[Dict[str, Any]], allowed_licenses: Sequence[str] = ()
) -> List[Release]:
    """Преобразует ответ libraries.io search в Release, фильтруя лицензии."""
    allowed = {str(value).strip().lower() for value in allowed_licenses if str(value).strip()}
    releases: List[Release] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        published = parse_iso(item.get("latest_release_published_at"))
        if published is None:
            continue
        license_value = ""
        licenses = item.get("licenses")
        if isinstance(licenses, list):
            license_value = ", ".join(str(value) for value in licenses)
        elif licenses:
            license_value = str(licenses)
        if allowed and license_value:
            normalized = {part.strip().lower() for part in re.split(r"[,/]", license_value) if part.strip()}
            if not (normalized & allowed):
                continue
        platform = str(item.get("platform") or "")
        name = str(item.get("name") or "")
        repo = f"{platform}:{name}" if platform else name
        releases.append(
            Release(
                repo=repo,
                name=str(item.get("description") or name),
                tag=str(item.get("latest_release_number") or ""),
                url=str(item.get("package_manager_url") or item.get("repository_url") or ""),
                published_at=published,
                body=str(item.get("description") or ""),
                source="libraries_io",
                license=license_value,
            )
        )
    return releases


# ---------------------------------------------------------------------------
# Отбор и рендер
# ---------------------------------------------------------------------------


def select_recent(
    releases: Iterable[Release],
    hours: float = 24,
    max_items: int = 20,
    include_prereleases: bool = False,
    now: Optional[datetime] = None,
    per_repo: int = 1,
) -> List[Release]:
    """Оставляет релизы за последние ``hours`` часов, сортирует и ограничивает.

    ``per_repo`` — сколько релизов одного репозитория максимум в дайджесте
    (1 = только самый свежий; 0 — без ограничения).
    """
    current = (now or utcnow()).astimezone(timezone.utc)
    cutoff = current - timedelta(hours=max(0.0, float(hours)))
    selected: List[Release] = []
    seen = set()
    for release in releases:
        published = release.published_at
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        if published < cutoff:
            continue
        if release.prerelease and not include_prereleases:
            continue
        key = (release.source, release.repo, release.tag)
        if key in seen:
            continue
        seen.add(key)
        selected.append(release)
    selected.sort(key=lambda item: item.published_at, reverse=True)
    if per_repo and int(per_repo) > 0:
        diversified: List[Release] = []
        counts: Dict[str, int] = {}
        for release in selected:
            key = f"{release.source}:{release.repo}"
            if counts.get(key, 0) >= int(per_repo):
                continue
            counts[key] = counts.get(key, 0) + 1
            diversified.append(release)
        selected = diversified
    return selected[: max(1, int(max_items))]


def _clean_body(text: str, limit: int = 140) -> str:
    """Чистит release notes/описание до одной короткой строки."""
    raw = str(text or "")
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", raw)
    raw = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", raw)
    raw = raw.replace("**", "").replace("__", "").replace("`", "")
    lines = [re.sub(r"\s+", " ", line).strip() for line in raw.splitlines()]
    meaningful = [
        line
        for line in lines
        if line
        and not line.lower().startswith(("full changelog", "what's changed", "changelog", "##"))
        and not line.startswith("#")
    ]
    if not meaningful:
        return ""
    text_out = meaningful[0]
    text_out = re.sub(r"\s+", " ", text_out)
    if len(text_out) > limit:
        text_out = text_out[: max(1, limit - 1)].rstrip() + "…"
    return text_out


_LABELS = {
    "en": {
        "title": "🛠 Open-source releases — last {hours}h",
        "empty": "🛠 OSS Radar: no new releases in the last {hours}h",
        "hashtags": "#opensource #ai #github",
        "intro": "New releases worth a look:",
    },
    "es": {
        "title": "🛠 Lanzamientos open source — últimas {hours} h",
        "empty": "🛠 OSS Radar: sin lanzamientos nuevos en las últimas {hours} h",
        "hashtags": "#opensource #IA #github",
        "intro": "Nuevos lanzamientos que vale la pena mirar:",
    },
}


def render_digest(
    releases: Sequence[Release],
    channel_id: str,
    hours: float = 24,
    language: str = "en",
    max_items: int = 10,
) -> Dict[str, str]:
    """Готовый Telegram-пост (HTML + plain) для канала."""
    lang = str(language or "en").lower()
    labels = _LABELS.get(lang, _LABELS["en"])
    items = list(releases)[: max(1, int(max_items))]
    title = labels["title"].format(hours=int(hours)) if int(hours) != 1 else labels["title"].format(hours=1)
    if not items:
        html = f"<b>{title}</b>\n\n{labels['empty'].format(hours=int(hours))}"
        return {"html": html, "plain": title, "items": 0, "channel": channel_id, "language": lang}
    html_lines = [f"<b>{title}</b>", "", labels["intro"], ""]
    plain_lines = [title, "", labels["intro"], ""]
    for release in items:
        label = _html_escape(release.repo)
        tag = _html_escape(release.tag or "release")
        url = _html_escape(release.url)
        pre = " <i>(pre-release)</i>" if release.prerelease else ""
        html_lines.append(f'• <a href="{url}">{label}</a> — <code>{tag}</code>{pre}')
        snippet = _clean_body(release.body)
        if snippet:
            html_lines.append(f"   {_html_escape(snippet)}")
        plain_tag = f"{release.tag} (pre-release)" if release.prerelease else release.tag
        plain_lines.append(f"• {release.repo} — {plain_tag}: {release.url}")
    html_lines += ["", labels["hashtags"]]
    plain_lines += ["", labels["hashtags"]]
    return {
        "html": "\n".join(html_lines),
        "plain": "\n".join(plain_lines),
        "items": len(items),
        "channel": channel_id,
        "language": lang,
    }


def _html_escape(value: Any) -> str:
    import html as html_module

    return html_module.escape(str(value or ""), quote=True)


# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------


def load_config(path: Path) -> Dict[str, Any]:
    """Читает YAML-конфиг OSS Radar и проверяет структуру."""
    import yaml

    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise OSSRadarError(f"не удалось прочитать конфиг {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise OSSRadarError(f"конфиг {path}: ожидался объект")
    channels = raw.get("channels")
    if not isinstance(channels, dict) or not channels:
        raise OSSRadarError(f"конфиг {path}: нет секции channels")
    for channel_id, channel in channels.items():
        if not isinstance(channel, dict):
            raise OSSRadarError(f"канал {channel_id}: ожидался объект")
        repos = channel.get("repos") or []
        if not isinstance(repos, list):
            raise OSSRadarError(f"канал {channel_id}: repos должен быть списком")
    return raw


def channel_config(config: Dict[str, Any], channel_id: str) -> Dict[str, Any]:
    channels = config.get("channels") or {}
    if channel_id not in channels:
        raise OSSRadarError(
            f"канал {channel_id!r} не найден в конфиге; доступны: {', '.join(sorted(channels))}"
        )
    channel = dict(channels[channel_id] or {})
    channel.setdefault("language", "en")
    channel.setdefault("repos", [])
    channel.setdefault("queries", [])
    channel.setdefault("platforms", ["PyPI", "npm"])
    channel.setdefault("allowed_licenses", [])
    channel.setdefault("max_items", 10)
    return channel
