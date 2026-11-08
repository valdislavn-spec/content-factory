#!/usr/bin/env python3
"""Publish the Telegram channel cards to Mastodon/Akkoma/Buffer/Tumblr/Pinterest.

Cards + captions are produced by ``scripts/generate_channel_cards.py`` (manifest
in ``docs/assets/channel-cards/manifest.json``).

Usage:
    python scripts/post_channel_cards.py                    # dry-run (default)
    python scripts/post_channel_cards.py --live              # publish everywhere
    python scripts/post_channel_cards.py --live --platforms mastodon,akkoma
    python scripts/post_channel_cards.py --live --channels crypto-news,ai-news

Credentials are read from env/.env:
    MASTODON_BASE_URL / MASTODON_TOKEN
    AKKOMA_BASE_URL / AKKOMA_TOKEN
    BUFFER_API_KEY (X / Bluesky / Facebook channels in Buffer)
    TUMBLR_CONSUMER_KEY / TUMBLR_CONSUMER_SECRET /
    TUMBLR_OAUTH_TOKEN / TUMBLR_OAUTH_TOKEN_SECRET / TUMBLR_BLOG
    PINTEREST_ACCESS_TOKEN / PINTEREST_BOARD_ID (optional; auto-creates a board)

Platform captions already include the Telegram CTA, the travel partner link and
the ad disclosure.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MANIFEST = ROOT / "docs" / "assets" / "channel-cards" / "manifest.json"
REPORT_DIR = ROOT / "data" / "reports"
USER_AGENT = "content-factory-channel-cards/1.0"
FEDIVERSE_LIMIT = 480


def _load_env(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    import os

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _env(name: str, default: str = "") -> str:
    import os

    return (os.environ.get(name, default) or "").strip()


def _clip(text: str, limit: int) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def _post_multipart(
    url: str,
    token: str,
    image_path: Path,
    *,
    fields: Optional[Dict[str, str]] = None,
    timeout: float = 60.0,
) -> Dict[str, Any]:
    boundary = "----contentfactory{}".format(int(time.time() * 1000))
    chunks: List[bytes] = []
    for key, value in (fields or {}).items():
        chunks.append(
            (
                "--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                % (boundary, key, value)
            ).encode("utf-8")
        )
    chunks.append(
        (
            "--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
            "Content-Type: image/png\r\n\r\n"
            % (boundary, image_path.name)
        ).encode("utf-8")
    )
    chunks.append(image_path.read_bytes())
    chunks.append(("\r\n--%s--\r\n" % boundary).encode("utf-8"))
    request = urllib.request.Request(
        url,
        data=b"".join(chunks),
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "multipart/form-data; boundary=" + boundary,
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", "replace")
    return json.loads(raw or "{}")


def _post_json(
    url: str,
    payload: Dict[str, Any],
    token: str,
    *,
    method: str = "POST",
    timeout: float = 45.0,
) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", "replace")
    return json.loads(raw or "{}")


def _get_json(url: str, token: str, *, timeout: float = 30.0) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace") or "{}")


def _fediverse_publish(
    *,
    base: str,
    token: str,
    image: Path,
    row: Dict[str, Any],
    platform: str,
    dry_run: bool,
) -> Dict[str, Any]:
    caption = _clip(row["captions"].get(platform) or row["captions"]["mastodon"], FEDIVERSE_LIMIT)
    if dry_run:
        return {"ok": True, "dry_run": True, "text": caption}
    media = _post_multipart(
        base.rstrip("/") + "/api/v2/media",
        token,
        image,
        fields={"description": row.get("alt_text", "")[:1500]},
    )
    media_id = str(media.get("id") or "")
    payload: Dict[str, Any] = {
        "status": caption,
        "visibility": "public",
        "language": row.get("language", "en"),
    }
    if media_id:
        payload["media_ids"] = [media_id]
    last_error: Optional[Exception] = None
    for attempt in range(3):
        try:
            data = _post_json(base.rstrip("/") + "/api/v1/statuses", payload, token)
            return {"ok": True, "id": data.get("id"), "url": data.get("url") or data.get("uri")}
        except urllib.error.HTTPError as exc:  # media may still be processing
            detail = exc.read().decode("utf-8", "replace")[:200]
            last_error = RuntimeError("HTTP {}: {}".format(exc.code, detail))
            if exc.code in (422, 500) and attempt < 2:
                time.sleep(2 + attempt * 2)
                continue
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            break
    return {"ok": False, "error": str(last_error)}


def _publish_mastodon(row: Dict[str, Any], image: Path, dry_run: bool) -> Dict[str, Any]:
    base, token = _env("MASTODON_BASE_URL"), _env("MASTODON_TOKEN")
    if not base or not token:
        return {"ok": False, "skipped": True, "error": "MASTODON_BASE_URL/MASTODON_TOKEN не заданы"}
    try:
        return _fediverse_publish(
            base=base, token=token, image=image, row=row, platform="mastodon", dry_run=dry_run
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _publish_akkoma(row: Dict[str, Any], image: Path, dry_run: bool) -> Dict[str, Any]:
    base, token = _env("AKKOMA_BASE_URL"), _env("AKKOMA_TOKEN")
    if not base or not token:
        return {"ok": False, "skipped": True, "error": "AKKOMA_BASE_URL/AKKOMA_TOKEN не заданы"}
    try:
        return _fediverse_publish(
            base=base, token=token, image=image, row=row, platform="akkoma", dry_run=dry_run
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _publish_buffer(rows: List[Dict[str, Any]], dry_run: bool) -> List[Dict[str, Any]]:
    try:
        from content_factory.integrations.buffer import BufferClient, BufferError
    except Exception as exc:  # noqa: BLE001
        return [{"ok": False, "error": "Buffer client: {}".format(exc)}]
    client = BufferClient.from_env()
    if not client.configured():
        return [{"ok": False, "skipped": True, "error": "BUFFER_API_KEY не задан"}]
    if dry_run:
        try:
            channels = client.channels()
        except BufferError as exc:
            return [{"ok": False, "error": str(exc)}]
        return [
            {
                "ok": True,
                "dry_run": True,
                "channel": channel.get("name"),
                "service": channel.get("service"),
                "cards": len(rows),
            }
            for channel in channels
            if str(channel.get("service") or "").lower() in {"twitter", "x", "bluesky", "facebook"}
        ]
    service_map = {
        "twitter": "x",
        "x": "x",
        "bluesky": "bluesky",
        "facebook": "facebook",
    }
    try:
        channels = client.channels()
    except BufferError as exc:
        return [{"ok": False, "error": str(exc)}]
    results: List[Dict[str, Any]] = []
    for channel in channels:
        service = str(channel.get("service") or "").lower()
        caption_key = service_map.get(service)
        if not caption_key:
            continue
        for row in rows:
            text = _clip(row["captions"].get(caption_key) or "", 600)
            try:
                post = client.create_post(
                    str(channel.get("id")),
                    text,
                    mode="addToQueue",
                    assets=[{"image": {"url": row["image_url"]}}],
                )
                results.append(
                    {
                        "ok": True,
                        "service": service,
                        "channel": channel.get("name"),
                        "card": row["channel_id"],
                        "post_id": post.get("id"),
                        "status": post.get("status"),
                    }
                )
            except BufferError as exc:
                results.append(
                    {
                        "ok": False,
                        "service": service,
                        "channel": channel.get("name"),
                        "card": row["channel_id"],
                        "error": str(exc),
                    }
                )
    return results


def _publish_tumblr(rows: List[Dict[str, Any]], dry_run: bool) -> List[Dict[str, Any]]:
    try:
        from content_factory.publishers.tumblr import _oauth1_request
    except Exception as exc:  # noqa: BLE001
        return [{"ok": False, "error": "Tumblr helper: {}".format(exc)}]
    keys = {
        key: _env(key)
        for key in (
            "TUMBLR_CONSUMER_KEY",
            "TUMBLR_CONSUMER_SECRET",
            "TUMBLR_OAUTH_TOKEN",
            "TUMBLR_OAUTH_TOKEN_SECRET",
        )
    }
    missing = [key for key, value in keys.items() if not value]
    if missing:
        return [{"ok": False, "skipped": True, "error": "нет " + ", ".join(missing)}]
    blog = _env("TUMBLR_BLOG")
    if not blog:
        return [{"ok": False, "skipped": True, "error": "TUMBLR_BLOG не задан"}]
    url = "https://api.tumblr.com/v2/blog/{}/post".format(urllib.parse.quote(blog, safe=""))
    results: List[Dict[str, Any]] = []
    for row in rows:
        caption = html.escape(row["captions"].get("tumblr") or row["captions"]["mastodon"]).replace("\n", "<br/>")
        params = {
            "type": "photo",
            "state": "published",
            "source": row["image_url"],
            "caption": caption,
            "link": row.get("telegram_url", ""),
            "tags": ",".join(tag.lstrip("#") for tag in row.get("hashtags") or []),
        }
        if dry_run:
            results.append({"ok": True, "dry_run": True, "card": row["channel_id"], "blog": blog})
            continue
        try:
            data = _oauth1_request(
                "POST",
                url,
                params,
                consumer_key=keys["TUMBLR_CONSUMER_KEY"],
                consumer_secret=keys["TUMBLR_CONSUMER_SECRET"],
                token=keys["TUMBLR_OAUTH_TOKEN"],
                token_secret=keys["TUMBLR_OAUTH_TOKEN_SECRET"],
            )
            response = data.get("response") or {}
            results.append(
                {
                    "ok": True,
                    "card": row["channel_id"],
                    "post_id": response.get("id"),
                    "url": "https://{}.tumblr.com/post/{}".format(blog, response.get("id")),
                }
            )
        except Exception as exc:  # noqa: BLE001
            results.append({"ok": False, "card": row["channel_id"], "error": str(exc)})
    return results


def _publish_pinterest(rows: List[Dict[str, Any]], dry_run: bool) -> List[Dict[str, Any]]:
    token = _env("PINTEREST_ACCESS_TOKEN")
    if not token:
        return [{"ok": False, "skipped": True, "error": "PINTEREST_ACCESS_TOKEN не задан"}]
    api = "https://api.pinterest.com/v5"
    board_id = _env("PINTEREST_BOARD_ID")
    if not board_id and not dry_run:
        try:
            boards = _get_json(api + "/boards", token).get("items") or []
            board_id = str(boards[0].get("id") or "") if boards else ""
            if not board_id:
                created = _post_json(
                    api + "/boards",
                    {
                        "name": "Telegram Channels",
                        "description": "Crypto, AI and sports Telegram channels",
                    },
                    token,
                )
                board_id = str(created.get("id") or "")
        except Exception as exc:  # noqa: BLE001
            return [{"ok": False, "error": "Pinterest boards: {}".format(exc)}]
    if not board_id:
        return [{"ok": False, "error": "не удалось получить board_id"}]
    results: List[Dict[str, Any]] = []
    for row in rows:
        payload = {
            "board_id": board_id,
            "title": row["title"][:100],
            "description": (row["description"] + " " + row["captions"].get("pinterest", ""))[:500],
            "alt_text": row.get("alt_text", "")[:500],
            "link": row.get("telegram_url", ""),
            "media_source": {"source_type": "image_url", "url": row["image_url"]},
        }
        if dry_run:
            results.append({"ok": True, "dry_run": True, "card": row["channel_id"], "board_id": board_id})
            continue
        try:
            data = _post_json(api + "/pins", payload, token)
            pin_id = str(data.get("id") or "")
            results.append(
                {
                    "ok": True,
                    "card": row["channel_id"],
                    "pin_id": pin_id,
                    "url": "https://www.pinterest.com/pin/{}/".format(pin_id) if pin_id else "",
                }
            )
        except urllib.error.HTTPError as exc:
            results.append(
                {
                    "ok": False,
                    "card": row["channel_id"],
                    "error": "HTTP {}: {}".format(exc.code, exc.read().decode("utf-8", "replace")[:200]),
                }
            )
        except Exception as exc:  # noqa: BLE001
            results.append({"ok": False, "card": row["channel_id"], "error": str(exc)})
    return results


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Опубликовать карточки Telegram-каналов")
    parser.add_argument("--manifest", default=str(MANIFEST))
    parser.add_argument("--channels", default="", help="Список channel_id через запятую")
    parser.add_argument("--limit", type=int, default=0, help="Сколько карточек обработать")
    parser.add_argument(
        "--platforms",
        default="mastodon,akkoma,buffer,tumblr,pinterest",
        help="Платформы через запятую",
    )
    parser.add_argument("--live", action="store_true", help="Реальная публикация (иначе dry-run)")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    _load_env()
    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    if not manifest_path.exists():
        print("Нет манифеста: {} — сначала запустите generate_channel_cards.py".format(manifest_path))
        return 2
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows: List[Dict[str, Any]] = list(payload.get("cards") or [])
    wanted = [item.strip() for item in str(args.channels or "").split(",") if item.strip()]
    if wanted:
        rows = [row for row in rows if row.get("channel_id") in wanted]
    if args.limit:
        rows = rows[: args.limit]
    if not rows:
        print("Нет карточек для публикации")
        return 2

    platforms = [item.strip().lower() for item in str(args.platforms or "").split(",") if item.strip()]
    dry_run = not args.live
    image_dir = manifest_path.parent
    report: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "cards": [row.get("channel_id") for row in rows],
        "platforms": platforms,
        "results": {},
    }
    print("Карточки: {} · платформы: {} · режим: {}".format(
        ", ".join(row["channel_id"] for row in rows), ", ".join(platforms), "dry-run" if dry_run else "LIVE"
    ))

    for platform in platforms:
        if platform in {"mastodon", "akkoma"}:
            results = []
            for row in rows:
                image = image_dir / str(row.get("file") or (row["channel_id"] + ".png"))
                if not image.exists():
                    results.append({"ok": False, "card": row["channel_id"], "error": "нет файла " + str(image)})
                    continue
                result = (
                    _publish_mastodon(row, image, dry_run)
                    if platform == "mastodon"
                    else _publish_akkoma(row, image, dry_run)
                )
                result["card"] = row["channel_id"]
                results.append(result)
                print("  {} {}: {}".format(
                    platform,
                    row["channel_id"],
                    result.get("url") or result.get("error") or ("dry-run: " + str(result.get("text", ""))[:80]),
                ))
            report["results"][platform] = results
        elif platform == "buffer":
            results = _publish_buffer(rows, dry_run)
            report["results"]["buffer"] = results
            for result in results[:12]:
                print("  buffer: {} {} {}".format(
                    result.get("service"), result.get("card"), result.get("status") or result.get("error") or "dry-run"
                ))
        elif platform == "tumblr":
            results = _publish_tumblr(rows, dry_run)
            report["results"]["tumblr"] = results
            for result in results:
                print("  tumblr: {} {}".format(result.get("card"), result.get("url") or result.get("error") or "dry-run"))
        elif platform == "pinterest":
            results = _publish_pinterest(rows, dry_run)
            report["results"]["pinterest"] = results
            for result in results:
                print("  pinterest: {} {}".format(result.get("card"), result.get("url") or result.get("error") or "dry-run"))
        else:
            print("  неизвестная платформа: {}".format(platform))

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / "channel-cards-post-{}.json".format(
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Отчёт: {}".format(report_path))

    failures = 0
    successes = 0
    for results in report["results"].values():
        for result in results:
            if result.get("ok"):
                successes += 1
            elif not result.get("skipped"):
                failures += 1
    if failures:
        print("Предупреждений: {} (подробности в отчёте)".format(failures))
    return 1 if failures and not successes else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
