#!/usr/bin/env python3
"""Клиент Kit Developer Docs MCP (https://developers.kit.com/mcp) без внешних зависимостей.

Даёт агенту актуальную документацию Kit API v4: поиск эндпоинтов, параметров, схем.
Публичный, авторизация не нужна. Транспорт — streamable HTTP + SSE-ответы.

  .venv/bin/python scripts/kit_docs_mcp.py --tools
  .venv/bin/python scripts/kit_docs_mcp.py --call search_kit_docs --json '{"query":"broadcast send"}'
"""
from __future__ import annotations

import argparse
import json
import urllib.request

URL = "https://developers.kit.com/mcp"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def _parse(body: str) -> dict:
    """SSE/JSON → первый JSON-RPC ответ."""
    if body.lstrip().startswith("{"):
        return json.loads(body)
    for line in body.splitlines():
        if line.startswith("data: "):
            payload = line[6:].strip()
            if payload and payload != "[DONE]":
                try:
                    return json.loads(payload)
                except json.JSONDecodeError:
                    continue
    return {}


class DocsMCP:
    def __init__(self) -> None:
        self._id = 0
        self.session = ""
        self._call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                  "clientInfo": {"name": "dsh-kit-docs", "version": "1.0"}})
        self._notify("notifications/initialized", {})

    def _post(self, payload: dict) -> dict:
        request = urllib.request.Request(URL, data=json.dumps(payload).encode(), method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json, text/event-stream")
        request.add_header("User-Agent", UA)
        if self.session:
            request.add_header("Mcp-Session-Id", self.session)
        with urllib.request.urlopen(request, timeout=60) as response:
            self.session = response.headers.get("Mcp-Session-Id") or self.session
            return _parse(response.read().decode())

    def _call(self, method: str, params: dict) -> dict:
        self._id += 1
        return self._post({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params})

    def _notify(self, method: str, params: dict) -> None:
        self._post({"jsonrpc": "2.0", "method": method, "params": params})

    def tools(self) -> list[dict]:
        return self._call("tools/list", {}).get("result", {}).get("tools", [])

    def call(self, name: str, arguments: dict) -> dict:
        return self._call("tools/call", {"name": name, "arguments": arguments})


def _text(result: dict) -> str:
    content = result.get("result", {}).get("content") or []
    chunks = [c.get("text", "") for c in content if isinstance(c, dict)]
    return "\n".join(chunks) or json.dumps(result, ensure_ascii=False)[:2000]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tools", action="store_true")
    parser.add_argument("--call", default="")
    parser.add_argument("--json", default="{}")
    args = parser.parse_args()
    mcp = DocsMCP()
    if args.tools or not args.call:
        for tool in mcp.tools():
            schema = (tool.get("inputSchema") or {}).get("required") or []
            print(f"- {tool.get('name')}: {(tool.get('description') or '')[:140]}")
            if schema:
                print(f"    required: {schema}")
        return 0
    print(_text(mcp.call(args.call, json.loads(args.json))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
