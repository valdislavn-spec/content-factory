#!/usr/bin/env python3
"""MCP-сервер Leonardo.ai (stdio JSON-RPC 2.0, только stdlib).

Инструменты:
  • leonardo_generate     — создать генерацию изображения (async);
  • leonardo_generation   — статус генерации и ссылки на изображения;
  • leonardo_download     — дождаться и скачать изображения в assets/generated;
  • leonardo_list_models  — доступные платформенные модели.

Авторизация: LEONARDO_API_KEY (https://app.leonardo.ai/api-access).
API: https://cloud.leonardo.ai/api/rest/v1, заголовок `Authorization: Bearer`.
Документация: docs/leonardo.md.
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
SERVER_INFO = {"name": "leonardo-mcp", "version": "1.0.0"}
BASE_URL = "https://cloud.leonardo.ai/api/rest/v1"
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "assets" / "generated"

DEFAULT_MODEL_ID = "7b592283-e8a7-4c5a-9ba6-d18c31f258b9"  # Lucid Origin
DEFAULT_STYLE_UUID = "111dc692-d470-4eec-b791-3475abac4c46"  # Dynamic


class LeonardoError(RuntimeError):
    """Ошибка Leonardo API с деталями ответа."""


def _api_key() -> str:
    return os.environ.get("LEONARDO_API_KEY", "").strip()


def _request(
    method: str,
    path: str,
    payload: Optional[Any] = None,
    timeout: int = 60,
) -> Any:
    key = _api_key()
    if not key:
        raise LeonardoError(
            "LEONARDO_API_KEY не задан. API-ключ: https://app.leonardo.ai/api-access"
        )
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        BASE_URL + path,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "factory-leonardo-mcp/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
        return json.loads(raw.decode("utf-8")) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise LeonardoError(
            f"Leonardo API {method} {path}: HTTP {exc.code} {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise LeonardoError(f"Leonardo API недоступен: {exc}") from exc


# ---------------------------------------------------------------------------
# операции
# ---------------------------------------------------------------------------
def build_payload(
    prompt: str,
    model_id: str = "",
    width: int = 1024,
    height: int = 1024,
    num_images: int = 1,
    style_uuid: str = "",
    alchemy: bool = False,
    contrast: float = 3.5,
) -> Dict[str, Any]:
    prompt = str(prompt or "").strip()
    if not prompt:
        raise LeonardoError("prompt обязателен")
    width = max(512, min(1536, int(width) // 8 * 8))
    height = max(512, min(1536, int(height) // 8 * 8))
    return {
        "prompt": prompt,
        "modelId": str(model_id or DEFAULT_MODEL_ID),
        "width": width,
        "height": height,
        "num_images": max(1, min(4, int(num_images))),
        "alchemy": bool(alchemy),
        "contrast": float(contrast),
        "styleUUID": str(style_uuid or DEFAULT_STYLE_UUID),
    }


def generate(
    prompt: str,
    model_id: str = "",
    width: int = 1024,
    height: int = 1024,
    num_images: int = 1,
    style_uuid: str = "",
    alchemy: bool = False,
    contrast: float = 3.5,
) -> Dict[str, Any]:
    payload = build_payload(
        prompt, model_id, width, height, num_images, style_uuid, alchemy, contrast
    )
    data = _request("POST", "/generations", payload) or {}
    return {
        "generation_id": (
            data.get("sdGenerationJob", {}).get("generationId")
            or data.get("generationId")
            or data.get("id")
        ),
        "status": "PENDING",
        "payload": payload,
    }


def generation(generation_id: str) -> Dict[str, Any]:
    gid = str(generation_id or "").strip()
    if not gid:
        raise LeonardoError("generation_id обязателен")
    data = _request("GET", f"/generations/{urllib.parse.quote(gid)}") or {}
    job = data.get("generations_by_pk") or data.get("generation") or data
    images = job.get("generated_images") or []
    urls: List[str] = []
    for image in images:
        url = image.get("url") or image.get("imageUrl") if isinstance(image, dict) else None
        if url:
            urls.append(str(url))
    return {
        "generation_id": job.get("id") or gid,
        "status": job.get("status"),
        "images": urls,
        "nsfw": job.get("nsfw"),
    }


def wait_for_generation(
    generation_id: str,
    timeout: int = 180,
    interval: int = 5,
    sleep: Any = time.sleep,
) -> Dict[str, Any]:
    deadline = time.time() + max(10, int(timeout))
    last: Dict[str, Any] = {}
    while time.time() < deadline:
        last = generation(generation_id)
        if last["status"] in {"COMPLETE", "FAILED"}:
            return last
        sleep(max(1, int(interval)))
    last = last or generation(generation_id)
    if last.get("status") == "PENDING":
        raise LeonardoError(f"генерация {generation_id} не завершилась за {timeout} c")
    return last


def _download(url: str, target: Path, timeout: int = 120) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "factory-leonardo-mcp/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        target.write_bytes(response.read())
    return target


def download_images(
    generation_id: str,
    out_dir: str = "",
    timeout: int = 180,
) -> Dict[str, Any]:
    result = wait_for_generation(generation_id, timeout=timeout)
    directory = Path(out_dir) if out_dir else OUT_DIR
    safe = re.sub(r"[^0-9A-Za-z_-]+", "-", str(generation_id))[:40]
    saved: List[str] = []
    for index, url in enumerate(result.get("images") or [], start=1):
        suffix = ".png"
        if ".jpg" in url.lower() or ".jpeg" in url.lower():
            suffix = ".jpg"
        elif ".webp" in url.lower():
            suffix = ".webp"
        target = directory / f"leonardo-{safe}-{index}{suffix}"
        _download(url, target)
        saved.append(str(target))
    return {"generation_id": result.get("generation_id"), "status": result.get("status"), "files": saved}


def list_models(limit: int = 30) -> Dict[str, Any]:
    data = _request("GET", "/platform-models") or {}
    models = data.get("custom_models") or data.get("models") or data
    result: List[Dict[str, Any]] = []
    if isinstance(models, list):
        for model in models[: max(1, int(limit))]:
            if not isinstance(model, dict):
                continue
            result.append(
                {
                    "id": model.get("id"),
                    "name": model.get("name"),
                    "type": model.get("modelType") or model.get("type"),
                }
            )
    return {"count": len(result), "models": result}


# ---------------------------------------------------------------------------
# MCP
# ---------------------------------------------------------------------------
TOOLS: List[Dict[str, Any]] = [
    {
        "name": "leonardo_generate",
        "description": "Создать генерацию изображения в Leonardo.ai (async: вернёт generation_id).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "model_id": {"type": "string"},
                "width": {"type": "integer", "minimum": 512, "maximum": 1536},
                "height": {"type": "integer", "minimum": 512, "maximum": 1536},
                "num_images": {"type": "integer", "minimum": 1, "maximum": 4},
                "style_uuid": {"type": "string"},
                "alchemy": {"type": "boolean"},
                "contrast": {"type": "number"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "leonardo_generation",
        "description": "Статус генерации и ссылки на изображения.",
        "inputSchema": {
            "type": "object",
            "properties": {"generation_id": {"type": "string"}},
            "required": ["generation_id"],
        },
    },
    {
        "name": "leonardo_download",
        "description": "Дождаться генерации и скачать изображения в assets/generated.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "generation_id": {"type": "string"},
                "out_dir": {"type": "string"},
                "timeout": {"type": "integer"},
            },
            "required": ["generation_id"],
        },
    },
    {
        "name": "leonardo_list_models",
        "description": "Доступные модели Leonardo.ai.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
        },
    },
]


def call_tool(name: str, arguments: Dict[str, Any]) -> Any:
    if name == "leonardo_generate":
        return generate(
            arguments.get("prompt", ""),
            arguments.get("model_id", ""),
            int(arguments.get("width") or 1024),
            int(arguments.get("height") or 1024),
            int(arguments.get("num_images") or 1),
            arguments.get("style_uuid", ""),
            bool(arguments.get("alchemy")),
            float(arguments.get("contrast") or 3.5),
        )
    if name == "leonardo_generation":
        return generation(arguments.get("generation_id", ""))
    if name == "leonardo_download":
        return download_images(
            arguments.get("generation_id", ""),
            arguments.get("out_dir", ""),
            int(arguments.get("timeout") or 180),
        )
    if name == "leonardo_list_models":
        return list_models(int(arguments.get("limit") or 30))
    raise LeonardoError(f"неизвестный инструмент: {name}")


def _ok(request_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _err(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    method = message.get("method")
    request_id = message.get("id")
    if method == "initialize":
        return _ok(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            },
        )
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
            return _ok(
                request_id,
                {
                    "content": [
                        {"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}
                    ],
                    "isError": False,
                },
            )
        except Exception as exc:  # noqa: BLE001
            return _ok(
                request_id,
                {"content": [{"type": "text", "text": f"Ошибка: {exc}"}], "isError": True},
            )
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
