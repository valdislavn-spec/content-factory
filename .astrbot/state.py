"""Сохранение/восстановление data/ AstrBot в приватном HF dataset."""
from __future__ import annotations

import os
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(os.environ["ASTRBOT_ROOT"]).resolve()
DATA = ROOT / "data"
TOKEN = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_API_KEY") or ""
REPO = os.environ.get("HF_REPO", "ERPSAS/cf-astrbot-state")
FILENAME = "astrbot_data.tar.gz"


def restore() -> None:
    if not TOKEN:
        print("no HF token, skip restore")
        return
    from huggingface_hub import hf_hub_download

    try:
        path = hf_hub_download(repo_id=REPO, filename=FILENAME, repo_type="dataset", token=TOKEN)
    except Exception as exc:  # noqa: BLE001
        print("no saved state:", exc)
        return
    ROOT.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path) as tar:
        tar.extractall(ROOT)
    print("state restored from", REPO)


def save() -> None:
    if not TOKEN:
        print("no HF token, skip save")
        return
    if not DATA.exists():
        print("no data to save")
        return
    from huggingface_hub import HfApi

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        name = tmp.name
    with tarfile.open(name, "w:gz") as tar:
        tar.add(DATA, arcname="data")
    HfApi(token=TOKEN).upload_file(
        path_or_fileobj=name,
        path_in_repo=FILENAME,
        repo_id=REPO,
        repo_type="dataset",
        commit_message="astrbot state sync",
    )
    print("state saved to", REPO)


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "restore"
    {"restore": restore, "save": save}[action]()
