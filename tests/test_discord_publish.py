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
