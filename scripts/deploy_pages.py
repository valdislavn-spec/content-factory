#!/usr/bin/env python3
"""Деплой статической папки на Cloudflare Pages (Direct Upload API).

    ./.venv/bin/python scripts/deploy_pages.py --dir docs/deals --project deals-finds

Нужны CLOUDFLARE_ACCOUNT_ID и CLOUDFLARE_API_TOKEN в .env.
Создаёт проект при необходимости и загружает deployment (production).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:  # optional dependency, see requirements-optional.txt
    requests = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
API = "https://api.cloudflare.com/client/v4"


def load_env() -> dict:
    env = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def api_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def ensure_project(account: str, token: str, name: str) -> str:
    if requests is None:
        raise SystemExit("Нужен requests: pip install -r requirements-optional.txt")
    url = f"{API}/accounts/{account}/pages/projects"
    r = requests.get(url, headers=api_headers(token), timeout=30)
    projects = {p.get("name") for p in (r.json().get("result") or [])}
    if name in projects:
        return name
    r = requests.post(url, headers=api_headers(token), timeout=30, json={"name": name, "production_branch": "main"})
    data = r.json()
    if not data.get("success"):
        raise SystemExit(f"Не удалось создать проект {name}: {data.get('errors')}")
    return name


def collect(dir_path: Path) -> tuple[dict, list[tuple[str, str, bytes]]]:
    manifest = {}
    parts = []
    for path in sorted(dir_path.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(dir_path)).replace("\\", "/")
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        manifest[rel] = sha
        parts.append((sha, rel, data))
    return manifest, parts


def deploy(account: str, token: str, project: str, dir_path: Path, branch: str = "main") -> str:
    if requests is None:
        raise SystemExit("Нужен requests: pip install -r requirements-optional.txt")
    manifest, parts = collect(dir_path)
    url = f"{API}/accounts/{account}/pages/projects/{project}/deployments"
    files = [("manifest", (None, json.dumps(manifest))), ("branch", (None, branch))]
    seen = set()
    for sha, rel, data in parts:
        if sha in seen:
            continue
        seen.add(sha)
        files.append((sha, (rel, data, "application/octet-stream")))
    r = requests.post(url, headers=api_headers(token), files=files, timeout=180)
    data = r.json()
    if not data.get("success"):
        raise SystemExit(f"Деплой не удался: {r.status_code} {json.dumps(data.get('errors'))[:500]}")
    result = data.get("result") or {}
    return str(result.get("url") or f"https://{project}.pages.dev")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Деплой на Cloudflare Pages")
    parser.add_argument("--dir", default=str(ROOT / "exports" / "landing"))
    parser.add_argument("--project", default="content-factory")
    parser.add_argument("--branch", default="main")
    args = parser.parse_args(argv)
    env = load_env()
    account = env.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = env.get("CLOUDFLARE_API_TOKEN", "")
    if not account or not token:
        print("Нет CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN в .env", file=sys.stderr)
        return 2
    dir_path = Path(args.dir)
    if not dir_path.exists():
        print(f"Нет папки {dir_path}", file=sys.stderr)
        return 2
    project = ensure_project(account, token, args.project)
    url = deploy(account, token, project, dir_path, branch=args.branch)
    print(f"Deployed → https://{project}.pages.dev ({url})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
