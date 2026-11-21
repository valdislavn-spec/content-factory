"""Submit sitemap URLs to IndexNow for every site we control."""
from __future__ import annotations
import json, re, sys, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
KEY = "79baf24dc0f238079df76bfe525ce384"
SITES = [
    {"host": "valdislavn-spec.github.io", "sitemap": ROOT/"docs"/"sitemap.xml", "prefix": "https://valdislavn-spec.github.io/content-factory/", "key_location": f"https://valdislavn-spec.github.io/content-factory/{KEY}.txt"},
    {"host": "valdislavn-spec.github.io", "sitemap": ROOT/"docs"/"travel-finds"/"sitemap.xml", "prefix": "https://valdislavn-spec.github.io/content-factory/travel-finds/", "key_location": f"https://valdislavn-spec.github.io/content-factory/{KEY}.txt"},
    {"host": "ofertas-finds.deed.page", "sitemap": ROOT/"build"/"deals"/"sitemap.xml", "prefix": "https://ofertas-finds.deed.page/", "key_location": f"https://ofertas-finds.deed.page/{KEY}.txt"},
]
def main():
    dry = "--dry-run" in sys.argv
    for site in SITES:
        path = site["sitemap"]
        if not path.is_file():
            print(f"{site['host']}: sitemap missing")
            continue
        urls = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", path.read_text(encoding="utf-8", errors="replace"))
        urls = list(dict.fromkeys(u for u in urls if u.startswith(site["prefix"])))
        payload = {"host": site["host"], "key": KEY, "keyLocation": site["key_location"], "urlList": urls}
        print(f"{site['host']}: {len(urls)} URLs, keyLocation={site['key_location']}")
        if dry:
            continue
        req = urllib.request.Request("https://api.indexnow.org/indexnow", data=json.dumps(payload).encode(), method="POST", headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "content-factory-indexnow/2.0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                print(f"{site['host']}: HTTP {r.status}")
        except Exception as e:
            print(f"{site['host']}: ERROR {type(e).__name__}: {e}")
if __name__ == "__main__":
    raise SystemExit(main())
