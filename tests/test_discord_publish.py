"""Discord-публикатор: реальный HTTP-запрос на локальный мок-сервер."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace as NS

import content_factory.publishers.discord as discord_mod
from content_factory.publishers.discord import DiscordPublisher


class _Handler(BaseHTTPRequestHandler):
    received: dict = {}

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        type(self).received = {
            "path": self.path,
            "body": json.loads(self.rfile.read(length).decode("utf-8")),
        }
        payload = json.dumps({"id": "999", "channel_id": "123"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # noqa: D401,ANN001
        return


def test_discord_publish_posts_content(monkeypatch) -> None:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    def fake_http_json(url, payload=None, **kwargs):
        import urllib.request

        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/webhooks/1/token",
            data=json.dumps(payload).encode(), method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)

    monkeypatch.setattr(discord_mod, "http_json", fake_http_json)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/token")

    publisher = DiscordPublisher(settings=NS())
    post = NS(plain_text="Тест", text="Тест", html="Тест", id="t1")
    channel = NS(id="crypto-news", language="en", telegram_chat_id="", title="Crypto")

    result = publisher.publish(post, channel, NS())
    server.server_close()

    assert result.ok is True
    assert result.external_id == "999"
    assert _Handler.received["body"]["content"] == "Тест"


def test_discord_text_is_markdown_not_html() -> None:
    from content_factory.publishers.discord import discord_text

    post = NS(
        html='<b>Headline</b>\n\nText with <i>italic</i> and <a href="https://example.com/a">link</a>.\n\n#Crypto #Bitcoin',
        text="", plain_text="",
    )
    channel = NS(id="crypto-news", language="en", title="Crypto", telegram_chat_id="",
                 public_url="https://t.me/HOOPY0007")
    result = discord_text(post, channel)

    assert "**Headline**" in result
    assert "*italic*" in result
    assert "[link](https://example.com/a)" in result
    assert "<b>" not in result and "<a " not in result
    assert "#Crypto" not in result
    assert result.rstrip().endswith("https://t.me/HOOPY0007")


def test_discord_text_respects_limit() -> None:
    from content_factory.publishers.discord import discord_text

    post = NS(html="Слово " * 800, text="", plain_text="")
    channel = NS(id="ai-news", language="en", title="AI", telegram_chat_id="",
                 public_url="https://t.me/AINEWS0007")
    result = discord_text(post, channel, limit=2000)
    assert len(result) <= 2000 + len("https://t.me/AINEWS0007") + 4
    assert result.rstrip().endswith("https://t.me/AINEWS0007")


def test_discord_publish_uses_cta_safe_mentions_and_wait(monkeypatch) -> None:
    seen: dict = {}

    def fake_http_json(url, payload=None, **kwargs):
        seen["url"] = url
        seen["payload"] = payload
        return {"id": "999", "channel_id": "123"}

    monkeypatch.setattr(discord_mod, "http_json", fake_http_json)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/token")

    publisher = DiscordPublisher(settings=NS())
    post = NS(plain_text="Тест", text="Тест", html="Тест", id="t1", meta={})
    channel = NS(
        id="crypto-news",
        language="en",
        title="Crypto",
        telegram_chat_id="",
        public_url="https://t.me/HOOPY0007",
        cta="Follow us on Telegram — it helps the channel grow.",
        meta={},
    )

    result = publisher.publish(post, channel, NS())

    assert result.ok is True
    assert "wait=true" in seen["url"]
    assert seen["payload"]["allowed_mentions"] == {"parse": []}
    assert "Follow us on Telegram" in seen["payload"]["content"]
    assert seen["payload"]["content"].rstrip().endswith("https://t.me/HOOPY0007")


def test_discord_publish_prefers_channel_webhook(monkeypatch) -> None:
    seen: dict = {}

    def fake_http_json(url, payload=None, **kwargs):
        seen["url"] = url
        return {"id": "1", "channel_id": "2"}

    monkeypatch.setattr(discord_mod, "http_json", fake_http_json)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/global/token")
    monkeypatch.setenv(
        "DISCORD_WEBHOOK_URL_SPORT_NEWS",
        "https://discord.com/api/webhooks/sport/token",
    )

    publisher = DiscordPublisher(settings=NS())
    post = NS(plain_text="Test", text="Test", html="Test", id="t1", meta={})
    channel = NS(
        id="sport-news",
        language="en",
        title="Sports",
        telegram_chat_id="",
        public_url="https://t.me/SPORTNews0007",
        cta="",
        meta={},
    )

    assert publisher.publish(post, channel, NS()).ok is True
    assert "/sport/token" in seen["url"]


def test_discord_publish_attaches_image_embed(monkeypatch) -> None:
    seen: dict = {}

    def fake_http_json(url, payload=None, **kwargs):
        seen["payload"] = payload
        return {"id": "1", "channel_id": "2"}

    monkeypatch.setattr(discord_mod, "http_json", fake_http_json)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/token")

    publisher = DiscordPublisher(settings=NS())
    post = NS(
        plain_text="Test",
        text="Test",
        html="Test",
        id="t1",
        meta={"image_url": "https://example.com/news.jpg"},
    )
    channel = NS(
        id="ai-news",
        language="en",
        title="AI",
        telegram_chat_id="",
        public_url="https://t.me/AINEWS0007",
        cta="",
        meta={},
    )

    assert publisher.publish(post, channel, NS()).ok is True
    assert seen["payload"]["embeds"][0]["image"]["url"] == "https://example.com/news.jpg"


def test_discord_publish_builds_message_url_only_with_guild_id(monkeypatch) -> None:
    monkeypatch.setattr(
        discord_mod,
        "http_json",
        lambda *args, **kwargs: {"id": "10", "channel_id": "20", "guild_id": "30"},
    )
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/token")
    publisher = DiscordPublisher(settings=NS())
    post = NS(plain_text="Test", text="Test", html="Test", id="t1", meta={})
    channel = NS(
        id="ai-news", language="en", title="AI", telegram_chat_id="",
        public_url="https://t.me/AINEWS0007", cta="", meta={},
    )
    result = publisher.publish(post, channel, NS())
    assert result.url == "https://discord.com/channels/30/20/10"
