"""Общий HTTP-клиент соцсетей: User-Agent не должен быть Python-urllib."""

from __future__ import annotations

from content_factory.publishers import social


class _FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return b'{"ok": true}'


def test_http_json_sets_content_factory_user_agent(monkeypatch) -> None:
    captured: dict = {}

    def fake_urlopen(request, timeout=0):
        captured["user_agent"] = request.get_header("User-agent")
        return _FakeResponse()

    monkeypatch.setattr(social.urllib.request, "urlopen", fake_urlopen)
    assert social.http_json("https://example.com/hook", payload={"content": "x"}) == {"ok": True}
    assert captured["user_agent"] == social.DEFAULT_USER_AGENT
    assert "Python-urllib" not in captured["user_agent"]
