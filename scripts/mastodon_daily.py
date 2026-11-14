#!/usr/bin/env python3
"""Ежедневный длинный обзор в Mastodon: thread из 3–5 постов по нашим темам.

    python scripts/mastodon_daily.py --dry-run          # показать thread
    python scripts/mastodon_daily.py --apply            # опубликовать
    python scripts/mastodon_daily.py --apply --slot 1   # второй пост за день

Темы чередуются по дате: AI → Crypto → Sports. В конце треда — акцент на
Telegram-канал. Ссылки вырезаются при MASTODON_NO_LINKS=1 (антиспам).
Дубли за день отсекаются по repository variable MASTODON_LAST_THREAD.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from content_factory.config import Settings, load_channels  # noqa: E402
from content_factory.nlp.llm import get_llm  # noqa: E402
from content_factory.pipeline import filter_articles  # noqa: E402
from content_factory.sources import get_adapter  # noqa: E402
from content_factory.utils import account_unavailable, normalize_space, strip_html  # noqa: E402

MAX_PART = 480
MAX_PARTS = 4
STATE_VAR = "MASTODON_LAST_THREAD"

# Mastodon-совместимые сети: (имя, env базы, env токена)
MASTODON_COMPAT_NETWORKS = [
    ("mastodon", "MASTODON_BASE_URL", "MASTODON_TOKEN"),
    ("pleroma", "PLEROMA_BASE_URL", "PLEROMA_TOKEN"),
    ("akkoma", "AKKOMA_BASE_URL", "AKKOMA_TOKEN"),
    ("gotosocial", "GOTOSOCIAL_BASE_URL", "GOTOSOCIAL_TOKEN"),
    ("friendica", "FRIENDICA_BASE_URL", "FRIENDICA_TOKEN"),
]

TOPICS: List[Dict[str, str]] = [
    {"channel_id": "ai-news", "title": "AI", "emoji": "🤖",
     "hashtags": "#AI #OpenAI #MachineLearning"},
    {"channel_id": "crypto-news", "title": "Crypto", "emoji": "🪙",
     "hashtags": "#Crypto #Bitcoin #Blockchain"},
    {"channel_id": "sport-news", "title": "Sports", "emoji": "🏆",
     "hashtags": "#NFL #NBA #Sports"},
]

SYSTEM = (
    "You are a professional journalist writing a long-form review for Mastodon. "
    "Write in English. Structure the review as {parts} separate posts, each up to "
    "{limit} characters. No numbering, no labels like 'Key points' or 'Why it matters'. "
    "Each post should read naturally on its own, with one relevant emoji at the start. "
    "The final post must explicitly invite readers to follow our Telegram channel: "
    "{handle} (write it as a plain mention, no URL). End the final post with hashtags: "
    "{hashtags}. Never include URLs. Output only the posts, separated by a line "
    "containing exactly ---"
)


def topic_for(day: date, slot: int = 0) -> Dict[str, str]:
    return TOPICS[(day.toordinal() + int(slot)) % len(TOPICS)]


def channel_map(settings: Settings) -> Dict[str, Any]:
    channels: Dict[str, Any] = {}
    for path in ("config/channels.en.yaml", "config/channels.es.yaml"):
        try:
            for channel in load_channels(settings, path=str(ROOT / path)):
                channels[channel.id] = channel
        except Exception:  # noqa: BLE001
            continue
    return channels


def collect_articles(channel: Any, settings: Settings, limit: int = 12) -> List[Any]:
    collected: List[Any] = []
    for source in channel.sources:
        if not source.enabled:
            continue
        try:
            items = get_adapter(source.type).fetch(source, settings) or []
            collected.extend(items)
        except Exception:  # noqa: BLE001
            continue
    try:
        fresh = filter_articles(channel, collected, settings)
    except Exception:  # noqa: BLE001
        fresh = collected
    seen: set = set()
    unique: List[Any] = []
    for article in fresh:
        key = (getattr(article, "title", "") or "").lower()[:80]
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(article)
    unique.sort(key=lambda a: getattr(a, "published_at", None) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return unique[:limit]


KNOWN_HANDLES = {
    "ai-news": "@AINEWS0007",
    "crypto-news": "@HOOPY0007",
    "sport-news": "@SPORTNews0007",
    "tech-ai-es": "@WORLDNews0007",
    "crypto-es": "@TechnologiesNews01",
    "futbol-es": "@SPORTSAnalytics007",
}


def _handle(channel: Any) -> str:
    """@канал для CTA: public_url → id-мэппинг → telegram_chat_id."""
    public = str(getattr(channel, "public_url", "") or "")
    match = re.search(r"t\.me/([A-Za-z0-9_]+)", public)
    if match:
        return "@" + match.group(1)
    known = KNOWN_HANDLES.get(str(getattr(channel, "id", "")))
    if known:
        return known
    chat = str(getattr(channel, "telegram_chat_id", "") or "")
    if chat.startswith("@"):
        return chat
    return ""


def _article_sentence(article: Any) -> str:
    title = normalize_space(getattr(article, "title", "") or "")
    summary = normalize_space(getattr(article, "summary", "") or "")
    summary = re.sub(r"\s*" + re.escape(title[:40]) + r".*", "", summary, count=1) if title else summary
    body = summary or normalize_space(getattr(article, "text", "") or "")[:220]
    body = body[:260]
    text = f"{title}. {body}".strip() if title else body
    text = re.sub(r"[.?!]\s*[.?!]+", ".", text)
    return clean_part(text)


def _no_links() -> bool:
    return str(os.environ.get("MASTODON_NO_LINKS", "") or "").strip().lower() in {
        "1", "true", "yes", "on"}


def split_llm_text(raw: str) -> List[str]:
    """Нарезает LLM-текст на части: --- / абзацы / предложения ≤ MAX_PART."""
    raw = (raw or "").strip()
    if not raw:
        return []
    by_sep = [part.strip() for part in re.split(r"(?m)^\s*-{3,}\s*$", raw) if part.strip()]
    if len(by_sep) >= 2:
        return by_sep
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", raw) if part.strip()]
    if len(paragraphs) >= 2:
        chunks: List[str] = []
        current = ""
        for paragraph in paragraphs:
            candidate = (current + "\n\n" + paragraph).strip() if current else paragraph
            if len(candidate) > MAX_PART and current:
                chunks.append(current)
                current = paragraph
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", raw) if sentence.strip()]
    chunks = []
    current = ""
    for sentence in sentences:
        candidate = (current + " " + sentence).strip() if current else sentence
        if len(candidate) > MAX_PART and current:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def clean_part(text: str, strip_links: Optional[bool] = None) -> str:
    text = normalize_space(strip_html(text or ""))
    if strip_links is None:
        strip_links = _no_links()
    if strip_links:
        text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    if len(text) <= MAX_PART:
        return text
    cut = text[:MAX_PART]
    for sep in (". ", "! ", "? ", "; "):
        pos = cut.rfind(sep)
        if pos > 120:
            return cut[: pos + 1].strip()
    return cut[: MAX_PART - 1].rstrip() + "…"


def build_fallback(channel: Any, topic: Dict[str, str], articles: List[Any]) -> List[str]:
    handle = _handle(channel)
    parts: List[str] = []
    if articles:
        first = articles[0]
        intro_lead = _article_sentence(first)
        parts.append(clean_part(f"{topic['emoji']} {topic['title']} review: {intro_lead}"))
        for article in articles[1:4]:
            parts.append(_article_sentence(article))
    else:
        parts.append(
            f"{topic['emoji']} {topic['title']} review: markets, models and people "
            f"worth watching. A calm look at what usually gets lost in the headlines."
        )
    tail = f"The full picture every day — in our Telegram channel {handle}." if handle else ""
    parts.append(clean_part(f"{tail} {topic['hashtags']}".strip()))
    return parts


def build_with_llm(channel: Any, topic: Dict[str, str], articles: List[Any],
                   settings: Settings) -> List[str]:
    llm = get_llm(settings)
    if not getattr(llm, "available", False):
        return []
    context_lines = []
    for article in articles[:5]:
        summary = normalize_space(getattr(article, "summary", "") or "")
        context_lines.append(f"- {getattr(article, 'title', '')}: {summary[:300]}")
    prompt = (
        f"Topic: {topic['title']}.\n"
        f"Today's material:\n" + "\n".join(context_lines) + "\n\n"
        f"Write the review as {MAX_PARTS - 1} posts plus a final invitation post "
        f"(total {MAX_PARTS}), each <= {MAX_PART} characters, separated by '---'. "
        f"Never use numbering or section labels."
    )
    system = SYSTEM.format(parts=MAX_PARTS, limit=MAX_PART,
                           handle=_handle(channel) or "@our_channel",
                           hashtags=topic["hashtags"])
    raw = llm.generate(prompt, system=system, max_tokens=1200, temperature=0.4)
    chunks = [clean_part(part) for part in split_llm_text(raw)]
    chunks = [chunk for chunk in chunks if len(chunk) >= 80][:MAX_PARTS]
    if len(chunks) < 2:
        return []
    if "#" not in chunks[-1]:
        chunks[-1] = clean_part(chunks[-1] + " " + topic["hashtags"])
    if _handle(channel) and _handle(channel) not in " ".join(chunks):
        chunks[-1] = clean_part(f"{chunks[-1]} Telegram: {_handle(channel)}")
    return chunks


def prepare_thread(channel: Any, topic: Dict[str, str], articles: List[Any],
                   settings: Settings) -> List[str]:
    parts = build_with_llm(channel, topic, articles, settings)
    if not parts:
        parts = build_fallback(channel, topic, articles)
    return [part for part in parts if part][:MAX_PARTS]


def _api_base() -> str:
    return (os.environ.get("MASTODON_BASE_URL", "") or "https://mastodon.social").rstrip("/")


def _api_token() -> str:
    return os.environ.get("MASTODON_TOKEN", "").strip()


def _env(name: str) -> str:
    return (os.environ.get(name, "") or "").strip()


def configured_networks() -> List[Dict[str, str]]:
    """Все настроенные сети: Mastodon-совместимые + Misskey."""
    result: List[Dict[str, str]] = []
    for name, base_env, token_env in MASTODON_COMPAT_NETWORKS:
        base, token = _env(base_env).rstrip("/"), _env(token_env)
        if base and token:
            result.append({"name": name, "kind": "mastodon", "base": base, "token": token})
    host, token = _env("MISSKEY_HOST").rstrip("/"), _env("MISSKEY_TOKEN")
    if host and token:
        host = re.sub(r"^https?://", "", host)
        result.append({"name": "misskey", "kind": "misskey", "base": host, "token": token})
    return result


def _http_json(url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None,
               form: bool = False, timeout: int = 45) -> Dict[str, Any]:
    if form:
        body = urllib.parse.urlencode(payload).encode("utf-8")
        content_type = "application/x-www-form-urlencoded"
    else:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        content_type = "application/json"
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={**(headers or {}), "Content-Type": content_type,
                 "Accept": "application/json", "User-Agent": "factory-mastodon-daily/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
        return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"HTTP {exc.code} {url.split('/')[2]}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"сеть недоступна {url.split('/')[2]}: {exc}") from exc


def post_status(text: str, reply_to: str = "", base: str = "", token: str = "") -> Dict[str, Any]:
    """Пост/ответ в Mastodon-совместимую сеть (Mastodon/Pleroma/Akkoma/GTS/Friendica)."""
    base = (base or _api_base()).rstrip("/")
    token = token or _api_token()
    if not token:
        raise RuntimeError("MASTODON_TOKEN не задан")
    payload: Dict[str, Any] = {"status": text, "visibility": "public", "language": "en"}
    if reply_to:
        payload["in_reply_to_id"] = reply_to
    return _http_json(f"{base}/api/v1/statuses", payload,
                      headers={"Authorization": f"Bearer {token}"}, form=True)


def post_misskey(text: str, reply_to: str = "", host: str = "", token: str = "") -> Dict[str, Any]:
    """Пост/ответ в Misskey (replyId для продолжения thread)."""
    host = re.sub(r"^https?://", "", (host or _env("MISSKEY_HOST")).rstrip("/"))
    token = token or _env("MISSKEY_TOKEN")
    if not host or not token:
        raise RuntimeError("MISSKEY_HOST/MISSKEY_TOKEN не заданы")
    payload: Dict[str, Any] = {"i": token, "text": text, "visibility": "public"}
    if reply_to:
        payload["replyId"] = reply_to
    data = _http_json(f"https://{host}/api/notes/create", payload)
    note = data.get("createdNote") or {}
    return {"id": note.get("id"), "url": note.get("url") or f"https://{host}/notes/{note.get('id')}"}


def publish_thread(parts: List[str], apply: bool, network: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """Публикует thread в одну сеть (по умолчанию — Mastodon из env)."""
    results: List[Dict[str, Any]] = []
    reply_to = ""
    for text in parts:
        if not apply:
            results.append({"dry_run": True, "chars": len(text), "text": text})
            continue
        if network and network.get("kind") == "misskey":
            data = post_misskey(text, reply_to, network["base"], network["token"])
        elif network:
            data = post_status(text, reply_to, network["base"], network["token"])
        else:
            data = post_status(text, reply_to)
        reply_to = str(data.get("id") or "")
        results.append({"id": data.get("id"), "url": data.get("url"), "chars": len(text)})
    return results


def publish_all_networks(parts: List[str], apply: bool,
                         only: str = "") -> Dict[str, Any]:
    """Публикует thread во все настроенные сети (или только в `only`)."""
    networks = configured_networks()
    if only:
        networks = [n for n in networks if n["name"] == only]
    if not networks:
        # без кредов — обычный dry-run в Mastodon-формате
        return {"networks": {}, "dry_run": not apply,
                "results": publish_thread(parts, False)}
    out: Dict[str, Any] = {"networks": {}, "dry_run": not apply}
    for network in networks:
        try:
            result = publish_thread(parts, apply, network)
            out["networks"][network["name"]] = {
                "ok": True,
                "url": next((r.get("url") for r in result if r.get("url")), ""),
                "results": result,
            }
        except Exception as exc:  # noqa: BLE001 - одна сеть не ломает остальные
            out["networks"][network["name"]] = {"ok": False, "error": str(exc)}
    return out


# --- state (repo variable) ---------------------------------------------------
def _gh_token() -> str:
    return (os.environ.get("ALERT_GITHUB_TOKEN", "") or os.environ.get("GITHUB_TOKEN", "")).strip()


def _state_get() -> Dict[str, Any]:
    token = _gh_token()
    repo = os.environ.get("STATE_SYNC_REPO", "valdislavn-spec/content-factory")
    if not token:
        return {}
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/actions/variables/{STATE_VAR}",
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "cf-daily"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return {"value": json.loads(response.read().decode("utf-8")).get("value", "")}
    except Exception:  # noqa: BLE001
        return {}


def _state_set(value: str) -> None:
    token = _gh_token()
    repo = os.environ.get("STATE_SYNC_REPO", "valdislavn-spec/content-factory")
    if not token:
        return
    headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "cf-daily",
               "Content-Type": "application/json"}
    body = json.dumps({"name": STATE_VAR, "value": value}).encode()
    for method, url in (
        ("POST", f"https://api.github.com/repos/{repo}/actions/variables"),
        ("PATCH", f"https://api.github.com/repos/{repo}/actions/variables/{STATE_VAR}"),
    ):
        request = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                if response.status in (201, 204):
                    return
        except Exception:  # noqa: BLE001
            continue


def _already_done(day: date, slot: int) -> bool:
    marker = f"{day.isoformat()}:{slot}"
    try:
        return str(_state_get().get("value", "")).find(marker) >= 0
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="только показать (по умолчанию)")
    parser.add_argument("--channel", default="", help="ai-news|crypto-news|sport-news")
    parser.add_argument("--slot", type=int, default=0, help="0 = первый пост дня, 1 = второй")
    parser.add_argument("--date", default="", help="YYYY-MM-DD (по умолчанию сегодня UTC)")
    parser.add_argument("--force", action="store_true", help="игнорировать проверку дубля")
    parser.add_argument("--network", default="", help="только одна сеть: mastodon|pleroma|akkoma|gotosocial|friendica|misskey")
    args = parser.parse_args()
    settings = Settings.load()
    day = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()
    if not args.force and _already_done(day, args.slot):
        print(f"{day} слот {args.slot}: уже опубликовано — выходим (--force чтобы повторить)")
        return 0
    topic = topic_for(day, args.slot)
    if args.channel:
        topic = next((t for t in TOPICS if t["channel_id"] == args.channel), topic)
    channels = channel_map(settings)
    channel = channels.get(topic["channel_id"])
    if channel is None:
        print(f"Канал {topic['channel_id']} не найден")
        return 2
    apply = args.apply and not args.dry_run
    articles = collect_articles(channel, settings)
    print(f"Тема: {topic['title']} | статей: {len(articles)}")
    parts = prepare_thread(channel, topic, articles, settings)
    print(f"Постов в thread: {len(parts)}")
    for index, part in enumerate(parts, start=1):
        print(f"--- part {index} ({len(part)} симв.) ---\n{part}")
    result = publish_all_networks(parts, apply, args.network)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    networks_ok = {
        name: data for name, data in (result.get("networks") or {}).items() if data.get("ok")
    }
    networks_failed = {
        name: data for name, data in (result.get("networks") or {}).items() if not data.get("ok")
    }
    if apply and not networks_ok:
        joined = json.dumps(networks_failed, ensure_ascii=False)
        if account_unavailable(joined):
            # @Yeti01 заблокирован (страйк 319361, апелляция в процессе) — известное
            # ожидаемое состояние, не считаем падением пайплайна. Покрывает все
            # fediverse-сети: 401/403, disabled, suspended, invalid access token.
            print("SKIP: аккаунт Mastodon недоступен — публикация пропущена: " + joined[:300])
            return 0
        print(
            "ОШИБКА: ни одна сеть не приняла thread: "
            + json.dumps(networks_failed, ensure_ascii=False)[:500]
        )
        return 1
    if apply and networks_failed:
        print("ПРЕДУПРЕЖДЕНИЕ: часть сетей не приняла thread: " + ", ".join(sorted(networks_failed)))
    if apply and networks_ok:
        _state_set(f"{day.isoformat()}:{args.slot}")
        for name, data in networks_ok.items():
            print(f"Опубликовано [{name}]: {data.get('url')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
