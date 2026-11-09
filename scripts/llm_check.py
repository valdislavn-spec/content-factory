#!/usr/bin/env python3
"""Реальная проверка LLM-провайдеров: один короткий вызов каждым.

Показывает причину сбоя (HTTP-код и тело без секретов), чтобы чинить
Cloudflare-блоки, устаревшие free-модели и reasoning-лимиты.
Для OpenRouter дополнительно перебирает free-модели каталога и указывает,
какая из них реально отвечает.

Запуск: python scripts/llm_check.py [--max-tokens 300]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from content_factory.config import Settings  # noqa: E402
from content_factory.nlp.llm import OpenAICompatibleLLM, _build_llm  # noqa: E402

PROVIDERS = [
    "cloudflare",
    "groq",
    "cohere",
    "pollinations",
    "gemini",
    "ollama_cloud",
    "openrouter",
]
PROMPT = "Reply with the single word: OK"


def probe(client, prompt=PROMPT, max_tokens=300):
    try:
        raw = client._generate(prompt, "", max_tokens, 0.0)
        answer = " ".join(str(raw or "").split())[:40]
        return {"ok": bool(answer), "answer": answer, "model": getattr(client, "model", "")}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": (type(exc).__name__ + ": " + str(exc))[:400]}


def free_openrouter_models(timeout=25):
    token = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not token:
        return []
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/models",
        headers={"Authorization": "Bearer " + token, "User-Agent": "content-factory-llm-check"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        catalog = json.load(response)
    return [
        item.get("id")
        for item in catalog.get("data") or []
        if str((item.get("pricing") or {}).get("prompt")) in ("0", "0.0", "0.00")
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-tokens", type=int, default=300)
    args = parser.parse_args()
    settings = Settings.load()
    results = {}
    for name in PROVIDERS:
        try:
            client = _build_llm(name, settings)
        except Exception as exc:  # noqa: BLE001
            results[name] = {"ok": False, "error": "build: " + str(exc)[:200]}
            continue
        if not getattr(client, "available", False):
            results[name] = {"ok": False, "error": "key missing / unavailable"}
            continue
        results[name] = probe(client, max_tokens=args.max_tokens)

    # OpenRouter: перебор free-моделей, если текущая не отвечает.
    if not results.get("openrouter", {}).get("ok"):
        candidates = []
        try:
            candidates = free_openrouter_models()
        except Exception as exc:  # noqa: BLE001
            results["openrouter_catalog"] = {"error": str(exc)[:200]}
        working = []
        for model in candidates[:12]:
            client = OpenAICompatibleLLM(
                {
                    "base_url": "https://openrouter.ai/api/v1",
                    "api_key_env": "OPENROUTER_API_KEY",
                    "model": model,
                    "timeout": 60,
                }
            )
            if not client.available:
                break
            outcome = probe(client, max_tokens=args.max_tokens)
            if outcome.get("ok"):
                working.append(model)
                if len(working) >= 3:
                    break
        results["openrouter_free_probe"] = {
            "catalog_free": len(candidates),
            "working": working,
            "candidates": candidates[:12],
        }

    print(json.dumps(results, ensure_ascii=False, indent=2))
    bad = [name for name, item in results.items() if isinstance(item, dict) and item.get("ok") is False]
    print("\nFAILED:", ", ".join(bad) if bad else "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
