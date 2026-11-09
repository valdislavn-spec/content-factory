#!/usr/bin/env python3
"""Queue the daily pin in Buffer, adapted per connected network.

Picks one pin per day (rotation by day-of-year), builds network-specific text
(Bluesky / X / Facebook) with a hub link + UTM, then creates one post per
channel with ``mode: addToQueue`` (Buffer queue) or ``customScheduled``.

Env: BUFFER_API_KEY. Dry-run by default; use --live to create posts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import re
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.integrations.buffer import BufferClient, BufferError  # noqa: E402
from content_factory.integrations.shortlink import shorten_url  # noqa: E402


def hub_link(base: str, utm: dict) -> str:
    query = urllib.parse.urlencode({k: v for k, v in (utm or {}).items() if v})
    return base + ("?" + query if query else "")


def clip(text: str, limit: int, keep_lines: bool = False) -> str:
    """Обрезает текст до limit. keep_lines=True сохраняет переносы строк."""
    if keep_lines:
        lines = [" ".join(line.split()) for line in str(text or "").splitlines()]
        text = "\n".join(line for line in lines if line)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
    else:
        text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rsplit(" ", 1)[0] + "…"


DEFAULT_STYLE = {
    "emoji": "",
    "hashtags": [],
    "cta": "Read more:",
    "question": "",
}


def _style(config: dict, niche: str, day_index: int = 0) -> dict:
    style = dict(DEFAULT_STYLE)
    styles = (config or {}).get("niches") or {}
    if niche and isinstance(styles.get(niche), dict):
        style.update(styles[niche])
    variants = [str(v) for v in (style.get("cta_variants") or []) if str(v).strip()]
    if variants:
        style["cta"] = variants[day_index % len(variants)]
    return style


def _hook(title: str, limit: int) -> str:
    hook = " ".join(str(title or "").strip().split()).rstrip(".")
    return clip(hook, limit)


def _first_sentence(description: str, limit: int) -> str:
    """Первое предложение описания — короткий и чистый benefit."""
    text = " ".join(str(description or "").split())
    sentence = re.split(r"(?<=[.!?])\s", text)[0] if text else ""
    sentence = sentence.rstrip(".")
    if len(sentence) > limit:
        sentence = clip(sentence, limit)
    return sentence


def _bullets(description: str, limit: int = 230) -> str:
    """2–3 пункта пользы из описания (по ; : •), каждый строкой «• ...»."""
    text = " ".join(str(description or "").split()).rstrip(".")
    parts = [part.strip(" -•") for part in re.split(r"[;•]", text) if part.strip()]
    if len(parts) == 1 and ":" in text:
        head, tail = text.split(":", 1)
        parts = [head.strip(), tail.strip()]
    picked, used = [], 0
    for part in parts[:3]:
        if used + len(part) > limit:
            break
        picked.append(part)
        used += len(part) + 2
    if len(picked) <= 1:
        return _first_sentence(description, limit)
    return "\n".join("• " + part for part in picked)


def _tags(style: dict, maximum: int) -> str:
    tags = [str(tag) for tag in (style.get("hashtags") or []) if str(tag).strip()]
    return " ".join(tags[:max(0, maximum)])


def _short(url: str, enabled: bool) -> str:
    """Короткая ссылка (TinyURL) — «одно слово» вместо длинного URL."""
    if not enabled or not url:
        return url
    return shorten_url(url)


_TP_PROGRAMS_CACHE: list = []


def tp_programs() -> list:
    """Все подключённые программы Travelpayouts (config/affiliate_links.yaml)."""
    if not _TP_PROGRAMS_CACHE:
        path = ROOT / "config" / "affiliate_links.yaml"
        try:
            import yaml as _yaml

            data = _yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            programs = data.get("programs") or {}
            _TP_PROGRAMS_CACHE.extend(
                str(item.get("partner_url") or "").strip()
                for item in programs.values()
                if isinstance(item, dict) and item.get("partner_url")
            )
        except Exception:  # noqa: BLE001
            pass
    return _TP_PROGRAMS_CACHE


_PARTNER_CACHE: dict = {}


def partner_url(slug: str) -> str:
    """Партнёрская ссылка Travelpayouts для пина (config/travelpayouts.yaml)."""
    if not _PARTNER_CACHE:
        try:
            import yaml as _yaml

            path = ROOT / "config" / "travelpayouts.yaml"
            data = _yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            _PARTNER_CACHE.update(data.get("pins") or {})
        except Exception:  # noqa: BLE001 - без конфига работаем как раньше
            _PARTNER_CACHE["__missing__"] = True
    entry = _PARTNER_CACHE.get(str(slug or ""))
    if isinstance(entry, dict):
        return str(entry.get("partner_url") or "").strip()
    return ""


ARTICLE_BY_SLUG = {
    "01-europe-for-under-300": "/travel/europe-under-300.html",
    "02-bali-on-a-budget": "/travel/bali-budget.html",
    "03-48-hours-in-rome": "/travel/rome-48-hours.html",
    "08-travel-esim": "/travel/travel-esim.html",
    "09-car-rental-no-surprises": "/travel/car-rental-europe.html",
    "10-airport-transfer": "/travel/airport-transfer-guide.html",
    "11-skip-the-line": "/travel/skip-the-line-tickets-guide.html",
    "12-tours-and-experiences": "/travel/skip-the-line-tickets-guide.html",
    "13-car-rental-booking-window": "/travel/car-rental-europe.html",
    "14-luggage-storage": "/travel/luggage-storage-guide.html",
}


def content_link(pin: dict, hub_url: str) -> str:
    """SEO/article URL for the pin topic (traffic to hub)."""
    slug = str(pin.get("slug") or "").strip()
    article = ARTICLE_BY_SLUG.get(slug)
    if article:
        return hub_url.rstrip("/") + article
    return ""


def article_link(pin: dict, hub_url: str, day_index: int = 0) -> str:
    """Ссылка на статью/гайд пина.

    Для travel-пинов — сразу партнёрская ссылка Travelpayouts (как в
    app.travelpayouts.com/programs), чтобы клик считался партнёркой.
    Для остальных — go/<slug>.html (если есть) или hub.
    """
    slug = str(pin.get("slug") or "").strip()
    if pin.get("article_url"):
        return str(pin["article_url"])
    # Traffic mix: every other post sends readers to the hub article (SEO/traffic),
    # the rest go straight to the partner link (commission).
    if int(day_index or 0) % 2 == 1:
        seo = content_link(pin, hub_url)
        if seo:
            return seo
    if str(pin.get("niche") or "") == "travel":
        affiliate = partner_url(slug)
        if affiliate:
            return affiliate
    if slug and (ROOT / "docs" / "go" / (slug + ".html")).exists():
        return hub_url.rstrip("/") + "/go/" + slug + ".html"
    return hub_url


def channel_link(config: dict, niche: str) -> str:
    """Ссылка на Telegram-канал под нишу (fallback — основной канал)."""
    links = (config or {}).get("links") or {}
    niche_links = (config or {}).get("niche_channels") or {}
    return str(niche_links.get(niche) or links.get("channel_default") or "")


def build_assets(pin: dict, alt_text: bool = False) -> list:
    """Картинка статьи (пина) для Buffer: assets=[{image:{url}}].

    Buffer GraphQL (ImageAssetInput) не принимает altText — альтернативный
    текст задаётся вручную в UI Buffer. Параметр alt_text оставлен для
    совместимости вызовов, но в API не уходит.
    """
    image = str(pin.get("image_url") or "").strip()
    if not image.startswith(("http://", "https://")):
        return []
    return [{"image": {"url": image}}]


def _fit(hook: str, benefit: str, footer: str, limit: int) -> str:
    """Собирает пост и гарантированно укладывается в лимит, не режа по живому."""
    text = hook + ("\n\n" + benefit if benefit else "") + "\n\n" + footer
    if len(text) <= limit:
        return text
    budget = limit - len(hook) - len(footer) - 4
    if benefit and budget >= 40:
        text = hook + "\n\n" + clip(benefit, budget) + "\n\n" + footer
        if len(text) <= limit:
            return text
    # без benefit: обрезаем хук, но ссылку и CTA оставляем целыми
    room = limit - len(footer) - 2
    return clip(hook, max(20, room)) + "\n\n" + footer


def _link_lines(article: str, channel: str, partner: str = "", label: str = "", article_label: str = "Guide:") -> str:
    lines = []
    if article:
        lines.append((article_label or "Guide:") + " " + article)
    if channel:
        lines.append("Telegram: " + channel)
    if partner:
        lines.append((label or "Ad:") + " " + partner)
    return " · ".join(lines)


def build_x(pin: dict, link: str, style: dict, limit: int = 280, channel: str = "", partner: str = "", partner_label: str = "") -> str:
    """X: хук в первой строке, 0 хэштегов, короткие ссылки (статья + канал)."""
    disclosure = " Ad" if pin.get("affiliate") else ""
    cta = str(style.get("cta") or "").strip()
    hook = _hook(pin.get("title") or "", 120)
    footer = _link_lines(link, channel, partner, partner_label, cta).strip() + disclosure
    benefit = _first_sentence(pin.get("description") or "", 120)
    return clip(_fit(hook, benefit, footer, limit), limit, keep_lines=True)


def build_bluesky(pin: dict, link: str, style: dict, limit: int = 300, channel: str = "", partner: str = "", partner_label: str = "") -> str:
    """Bluesky: хук с эмодзи, 1–3 хэштега, короткие ссылки статья + канал."""
    disclosure = " Ad" if pin.get("affiliate") else ""
    emoji = str(style.get("emoji") or "").strip()
    tags = _tags(style, 3)
    cta = str(style.get("cta") or "").strip()
    hook = (emoji + " " + _hook(pin.get("title") or "", 120)).strip()
    footer = (_link_lines(link, channel, partner, partner_label, cta) + disclosure + (" " + tags if tags else "")).strip()
    benefit = _first_sentence(pin.get("description") or "", 120)
    return clip(_fit(hook, benefit, footer, limit), limit, keep_lines=True)


def build_facebook(pin: dict, link: str, style: dict, limit: int = 1000, channel: str = "", partner: str = "", partner_label: str = "") -> str:
    """Facebook: хук <80 симв., пункты, вопрос, статья + канал, 0–2 тега."""
    disclosure = " Ad" if pin.get("affiliate") else ""
    emoji = str(style.get("emoji") or "").strip()
    tags = _tags(style, 2)
    hook = (emoji + " " + _hook(pin.get("title") or "", 80)).strip()
    bullets = _bullets(pin.get("description") or "")
    question = str(style.get("question") or "").strip()
    cta = str(style.get("cta") or "").strip()
    parts = [hook]
    if bullets:
        parts.append(bullets)
    if question:
        parts.append(question)
    parts.append((_link_lines(link, channel, partner, partner_label, cta) + disclosure).strip())
    if tags:
        parts.append(tags)
    return clip("\n\n".join(parts), limit, keep_lines=True)


def build_text(pin: dict, channel: dict, hub_url: str, config: dict = None, day_index: int = 0) -> str:
    service = str(channel.get("service") or "")
    limit = int(channel.get("max_chars") or 280)
    niche = str(pin.get("niche") or "")
    style = _style(config or {}, niche, day_index)
    links_config = (config or {}).get("links") or {}
    shorten = bool(links_config.get("shorten", False))
    utm = channel.get("utm") or {}
    article = article_link(pin, hub_url, day_index)
    if utm.get("utm_source"):
        params = {"utm_source": utm.get("utm_source"), "utm_medium": "social"}
        if "/travel/" in article or article.rstrip("/") == hub_url.rstrip("/"):
            params["utm_campaign"] = "traffic"
        article = hub_link(article, params)
    article = _short(article, shorten)
    tg_link = channel_link(config, niche)
    # t.me-ссылки и так короткие — сокращаем только длинные.
    tg_channel = _short(tg_link, shorten) if len(tg_link) > 40 else tg_link
    partners = (config or {}).get("niche_partners") or {}
    partner = str(partners.get(niche) or "").strip()
    if niche == "travel":
        programs = tp_programs()
        if programs:
            partner = programs[day_index % len(programs)]
    partner = _short(partner, shorten) if partner and len(partner) > 40 else partner
    partner_label = str((config or {}).get("partner_label") or "Ad:")
    if service in ("twitter", "x"):
        return build_x(pin, article, style, limit, tg_channel, partner, partner_label)
    if service == "bluesky":
        return build_bluesky(pin, article, style, limit, tg_channel, partner, partner_label)
    if service == "facebook":
        return build_facebook(pin, article, style, limit, tg_channel, partner, partner_label)
    title_part = clip(pin.get("title") or "", 90)
    description_part = clip(pin.get("description") or "", max(20, limit - len(title_part) - len(article) - 10))
    return clip(title_part + "\n\n" + description_part + "\n\n" + _link_lines(article, tg_channel), limit)



SCHEDULED_QUERY = """
query Scheduled($org: OrganizationId!, $channels: [ChannelId!], $first: Int!, $after: String) {
  posts(input: {organizationId: $org, filter: {channelIds: $channels, status: [scheduled]}},
        first: $first, after: $after) {
    edges { node { id channelId dueAt status } }
    pageInfo { hasNextPage endCursor }
  }
}
"""


def fetch_scheduled_nodes(client, org_id, channel_ids):
    """Все запланированные посты каналов (для расписания/очистки)."""
    nodes = []
    after = None
    for _ in range(5):
        data = client.gql(
            SCHEDULED_QUERY,
            {"org": org_id, "channels": channel_ids, "first": 100, "after": after},
        )
        posts = data.get("posts") or {}
        for edge in posts.get("edges") or []:
            node = edge.get("node") or {}
            if node:
                nodes.append(node)
        page = posts.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        after = page.get("endCursor")
        if not after:
            break
    return nodes


def schedule_slots(service, config, now):
    """Слоты публикации на horizon_days вперёд (UTC) по конфигу."""
    schedule = config.get("schedule") or {}
    times = [str(item) for item in ((schedule.get("times") or {}).get(service) or [])]
    horizon = int(schedule.get("horizon_days") or 3)
    slots = []
    for day_offset in range(horizon):
        current_date = (now + timedelta(days=day_offset)).date()
        for index, hhmm in enumerate(times):
            try:
                hour, minute = [int(part) for part in hhmm.split(":", 1)]
            except (TypeError, ValueError):
                continue
            slot = datetime(
                current_date.year, current_date.month, current_date.day,
                hour, minute, tzinfo=timezone.utc,
            )
            if slot <= now + timedelta(minutes=30):
                continue
            slots.append((slot, index))
    return slots


def slot_key(slot):
    return slot.strftime("%Y-%m-%d %H:%M")


def pin_for_slot(pin_files, slot, slot_index=0, service=""):
    """Разные пины для слотов и сетей (ротация без повторов подряд)."""
    service_shift = sum(ord(char) for char in str(service)) % max(1, len(pin_files))
    return pin_files[(slot.timetuple().tm_yday * 7 + slot_index + service_shift) % len(pin_files)]


def main(argv=None) -> int:
    import yaml

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "config" / "buffer.yaml"))
    parser.add_argument("--pins", default=str(ROOT / "docs" / "assets" / "pins"))
    parser.add_argument("--live", action="store_true", help="create posts (default: dry-run)")
    parser.add_argument("--services", default="", help="фильтр сетей через запятую (twitter,bluesky,facebook)")
    parser.add_argument("--mode", default="", help="override mode: addToQueue/shareNow/customScheduled")
    parser.add_argument("--date", default="", help="override day (YYYY-MM-DD) for rotation/log")
    parser.add_argument("--report", default=str(ROOT / "data" / "reports"))
    parser.add_argument("--state", default="", help="файл состояния (антиповтор/история)")
    parser.add_argument("--schedule", action="store_true", help="режим расписания: customScheduled по слотам")
    parser.add_argument("--clear-scheduled", action="store_true", help="удалить все scheduled посты и выйти")
    parser.add_argument("--require-affiliate", dest="require_affiliate", action="store_true", default=True,
                        help="block live publishing for pins without a Travelpayouts redirect")
    parser.add_argument("--allow-no-affiliate", dest="require_affiliate", action="store_false")
    args = parser.parse_args(argv)

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}
    hub_url = str(config.get("hub_url") or "https://valdislavn-spec.github.io/content-factory/")
    org_id = str(config.get("organization_id") or "")
    mode = str(config.get("mode") or "addToQueue")
    channels = config.get("channels") or []
    wanted = [part.strip().lower() for part in str(args.services or "").split(",") if part.strip()]
    if wanted:
        channels = [c for c in channels if str(c.get("service") or "").lower() in wanted]
    if args.mode:
        mode = str(args.mode)

    pin_files = [p for p in sorted(Path(args.pins).glob("*.json")) if p.name != "index.json"]
    affiliate_slugs = set()
    tp_config_path = ROOT / "config" / "travelpayouts.yaml"
    if tp_config_path.exists():
        tp_config = yaml.safe_load(tp_config_path.read_text(encoding="utf-8")) or {}
        for slug in (tp_config.get("pins") or {}):
            if (ROOT / "docs" / "go" / (str(slug) + ".html")).exists():
                affiliate_slugs.add(str(slug))
    preferred = [p for p in pin_files if p.stem in affiliate_slugs]
    if preferred:
        pin_files = preferred
    if not pin_files:
        print("no pins found in", args.pins)
        return 1
    now = datetime.now(timezone.utc)
    day = args.date or now.strftime("%Y-%m-%d")

    wanted_services = {part.strip() for part in str(args.services or "").split(",") if part.strip()}
    if wanted_services:
        channels = [channel for channel in channels if str(channel.get("service")) in wanted_services]
    channel_ids = [str(channel.get("channel_id")) for channel in channels]
    client = BufferClient.from_env()
    scheduled_nodes = []
    if client.configured():
        scheduled_nodes = fetch_scheduled_nodes(client, org_id, channel_ids)
    else:
        print("buffer: BUFFER_API_KEY не задан — только план (dry-run)")

    if args.clear_scheduled:
        if not client.configured():
            print("clear: нужен BUFFER_API_KEY")
            return 1
        deleted = 0
        for node in scheduled_nodes:
            post_id = str(node.get("id") or "")
            if not post_id:
                continue
            try:
                client.delete_post(post_id)
                deleted += 1
            except BufferError as error:  # noqa: PERF203
                print("delete FAIL:", str(error)[:160])
        print("clear: удалено scheduled-постов:", deleted)
        return 0

    if args.schedule:
        scheduled_keys = {}
        for node in scheduled_nodes:
            cid = str(node.get("channelId") or "")
            due = str(node.get("dueAt") or "")
            if cid and due:
                scheduled_keys.setdefault(cid, set()).add(due[:16].replace("T", " "))
        created = 0
        skipped = 0
        errors = []
        for channel in channels:
            service = str(channel.get("service") or "")
            cid = str(channel.get("channel_id") or "")
            for slot, slot_index in schedule_slots(service, config, now):
                key = slot_key(slot)
                if key in scheduled_keys.get(cid, set()):
                    skipped += 1
                    continue
                pin_file = pin_for_slot(pin_files, slot, slot_index, service)
                sidecar = json.loads(pin_file.read_text(encoding="utf-8"))
                payload = sidecar.get("pin") or {}
                pin = {
                    "slug": pin_file.stem,
                    "title": payload.get("title") or sidecar.get("title") or "",
                    "description": payload.get("description") or sidecar.get("description") or "",
                    "niche": sidecar.get("niche") or payload.get("niche") or "",
                    "alt_text": payload.get("alt_text") or sidecar.get("alt_text") or "",
                    "image_url": sidecar.get("image_url") or payload.get("media_source", {}).get("url") or "",
                    "article_url": sidecar.get("article_url") or "",
                    "affiliate": bool(sidecar.get("affiliate") or payload.get("link")),
                }
                if not (pin["title"] and pin["description"] and str(pin["image_url"]).startswith("http")):
                    errors.append("quality: " + pin_file.name)
                    print("quality: skip", pin_file.stem)
                    continue
                slug_link = hub_url
                if pin["slug"] in affiliate_slugs:
                    slug_link = "%s/go/%s.html" % (hub_url.rstrip("/"), pin["slug"])
                text = build_text(pin, channel, slug_link, config)
                assets = build_assets(pin, bool(config.get("assets_alt_text")))
                print("plan:", service, slot.strftime("%Y-%m-%dT%H:%MZ"), "|", pin_file.name, "|", len(text), "chars")
                if not args.live:
                    continue
                try:
                    post = client.create_post(
                        cid,
                        text,
                        mode="customScheduled",
                        due_at=slot.strftime("%Y-%m-%dT%H:%M:00.000Z"),
                        metadata=channel.get("metadata"),
                        assets=assets or None,
                    )
                    created += 1
                    print("scheduled:", service, "->", post.get("dueAt"), post.get("id"))
                except BufferError as error:
                    errors.append(str(error))
                    print("FAIL:", service, slot.strftime("%H:%M"), str(error)[:200])
        print("schedule: created=%d skipped=%d errors=%d" % (created, skipped, len(errors)))
        return 0 if not errors else 1

    start = now.timetuple().tm_yday % len(pin_files)

    # Quality-гейт: только хорошие посты — курируемый список пинов, без
    # повторов, с картинкой и непустыми title/description.
    quality = config.get("quality") or {}
    allowed = {str(item) for item in (quality.get("allowed_slugs") or []) if str(item).strip()}
    repeat_days = int(quality.get("repeat_after_days") or 14)
    require_image = bool(quality.get("require_image", True))
    state_path = Path(args.state or (ROOT / str(config.get("state_path") or "data/buffer_state.json")))
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    chosen = None
    for offset in range(len(pin_files)):
        candidate = pin_files[(start + offset) % len(pin_files)]
        candidate_slug = candidate.stem
        if allowed and candidate_slug not in allowed:
            print("quality: skip %s — не входит в курируемый список" % candidate_slug)
            continue
        previous = str(state.get(candidate_slug) or "")[:10]
        if previous:
            try:
                if (date.fromisoformat(day) - date.fromisoformat(previous)).days < repeat_days:
                    print("quality: skip %s — уже публиковался %s" % (candidate_slug, previous))
                    continue
            except ValueError:
                pass
        candidate_sidecar = json.loads(candidate.read_text(encoding="utf-8"))
        candidate_payload = candidate_sidecar.get("pin") or {}
        if not (candidate_payload.get("title") and candidate_payload.get("description")):
            print("quality: skip %s — пустые title/description" % candidate_slug)
            continue
        candidate_image = candidate_sidecar.get("image_url") or candidate_payload.get("media_source", {}).get("url") or ""
        if require_image and not str(candidate_image).startswith("http"):
            print("quality: skip %s — нет картинки" % candidate_slug)
            continue
        chosen = (candidate, candidate_sidecar, candidate_payload)
        break
    if chosen is None:
        print("quality: нет подходящего пина на %s (повторы/качество) — очередь не пополняем" % day)
        return 0
    pin_file, sidecar, pin_payload = chosen
    slug = pin_file.stem
    pin = {
        "slug": slug,
        "title": pin_payload.get("title") or sidecar.get("title") or "",
        "description": pin_payload.get("description") or sidecar.get("description") or "",
        "niche": sidecar.get("niche") or pin_payload.get("niche") or "",
        "alt_text": pin_payload.get("alt_text") or sidecar.get("alt_text") or "",
        "image_url": sidecar.get("image_url") or pin_payload.get("media_source", {}).get("url") or "",
        "article_url": sidecar.get("article_url") or "",
        "affiliate": bool(sidecar.get("affiliate") or pin_payload.get("link")),
    }
    print("pin:", pin_file.name, "| date:", day, "| channels:", len(channels))

    client = BufferClient.from_env() if args.live else BufferClient(token="preview")
    results = []
    slug_link = hub_url
    if slug in affiliate_slugs:
        slug_link = "%s/go/%s.html" % (hub_url.rstrip("/"), slug)
    day_index = now.timetuple().tm_yday
    assets = build_assets(pin, bool(config.get("assets_alt_text")))
    for channel in channels:
        text = build_text(pin, channel, slug_link, config, day_index)
        record = {
            "date": day,
            "service": channel.get("service"),
            "channel_id": channel.get("channel_id"),
            "name": channel.get("name"),
            "text": text,
            "chars": len(text),
            "image": assets[0]["image"]["url"] if assets else "",
            "mode": mode,
            "ok": False,
        }
        if args.live:
            try:
                post = client.create_post(
                    str(channel.get("channel_id")),
                    text,
                    mode=mode,
                    metadata=channel.get("metadata"),
                    assets=assets or None,
                )
                record.update({
                    "ok": True,
                    "post_id": post.get("id"),
                    "due_at": post.get("dueAt"),
                    "external_link": post.get("externalLink") or "",
                })
                if post.get("externalLink"):
                    print("link:", post.get("externalLink"))
                print("queued:", channel.get("service"), "->", post.get("dueAt"))
            except BufferError as error:
                message = str(error)
                if "limit" in message.lower():
                    record["skipped"] = "limit"
                    print("queue full:", channel.get("service"), message[:160])
                    continue
                record["error"] = message
                print("FAIL:", channel.get("service"), message)
        else:
            record["ok"] = True
            print("--- %s (%d chars) ---\n%s" % (channel.get("service"), len(text), text))
            if assets:
                print("[image] %s" % assets[0]["image"]["url"])
        results.append(record)

    report_dir = Path(args.report)
    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / ("buffer-queue-%s.json" % day)
    report.write_text(json.dumps({"pin": pin_file.name, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.live and any(item.get("ok") for item in results):
        state[slug] = day
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    print("report:", report)
    return 0 if all(item.get("ok") or item.get("skipped") for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
