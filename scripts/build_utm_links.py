"""Build UTM-tagged distribution links for public landing pages."""
from __future__ import annotations
import csv, re, urllib.parse
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "marketing"
SITEMAPS = [ROOT/"docs"/"sitemap.xml", ROOT/"docs"/"travel-finds"/"sitemap.xml", ROOT/"build"/"deals"/"sitemap.xml"]
SOURCES = [("telegram","social"),("pinterest","social"),("email","newsletter"),("x","social"),("reddit","social"),("tiktok","bio"),("facebook","social"),("vk","social"),("dzen","social")]
EXTRA_PAGES = ["https://travel-finds.surge.sh/","https://travel-finds.surge.sh/es.html","https://ofertas-finds.deed.page/","https://valdislavn-spec.github.io/seller-launch-kit/","https://erpsas-seller-launch-kit.static.hf.space/"]

def campaign_for(url):
    p = urllib.parse.urlparse(url)
    path = p.path.strip("/")
    if not path or path == "content-factory":
        return "home"
    path = path.removeprefix("content-factory/")
    slug = re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")
    return slug or "home"

def tagged(url, source, medium):
    p = urllib.parse.urlparse(url)
    q = urllib.parse.parse_qs(p.query, keep_blank_values=True)
    q["utm_source"] = [source]
    q["utm_medium"] = [medium]
    q["utm_campaign"] = [campaign_for(url)]
    q["utm_content"] = ["organic"]
    return urllib.parse.urlunparse(p._replace(query=urllib.parse.urlencode(q, doseq=True)))

def main():
    urls = []
    for sitemap in SITEMAPS:
        if sitemap.is_file():
            text = sitemap.read_text(encoding="utf-8", errors="replace")
            urls += re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text)
    urls += EXTRA_PAGES
    urls = list(dict.fromkeys(urls))
    rows = []
    for url in urls:
        for source, medium in SOURCES:
            rows.append({"page":url,"campaign":campaign_for(url),"source":source,"medium":medium,"utm_url":tagged(url,source,medium)})
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT/"utm-links.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["page","campaign","source","medium","utm_url"])
        w.writeheader(); w.writerows(rows)
    priority = [u for u in urls if any(k in u for k in ("flight-hotel-us","flight-hotel-abroad","travel-finds.surge.sh","ofertas-finds.deed.page","/travel/","/destinations/","/resorts/","/compare/","/collections/en/"))]
    lines = ["# UTM links — Content Factory","",f"Сгенерировано для **{len(urls)} страниц** и **{len(SOURCES)} источников**.",f"Полная таблица: [`utm-links.csv`](utm-links.csv) ({len(rows)} строк).","","## Быстрая шпаргалка","","| Страница | Telegram | Pinterest | Email |","|---|---|---|---|"]
    for url in priority[:30]:
        lines.append("| {page} | [TG]({tg}) | [Pin]({pin}) | [Email]({email}) |".format(page=url.replace("https://",""),tg=tagged(url,"telegram","social"),pin=tagged(url,"pinterest","social"),email=tagged(url,"email","newsletter")))
    lines += ["","## Правила","","- UTM ставим на URL лендинга, не на партнёрскую ссылку `/r/...`.","- `utm_campaign` — стабильный slug страницы; не меняем между постами.","- Один пост/пин = один `utm_source` и один `utm_content` (при необходимости `post1`, `pin03`).","- Для партнёрских переходов отдельно смотрим отчёты Travelpayouts."]
    (OUT/"utm-links.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(f"pages={len(urls)} rows={len(rows)}")

if __name__ == "__main__":
    raise SystemExit(main())
