#!/usr/bin/env python3
"""MCP-сервер генерации изображений: Pollinations (без ключа), Leonardo, HuggingFace.

Инструменты:
  • image_generate  — сгенерировать изображение и сохранить в assets/generated;
  • image_providers — какие провайдеры доступны (по наличию ключей).

Провайдеры:
  pollinations — бесплатно, без ключа, доступен из РФ (default);
  leonardo     — платный API Leonardo.ai, нужен LEONARDO_API_KEY;
  huggingface  — инференс HF, нужен HUGGINGFACE_API_KEY (локально из РФ DNS
                 часто недоступен, в GitHub Actions работает).

Документация: docs/image-generation.md.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "image-mcp", "version": "1.0.0"}
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "assets" / "generated"
POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"
POLLINATIONS_TOKEN_ENV = "POLLINATIONS_TOKEN"  # необязательный pollen-ключ
HF_MODEL = "black-forest-labs/FLUX.1-schnell"


class ImageError(RuntimeError):
    """Ошибка генерации изображения."""


def _key(name: str) -> str:
    return os.environ.get(name, "").strip()


def available_providers() -> List[str]:
    providers = ["pollinations"]
    if _key("LEONARDO_API_KEY"):
        providers.append("leonardo")
    if _key("HUGGINGFACE_API_KEY"):
        providers.append("huggingface")
    return providers


def _clamp(value: int, low: int = 256, high: int = 1536) -> int:
    value = int(value)
    return max(low, min(high, value // 8 * 8))


def _fetch(url: str, payload: Optional[bytes] = None, headers: Optional[Dict[str, str]] = None,
           timeout: int = 180, method: str = "GET") -> bytes:
    request = urllib.request.Request(url, data=payload, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200]
        raise ImageError(f"HTTP {exc.code} от {urllib.parse.urlsplit(url).netloc}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ImageError(f"сеть недоступна для {urllib.parse.urlsplit(url).netloc}: {exc}") from exc


def _save(data: bytes, target: Path, suffix: str = ".jpg") -> Path:
    if not data:
        raise ImageError("провайдер вернул пустой ответ")
    if len(data) < 1024:
        snippet = data[:200].decode("utf-8", "replace")
        raise ImageError(f"похоже на ошибку вместо изображения: {snippet}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def generate_pollinations(
    prompt: str, width: int = 1024, height: int = 1024,
    model: str = "flux", seed: Optional[int] = None, out_dir: str = "",
) -> Dict[str, Any]:
    prompt = str(prompt or "").strip()
    if not prompt:
        raise ImageError("prompt обязателен")
    params: Dict[str, str] = {
        "width": str(_clamp(width)),
        "height": str(_clamp(height)),
        "model": model or "flux",
        "nologo": "true",
    }
    if seed is not None:
        params["seed"] = str(int(seed))
    token = _key(POLLINATIONS_TOKEN_ENV)
    if token:
        params["token"] = token
    url = POLLINATIONS_URL.format(prompt=urllib.parse.quote(prompt)) + "?" + urllib.parse.urlencode(params)
    data = _pollinations_fetch(url)
    safe = re.sub(r"[^0-9A-Za-z]+", "-", prompt.strip().lower())[:40].strip("-") or "image"
    directory = Path(out_dir) if out_dir else OUT_DIR
    suffix = ".png" if data[:8].startswith(b"\x89PNG") else ".jpg"
    target = directory / f"pollinations-{safe}-{int(time.time())}{suffix}"
    path = _save(data, target, suffix)
    return {"provider": "pollinations", "prompt": prompt, "file": str(path),
            "width": _clamp(width), "height": _clamp(height), "bytes": len(data)}


def _pollinations_fetch(url: str, attempts: int = 3) -> bytes:
    """Pollinations бесплатно даёт 1 изображение/45 с на IP — ждём и повторяем."""
    last_error: Optional[ImageError] = None
    for attempt in range(attempts):
        try:
            return _fetch(url, timeout=240)
        except ImageError as exc:
            last_error = exc
            match = re.search(r"Retry after (\d+)s", str(exc))
            if "FREE_LIMIT" not in str(exc) and "402" not in str(exc):
                raise
            if attempt < attempts - 1:
                wait = int(match.group(1)) + 2 if match else 45
                time.sleep(max(5, min(70, wait)))
    raise last_error or ImageError("Pollinations недоступен")


def generate_huggingface(
    prompt: str, width: int = 1024, height: int = 1024,
    model: str = "", out_dir: str = "",
) -> Dict[str, Any]:
    key = _key("HUGGINGFACE_API_KEY")
    if not key:
        raise ImageError("HUGGINGFACE_API_KEY не задан")
    prompt = str(prompt or "").strip()
    if not prompt:
        raise ImageError("prompt обязателен")
    model_id = model or HF_MODEL
    url = f"https://router.huggingface.co/hf-inference/models/{model_id}"
    body = json.dumps({"inputs": prompt, "parameters": {
        "width": _clamp(width), "height": _clamp(height)}}).encode("utf-8")
    data = _fetch(url, payload=body, headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json",
        "User-Agent": "factory-image-mcp/1.0"}, timeout=240, method="POST")
    safe = re.sub(r"[^0-9A-Za-z]+", "-", prompt.strip().lower())[:40].strip("-") or "image"
    directory = Path(out_dir) if out_dir else OUT_DIR
    suffix = ".png" if data[:8].startswith(b"\x89PNG") else ".jpg"
    path = _save(data, directory / f"hf-{safe}-{int(time.time())}{suffix}", suffix)
    return {"provider": "huggingface", "prompt": prompt, "file": str(path),
            "width": _clamp(width), "height": _clamp(height), "bytes": len(data)}


def generate_leonardo(prompt: str, width: int = 1024, height: int = 1024, out_dir: str = "") -> Dict[str, Any]:
    sys.path.insert(0, str(ROOT))
    import tools.leonardo_mcp as leo  # ленивый импорт: без ключа не нужен

    job = leo.generate(prompt, width=width, height=height)
    result = leo.download_images(str(job["generation_id"]), out_dir=out_dir)
    files = result.get("files") or []
    return {"provider": "leonardo", "prompt": prompt, "file": files[0] if files else "",
            "files": files, "width": _clamp(width), "height": _clamp(height)}


def generate(
    prompt: str, provider: str = "", width: int = 1024, height: int = 1024,
    model: str = "", seed: Optional[int] = None, out_dir: str = "",
) -> Dict[str, Any]:
    chosen = str(provider or "pollinations").strip().lower()
    if chosen == "pollinations":
        return generate_pollinations(prompt, width, height, model or "flux", seed, out_dir)
    if chosen == "huggingface":
        return generate_huggingface(prompt, width, height, model, out_dir)
    if chosen == "leonardo":
        return generate_leonardo(prompt, width, height, out_dir)
    raise ImageError(f"неизвестный провайдер: {provider} (pollinations|huggingface|leonardo)")


# ---------------------------------------------------------------------------
# MCP
# ---------------------------------------------------------------------------
TOOLS: List[Dict[str, Any]] = [
    {
        "name": "image_generate",
        "description": "Сгенерировать изображение (по умолчанию Pollinations, без ключа).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "provider": {"type": "string", "enum": ["pollinations", "huggingface", "leonardo"]},
                "width": {"type": "integer", "minimum": 256, "maximum": 1536},
                "height": {"type": "integer", "minimum": 256, "maximum": 1536},
                "model": {"type": "string"},
                "seed": {"type": "integer"},
                "out_dir": {"type": "string"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "image_providers",
        "description": "Доступные провайдеры генерации (по наличию ключей).",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def call_tool(name: str, arguments: Dict[str, Any]) -> Any:
    if name == "image_generate":
        return generate(
            arguments.get("prompt", ""),
            arguments.get("provider") or "",
            int(arguments.get("width") or 1024),
            int(arguments.get("height") or 1024),
            arguments.get("model") or "",
            arguments.get("seed"),
            arguments.get("out_dir") or "",
        )
    if name == "image_providers":
        return {"providers": available_providers(), "default": "pollinations"}
    raise ImageError(f"неизвестный инструмент: {name}")


def _ok(request_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _err(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    method = message.get("method")
    request_id = message.get("id")
    if method == "initialize":
        return _ok(request_id, {"protocolVersion": PROTOCOL_VERSION,
                                "capabilities": {"tools": {"listChanged": False}},
                                "serverInfo": SERVER_INFO})
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "ping":
        return _ok(request_id, {})
    if method == "tools/list":
        return _ok(request_id, {"tools": TOOLS})
    if method == "tools/call":
        params = message.get("params") or {}
        arguments = params.get("arguments") or {}
        try:
            result = call_tool(str(params.get("name", "")), arguments if isinstance(arguments, dict) else {})
            return _ok(request_id, {"content": [
                {"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
                "isError": False})
        except Exception as exc:  # noqa: BLE001
            return _ok(request_id, {"content": [
                {"type": "text", "text": f"Ошибка: {exc}"}], "isError": True})
    return _err(request_id, -32601, f"метод не поддерживается: {method}")


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            sys.stdout.write(json.dumps(_err(None, -32700, "invalid JSON")) + "\n")
            sys.stdout.flush()
            continue
        try:
            result = handle(message)
        except Exception as exc:  # noqa: BLE001
            result = _err(message.get("id"), -32603, f"внутренняя ошибка: {exc}")
        if result is not None:
            sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
