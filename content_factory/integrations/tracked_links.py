"""Helpers for tracked /r/{code} links on the links-tracker worker."""
from __future__ import annotations

import os
from urllib.parse import urlencode

DEFAULT_TRACKER_BASE = "https://links-tracker.valdislav-n.workers.dev"


def tracker_base() -> str:
    return (os.environ.get("LINK_TRACKER_BASE") or DEFAULT_TRACKER_BASE).rstrip("/")


def tracker_url(code: str, **params: str) -> str:
    clean = {k: str(v) for k, v in params.items() if v not in (None, "")}
    url = "{}/r/{}".format(tracker_base(), str(code).strip())
    return url + ("?" + urlencode(clean) if clean else "")


def guide_code(slug: str) -> str:
    return "tf-guide-{}".format(str(slug).strip())


def pin_code(slug: str) -> str:
    return "tf-pin-{}".format(str(slug).strip())
