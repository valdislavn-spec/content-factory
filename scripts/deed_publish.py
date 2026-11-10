#!/usr/bin/env python3
"""Публикация папки на deed.page (нейтральный домен, без имени).

    ./.venv/bin/python scripts/deed_publish.py --dir docs/deals --slug deals-finds

Токен хранится в ~/.local/keys/deed-page.json (workspace .local/keys/deed-page.json).
Первый publish создаёт сайт и возвращает токен; обновления — сAuthorization: Bearer.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT.parent
TOKEN_FILE = WORKSPACE / ".local" / "keys" / "deed-page.json"
PROXY = "socks5h://127.0.0.1:1080"  # deed.page из РФ доступен только через прокси


def token() -> str:
    if TOKEN_FILE.exists():
        return str(json.loads(TOKEN_FILE.read_text(encoding="utf-8")).get("token") or "")
    return os.environ.get("DEEDPAGE_TOKEN", "")


def pack(dir_path: Path) -> Path:
    tmp = Path(tempfile.mkstemp(suffix=".tar.gz")[1])
    with tarfile.open(tmp, "w:gz") as tar:
        for path in sorted(dir_path.rglob("*")):
            if path.is_file():
                tar.add(path, arcname=str(path.relative_to(dir_path)))
    return tmp


def publish(dir_path: Path, slug: str, proxy: str) -> dict:
    archive = pack(dir_path)
    cmd = [
        "curl", "-s", "-m", "180", "--socks5-hostname", proxy.replace("socks5h://", ""),
        "-X", "PUT", f"https://deed.page/v1/sites?slug={slug}&ref=llms",
        "-H", "Content-Type: application/gzip",
        "-H", "X-Client: dsh-agent",
        "--data-binary", f"@{archive}",
        "-w", "\nHTTP:%{http_code}",
    ]
    tok = token()
    if tok:
        cmd += ["-H", f"Authorization: Bearer {tok}"]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=200).stdout
    archive.unlink(missing_ok=True)
    body, _, status_line = out.rpartition("\nHTTP:")
    data = json.loads(body)
    data["_http"] = status_line.strip()
    return data


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Publish static site to deed.page")
    parser.add_argument("--dir", default=str(ROOT / "build" / "deals"))
    parser.add_argument("--slug", default="deals-finds")
    parser.add_argument("--proxy", default=PROXY)
    args = parser.parse_args(argv)
    result = publish(Path(args.dir), args.slug, args.proxy)
    print(json.dumps({k: result.get(k) for k in ("ok", "url", "version", "files", "bytes", "_http", "token")}, ensure_ascii=False, indent=2))
    if result.get("token"):
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(json.dumps({"slug": args.slug, "url": result.get("url"), "token": result["token"]}, ensure_ascii=False, indent=2), encoding="utf-8")
        print("token сохранён в", TOKEN_FILE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
