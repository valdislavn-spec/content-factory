#!/usr/bin/env python3
"""Бэкап облачных данных проекта в OneDrive — запускается в GitHub Actions.

Что сохраняется (то, чего нет на выключенном Mac):
    repo.tar.gz           — снимок HEAD репозитория (git archive)
    growth-reports.tar.gz — ветка growth-reports (отчёты + сырые JSON)
    artifacts/<flow>/...  — последние zip-артефакты workflows
                            (content-factory: outbox/reports/logs;
                             growth-report: Markdown + raw JSON)
    manifest.json         — что вошло, размеры, время

Куда: rclone remote (по умолчанию onedrive:ServerBackups), дата-папка,
ретеншен на облаке — 30 дней. Конфиг rclone в CI берётся из секрета
RCLONE_CONF_B64 (см. .github/workflows/onedrive-backup.yml).

Локальный тест:
    GITHUB_TOKEN=... python scripts/cloud_backup.py --runs 1 --remote onedrive:ServerBackups-test
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKFLOWS = ("content-factory.yml", "growth-report.yml")


def log(message: str) -> None:
    print("[{}] {}".format(datetime.now(timezone.utc).strftime("%H:%M:%S"), message), flush=True)


def run(command: Sequence[str], *, check: bool = False, timeout: int = 600) -> subprocess.CompletedProcess:
    result = subprocess.run(
        command, capture_output=True, text=True, timeout=timeout, cwd=str(ROOT), check=False
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            "команда {} упала: {}".format(" ".join(command), (result.stderr or "")[:500])
        )
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


def github_api(url: str, token: str) -> tuple:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer {}".format(token),
            "Accept": "application/vnd.github+json",
            "User-Agent": "content-factory-backup",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def successful_runs(repo: str, workflow: str, token: str, limit: int) -> List[Dict[str, Any]]:
    url = "https://api.github.com/repos/{}/actions/workflows/{}/runs?per_page={}&status=success".format(
        repo, workflow, max(limit, 1)
    )
    status, _headers, body = github_api(url, token)
    if status != 200:
        log("не удалось получить runs {}: HTTP {}".format(workflow, status))
        return []
    try:
        return (json.loads(body) or {}).get("workflow_runs", [])[:limit]
    except ValueError:
        return []


def run_artifacts(repo: str, run_id: int, token: str) -> List[Dict[str, Any]]:
    url = "https://api.github.com/repos/{}/actions/runs/{}/artifacts".format(repo, run_id)
    status, _headers, body = github_api(url, token)
    if status != 200:
        return []
    try:
        artifacts = (json.loads(body) or {}).get("artifacts", [])
    except ValueError:
        return []
    return [a for a in artifacts if not a.get("expired") and a.get("size_in_bytes")]


def download_artifact(repo: str, artifact_id: int, token: str, destination: Path) -> bool:
    """Скачивает zip артефакта: сначала API-редирект, затем signed URL без токена."""
    url = "https://api.github.com/repos/{}/actions/artifacts/{}/zip".format(repo, artifact_id)
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer {}".format(token),
            "Accept": "application/vnd.github+json",
            "User-Agent": "content-factory-backup",
        },
    )
    opener = urllib.request.build_opener(NoRedirect)
    try:
        opener.open(request, timeout=40)
        return False  # без редиректа — нечего скачивать
    except urllib.error.HTTPError as exc:
        if exc.code not in (301, 302, 303, 307):
            log("артефакт {}: HTTP {}".format(artifact_id, exc.code))
            return False
        location = exc.headers.get("Location")
    if not location:
        return False
    try:
        with urllib.request.urlopen(location, timeout=120) as response:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(response.read())
        return True
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        log("скачивание артефакта {} не удалось: {}".format(artifact_id, exc))
        return False


def git_archive(ref: str, output: Path) -> bool:
    result = run(["git", "archive", "--format=tar.gz", "-o", str(output), ref])
    return result.returncode == 0 and output.is_file()


def build_backup(
    repo: str,
    token: str,
    workflows: Sequence[str],
    runs: int,
    staging: Path,
) -> Dict[str, Any]:
    manifest: Dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repo": repo,
        "files": [],
    }
    # 1) снимок репозитория
    repo_tar = staging / "repo.tar.gz"
    if git_archive("HEAD", repo_tar):
        manifest["files"].append({"name": repo_tar.name, "bytes": repo_tar.stat().st_size})
        log("repo.tar.gz: {} байт".format(repo_tar.stat().st_size))
    # 2) ветка growth-reports
    fetch = run(["git", "fetch", "origin", "growth-reports"])
    if fetch.returncode == 0:
        branch_tar = staging / "growth-reports.tar.gz"
        if git_archive("FETCH_HEAD", branch_tar):
            manifest["files"].append(
                {"name": branch_tar.name, "bytes": branch_tar.stat().st_size}
            )
            log("growth-reports.tar.gz: {} байт".format(branch_tar.stat().st_size))
    # 3) артефакты последних успешных запусков
    downloaded = 0
    for workflow in workflows:
        for run_info in successful_runs(repo, workflow, token, runs):
            run_id = run_info.get("id")
            if not run_id:
                continue
            for artifact in run_artifacts(repo, int(run_id), token):
                destination = (
                    staging
                    / "artifacts"
                    / Path(workflow).stem
                    / str(run_id)
                    / "{}.zip".format(artifact.get("name", "artifact"))
                )
                if download_artifact(repo, int(artifact["id"]), token, destination):
                    downloaded += 1
                    manifest["files"].append(
                        {
                            "name": str(destination.relative_to(staging)),
                            "bytes": destination.stat().st_size,
                        }
                    )
        log("{}: артефактов скачано {}".format(workflow, downloaded))
    manifest["artifacts_downloaded"] = downloaded
    (staging / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return manifest


def rclone_base(args: argparse.Namespace) -> List[str]:
    binary = args.rclone_bin or os.environ.get("RCLONE_BIN", "") or shutil.which("rclone") or "rclone"
    command = [binary]
    config = args.rclone_config or os.environ.get("RCLONE_CONFIG", "")
    if config:
        command += ["--config", config]
    return command


def upload(archive: Path, checksum: Path, remote: str, args: argparse.Namespace) -> bool:
    command = rclone_base(args)
    target = remote.rstrip("/")
    ok = True
    for path in (archive, checksum):
        result = run(command + ["copyto", str(path), "{}/{}".format(target, path.name)], timeout=1800)
        if result.returncode != 0:
            ok = False
            log("rclone copyto {}: {}".format(path.name, (result.stderr or "").strip()[:300]))
    if ok:
        log("выгружено в {}".format(target))
    return ok


def prune_remote(remote: str, keep_days: int, args: argparse.Namespace) -> None:
    if keep_days <= 0:
        return
    result = run(
        rclone_base(args)
        + ["delete", remote.rstrip("/"), "--min-age", "{}d".format(keep_days),
           "--include", "server-backup-*"],
        timeout=600,
    )
    if result.returncode == 0:
        log("ретеншен облака: удалены архивы старше {} дней".format(keep_days))


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Бэкап облачных данных в OneDrive")
    parser.add_argument("--remote", default=os.environ.get("ONEDRIVE_BACKUP_REMOTE", "onedrive:ServerBackups"))
    parser.add_argument("--workflows", default=",".join(DEFAULT_WORKFLOWS))
    parser.add_argument("--runs", type=int, default=3, help="по сколько успешных запусков на workflow")
    parser.add_argument("--keep-days", type=int, default=30)
    parser.add_argument("--rclone-bin", default="")
    parser.add_argument("--rclone-config", default="")
    parser.add_argument("--local-dir", default="", help="оставить архив локально в этой папке")
    parser.add_argument("--no-upload", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GH_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "valdislavn-spec/content-factory")
    if not token:
        log("GITHUB_TOKEN не задан")
        return 2
    workflows = [w.strip() for w in args.workflows.split(",") if w.strip()]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        manifest = build_backup(repo, token, workflows, max(args.runs, 1), staging)
        archive = Path(tmp) / "server-backup-{}.tar.gz".format(stamp)
        checksum = archive.with_suffix(".sha256")
        with tarfile.open(archive, "w:gz") as tar:
            for path in sorted(staging.rglob("*")):
                if path.is_file():
                    tar.add(path, arcname=str(path.relative_to(staging)))
        digest = hashlib.sha256()
        with archive.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        checksum.write_text("{}  {}\n".format(digest.hexdigest(), archive.name), encoding="utf-8")
        log("архив: {} ({:.1f} MB)".format(archive.name, archive.stat().st_size / 1024 / 1024))
        if args.local_dir:
            local = Path(args.local_dir).expanduser()
            local.mkdir(parents=True, exist_ok=True)
            shutil.copy2(archive, local / archive.name)
            shutil.copy2(checksum, local / checksum.name)
            log("локальная копия: {}".format(local))
        if args.dry_run or args.no_upload:
            log("выгрузка пропущена (dry-run)")
            return 0
        if not upload(archive, checksum, args.remote, args):
            return 1
        prune_remote(args.remote, args.keep_days, args)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
