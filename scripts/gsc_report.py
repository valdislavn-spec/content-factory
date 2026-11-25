#!/usr/bin/env python3
"""Google Search Console report for the content-factory properties (read-only).

Requires google-auth + requests (see .tools/gsc-venv in the workspace):
    python3 -m venv .tools/gsc-venv
    .tools/gsc-venv/bin/pip install google-auth requests
    .tools/gsc-venv/bin/python content-factory/scripts/gsc_report.py

Writes a Markdown report to content-factory/runs/gsc/REPORT-<date>.md plus JSON data.
Service account: tools/gcloud/persistent/google-sa.json.
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

WORKSPACE = Path(__file__).resolve().parents[2]
SA = Path(os.environ.get("GOOGLE_SA_JSON", WORKSPACE / "tools/gcloud/persistent/google-sa.json"))
OUT = Path(__file__).resolve().parents[1] / "runs" / "gsc"
PROJECT = "seo-mcp-cf-vd0ul"
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
INSPECT_URLS = {
    "https://valdislavn-spec.github.io/content-factory/": [
        "https://valdislavn-spec.github.io/content-factory/travel-finds/",
        "https://valdislavn-spec.github.io/content-factory/travel-finds/guides/us-esim.html",
        "https://valdislavn-spec.github.io/content-factory/travel-finds/guides/us-car-rental.html",
        "https://valdislavn-spec.github.io/content-factory/travel-finds/blog/how-to-find-cheap-flights-2026.html",
    ]
}
DAYS = 28
PREFIX = "https://valdislavn-spec.github.io/content-factory/"


def headers() -> dict[str, str]:
    creds = service_account.Credentials.from_service_account_file(str(SA), scopes=SCOPES)
    creds.refresh(Request())
    return {"Authorization": "Bearer " + creds.token, "x-goog-user-project": PROJECT}


def get(url: str, hdrs: dict) -> dict:
    resp = requests.get(url, headers=hdrs, timeout=30)
    return resp.json() if resp.content else {}


def post(url: str, hdrs: dict, body: dict) -> dict:
    resp = requests.post(url, headers=hdrs, json=body, timeout=30)
    try:
        return resp.json()
    except ValueError:
        return {"http": resp.status_code, "text": resp.text[:300]}


def short(url: str) -> str:
    return (url or "—").replace(PREFIX, "/")


def main() -> int:
    hdrs = headers()
    sites = get("https://www.googleapis.com/webmasters/v3/sites", hdrs).get("siteEntry") or []
    end = date.today()
    start = end - timedelta(days=DAYS)
    data: dict = {"generated": end.isoformat(), "window": [start.isoformat(), end.isoformat()], "properties": {}}

    for entry in sites:
        site = entry.get("siteUrl", "")
        prop = {"permission": entry.get("permissionLevel"), "sitemaps": [], "queries": [], "pages": [], "inspection": []}
        quoted = requests.utils.quote(site, safe="")
        smaps = get("https://www.googleapis.com/webmasters/v3/sites/{s}/sitemaps".format(s=quoted), hdrs).get("sitemap") or []
        for smap in smaps:
            prop["sitemaps"].append({
                "path": smap.get("path"),
                "lastSubmitted": smap.get("lastSubmitted"),
                "lastDownloaded": smap.get("lastDownloaded"),
                "errors": smap.get("errors"),
                "warnings": smap.get("warnings"),
                "contents": smap.get("contents"),
            })
        for dims in (["query"], ["page"]):
            body = {"startDate": start.isoformat(), "endDate": end.isoformat(), "dimensions": dims, "rowLimit": 25}
            rows = post("https://www.googleapis.com/webmasters/v3/sites/{s}/searchAnalytics/query".format(s=quoted), hdrs, body).get("rows") or []
            prop["queries" if dims[0] == "query" else "pages"] = rows
        for page_url in INSPECT_URLS.get(site, []):
            result = post(
                "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",
                hdrs,
                {"inspectionUrl": page_url, "siteUrl": site},
            )
            status = ((result.get("inspectionResult") or {}).get("indexStatusResult") or {})
            prop["inspection"].append({
                "url": page_url,
                "verdict": status.get("verdict"),
                "coverageState": status.get("coverageState"),
                "crawledAs": status.get("crawledAs"),
                "lastCrawlTime": status.get("lastCrawlTime"),
                "googleCanonical": status.get("googleCanonical"),
                "userCanonical": status.get("userCanonical"),
            })
        data["properties"][site] = prop

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = end.isoformat()
    (OUT / "gsc-{d}.json".format(d=stamp)).write_text(
        json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    lines = [
        "# Google Search Console — отчёт {d}".format(d=stamp),
        "",
        "Окно данных: {a} → {b} (28 дней). Источник: Search Console API, service account (read-only).".format(
            a=start.isoformat(), b=end.isoformat()),
        "",
        "## Ресурсы",
        "",
        "| Ресурс | Роль | Запросов | Страниц | Sitemap |",
        "|---|---|---|---|---|",
    ]
    for site, prop in data["properties"].items():
        sitemaps = ", ".join((s["path"] or "").rsplit("/", 1)[-1] for s in prop["sitemaps"]) or "—"
        lines.append("| {s} | {r} | {q} | {p} | {sm} |".format(
            s=site, r=prop["permission"], q=len(prop["queries"]), p=len(prop["pages"]), sm=sitemaps))

    for site, prop in data["properties"].items():
        lines += ["", "## " + site, ""]
        if prop["sitemaps"]:
            for smap in prop["sitemaps"]:
                contents = smap.get("contents") or []
                submitted = sum(int(c.get("submitted") or 0) for c in contents)
                indexed = sum(int(c.get("indexed") or 0) for c in contents) if any("indexed" in c for c in contents) else ""
                lines.append("- sitemap {p}: отправлен {ls}, скачан {ld}, ошибок {e}, предупреждений {w}".format(
                    p=smap["path"], ls=smap["lastSubmitted"], ld=smap["lastDownloaded"],
                    e=(smap["errors"] or 0), w=(smap["warnings"] or 0)))
                lines.append("  - URLs в sitemap: {n}{idx}".format(
                    n=submitted, idx=(", проиндексировано " + str(indexed)) if indexed != "" else ""))
        else:
            lines.append("- sitemap не отправлен")
        if prop["queries"]:
            lines += ["", "**Запросы (топ):**", "", "| Запрос | Клики | Показы | CTR | Позиция |", "|---|---|---|---|---|"]
            for row in prop["queries"][:10]:
                key = (row.get("keys") or [""])[0]
                lines.append("| {k} | {c} | {i} | {ctr:.1%} | {p:.1f} |".format(
                    k=key, c=int(row.get("clicks", 0)), i=int(row.get("impressions", 0)),
                    ctr=float(row.get("ctr", 0)), p=float(row.get("position", 0))))
        else:
            lines.append("- запросов в окне нет (нужно больше данных)")
        if prop["pages"]:
            lines += ["", "**Страницы (топ):**", "", "| URL | Клики | Показы | Позиция |", "|---|---|---|---|"]
            for row in prop["pages"][:10]:
                key = (row.get("keys") or [""])[0]
                lines.append("| {k} | {c} | {i} | {p:.1f} |".format(
                    k=short(key), c=int(row.get("clicks", 0)), i=int(row.get("impressions", 0)),
                    p=float(row.get("position", 0))))
        if prop["inspection"]:
            lines += ["", "**Индексация ключевых URL:**", "", "| URL | verdict | coverageState | Google canonical | user canonical |", "|---|---|---|---|---|"]
            for item in prop["inspection"]:
                lines.append("| {u} | {v} | {c} | {g} | {us} |".format(
                    u=short(item["url"]), v=item.get("verdict") or "—", c=item.get("coverageState") or "—",
                    g=short(item.get("googleCanonical")), us=short(item.get("userCanonical"))))

    report = OUT / "REPORT-{d}.md".format(d=stamp)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(report)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
