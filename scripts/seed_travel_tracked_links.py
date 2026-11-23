"""Seed travel tracked links in the D1 link tracker.

Idempotent: existing codes are left untouched. Run:
    .venv/bin/python scripts/seed_travel_tracked_links.py --dry-run
    .venv/bin/python scripts/seed_travel_tracked_links.py
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.integrations.link_tracker import LinkTrackerClient, LinkTrackerError
from content_factory.utils import load_dotenv

US_LINKS = {
    "aviasales": "https://aviasales.tpk.ro/2ZW95Xpf",
    "tiqets": "https://tiqets.tpk.ro/ufgJDVmO",
    "klook": "https://klook.tpk.ro/2NhHWOSD",
    "airalo": "https://airalo.tpk.ro/IQhjJkbT",
    "saily": "https://saily.tpk.ro/QSNyiXp7",
    "yesim": "https://yesim.tpk.ro/uzjpBpju",
    "kiwitaxi": "https://kiwitaxi.tpk.ro/xmQYmqIl",
    "gettransfer": "https://gettransfer.tpk.ro/sMmU1wE7",
    "welcomepickups": "https://tpk.ro/kTevGAQP",
    "localrent": "https://localrent.tpk.ro/edD3Ejwe",
    "economybookings": "https://economybookings.tpk.ro/IwQqKHL3",
    "qeeq": "https://qeeq.tpk.ro/9W1Pi9hm",
    "getrentacar": "https://getrentacar.tpk.ro/tyEGMAcd",
    "kiwi": "https://kiwi.tpk.ro/RJINNJJm",
    "gocity": "https://gocity.tpk.ro/yoqmgDkj",
    "radicalstorage": "https://radicalstorage.tpk.ro/wskVrPYh",
    "airhelp": "https://airhelp.tpk.ro/rZjahO3R",
    "compensair": "https://compensair.tpk.ro/4klXfGpD",
    "kkday": "https://kkday.tpk.ro/11CJTQvo",
}
RU_LINKS = {
    "airalo": "https://airalo.tpk.ro/IQhjJkbT",
    "aviasales": "https://aviasales.tpk.ro/2ZW95Xpf",
    "kiwi": "https://kiwi.tpk.ro/RJINNJJm",
    "kiwitaxi": "https://kiwitaxi.tpk.ro/xmQYmqIl",
    "klook": "https://klook.tpk.ro/2NhHWOSD",
    "localrent": "https://localrent.tpk.ro/edD3Ejwe",
    "tiqets": "https://tiqets.tpk.ro/ufgJDVmO",
}
BLOG_LINKS = {
    "tf-blog-kiwi": "https://kiwi.tpk.ro/RJINNJJm",
    "tf-blog-gocity": "https://gocity.tpk.ro/yoqmgDkj",
    "tf-blog-klook": "https://klook.tpk.ro/2NhHWOSD",
    "tf-blog-es-kiwi": "https://kiwi.tpk.ro/n2alia22",
    "tf-blog-es-gocity": "https://gocity.tpk.ro/zbvrGR7x",
}
PIN_V5 = {
    "tf-pin-v5-aviasales": "https://aviasales.tpk.ro/2ZW95Xpf",
    "tf-pin-v5-localrent": "https://localrent.tpk.ro/vGHu8Vuj",
    "tf-pin-v5-airhelp": "https://airhelp.tpk.ro/WbJKruUg",
    "tf-pin-v5-yesim": "https://yesim.tpk.ro/aU7AT4LC",
    "tf-pin-v5-bali-budget-qr": "https://aviasales.tpk.ro/2ZW95Xpf",
    "tf-pin-v5-dubai-weekend-qr": "https://aviasales.tpk.ro/2ZW95Xpf",
    "tf-pin-v5-winter-sun-qr": "https://aviasales.tpk.ro/2ZW95Xpf",
    "tf-pin-v5-europe-under-300-qr": "https://aviasales.tpk.ro/2ZW95Xpf",
    "tf-pin-v5-travel-esim-qr": "https://yesim.tpk.ro/aU7AT4LC",
    "tf-pin-v5-car-rental-qr": "https://localrent.tpk.ro/vGHu8Vuj",
    "tf-pin-v5-flight-compensation-qr": "https://airhelp.tpk.ro/WbJKruUg",
}


def with_sub_id(url: str, sub_id: str) -> str:
    parts = urlsplit(str(url))
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("sub_id", sub_id)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def ensure(client: LinkTrackerClient, code: str, target: str, channel: str, dry_run: bool) -> str:
    if dry_run:
        print("would create", code, "->", target)
        return "dry"
    for attempt in range(3):
        try:
            client.create_link(code, target, channel=channel, network=code, label=code)
            print("created", code)
            return "created"
        except LinkTrackerError as error:
            message = str(error)
            if "already exists" in message.lower() or "unique" in message.lower():
                print("exists", code)
                return "exists"
            if attempt == 2:
                print("failed", code, message[:160])
                return "failed"
            time.sleep(1)
    return "failed"


def yaml_links():
    import yaml
    data = yaml.safe_load((ROOT / "config" / "travelpayouts.yaml").read_text(encoding="utf-8")) or {}
    for slug, item in (data.get("pins") or {}).items():
        if not isinstance(item, dict):
            continue
        target = str(item.get("partner_url") or "").strip()
        if not target:
            continue
        sub_id = str(item.get("sub_id") or "pin_" + slug)
        yield "tf-pin-" + slug, with_sub_id(target, sub_id), "pinterest"
        yield "tf-guide-" + slug, with_sub_id(target, "guide_" + slug), "travel-guide"


def build_specs():
    specs = list(yaml_links())
    specs += [("us-" + key, with_sub_id(url, "us_landing"), "us-landing") for key, url in US_LINKS.items()]
    specs += [("tf-ru-" + key, with_sub_id(url, "ru_landing"), "ru-landing") for key, url in RU_LINKS.items()]
    specs += [(code, with_sub_id(url, code.replace("tf-blog-", "seo_")), "travel-blog") for code, url in BLOG_LINKS.items()]
    specs += [(code, with_sub_id(url, code), "pinterest") for code, url in PIN_V5.items()]
    return specs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    load_dotenv(ROOT / ".env")
    client = LinkTrackerClient()
    counts = {"created": 0, "exists": 0, "failed": 0, "dry": 0}
    for code, target, channel in build_specs():
        result = ensure(client, code, target, channel, args.dry_run)
        counts[result] = counts.get(result, 0) + 1
    print("summary:", counts)
    return 1 if counts.get("failed", 0) > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
