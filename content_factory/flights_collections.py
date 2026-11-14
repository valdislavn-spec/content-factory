"""Подборки дешёвых билетов: витрины /flights/* → тематические страницы и посты.

Идея в том, что уже собранные данные Авиасейлс (страницы /flights/almaty/ и
/flights/minsk/, которые обновляет flights_digest.py) раскладываются по смыслу:
«до 15 000 ₽», «Турция», «Средняя Азия и Кавказ», «тёплые направления», «лучшее
из Алматы», «лучшее из Минска». На каждую подборку получается:

  * docs/collections/<slug>/index.html — страница с ценами, датами и партнёрскими
    ссылками (SEO: canonical, og, JSON-LD ItemList + BreadcrumbList);
  * docs/collections/index.html — хаб со всеми подборками;
  * data/outbox/collections/<slug>.html — готовый пост для Telegram (HTML);
  * data/collections/latest.json — снимок для отчётов.

Модуль не ходит в сеть: источник данных — уже отрендеренные страницы, поэтому
подборки обновляются в том же workflow, что и сами витрины.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence

from content_factory import flights_geo as geo

PUBLIC = "https://valdislavn-spec.github.io/content-factory"
AVIASALES_CTA = "https://aviasales.tpk.ro/b3PI8GVN"
TELEGRAM_LIMIT = 4096

ORIGINS: Dict[str, Dict[str, str]] = {
    "ALA": {"slug": "almaty", "name": "Алматы", "country": "KZ", "prefix": "из Алматы"},
    "MSQ": {"slug": "minsk", "name": "Минск", "country": "BY", "prefix": "из Минска"},
}

MONTHS_RU = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
MONTHS_SHORT = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


@dataclass(frozen=True)
class Deal:
    origin: str
    dest: str
    price: int
    dep: Optional[date]
    ret: Optional[date]
    airline: str
    link: str

    @property
    def city(self) -> str:
        return geo.city_name(self.dest, "ru")

    @property
    def country(self) -> str:
        return geo.city(self.dest).country

    @property
    def tags(self):
        return geo.city(self.dest).tags

    @property
    def nights(self) -> int:
        if not self.dep or not self.ret:
            return 0
        return max(0, (self.ret - self.dep).days)

    @property
    def price_text(self) -> str:
        return money(self.price)

    @property
    def route(self) -> str:
        return "%s → %s" % (ORIGINS.get(self.origin, {}).get("name", self.origin), self.city)


@dataclass
class Collection:
    slug: str
    title: str
    lead: str
    emoji: str
    deals: List[Deal] = field(default_factory=list)
    seo: str = ""

    @property
    def count(self) -> int:
        return len(self.deals)

    @property
    def cheapest(self) -> int:
        return min((d.price for d in self.deals), default=0)


# ---------------------------------------------------------------------------
# Форматирование
# ---------------------------------------------------------------------------
def money(value: int) -> str:
    return "{:,}".format(int(value)).replace(",", " ") + " ₽"


def plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def directions(n: int) -> str:
    """«1 направление», «3 направления», «7 направлений»."""
    return "%d %s" % (n, plural(n, "направление", "направления", "направлений"))


def fmt_date(value: Optional[date], short: bool = False) -> str:
    if not value:
        return "—"
    months = MONTHS_SHORT if short else MONTHS_RU
    return "%d %s" % (value.day, months[value.month - 1])


def fmt_dates(dep: Optional[date], ret: Optional[date], short: bool = False) -> str:
    """8–16 февраля · 27 января – 2 февраля · 27 ноября (туда-обратно в один день)."""
    if not dep:
        return "даты уточняются"
    if not ret or ret == dep:
        return fmt_date(dep, short)
    if dep.month == ret.month:
        months = MONTHS_SHORT if short else MONTHS_RU
        return "%d–%d %s" % (dep.day, ret.day, months[ret.month - 1])
    return "%s – %s" % (fmt_date(dep, short), fmt_date(ret, short))


def fmt_updated(updated: Optional[datetime], short: bool = False) -> str:
    if not updated:
        return "сегодня"
    if short:
        return "%d %s" % (updated.day, MONTHS_RU[updated.month - 1])
    return "%d %s %d, %02d:%02d UTC" % (
        updated.day, MONTHS_RU[updated.month - 1], updated.year, updated.hour, updated.minute,
    )


def _esc(value: str) -> str:
    return html.escape(str(value), quote=True)


# ---------------------------------------------------------------------------
# Разбор витрин
# ---------------------------------------------------------------------------
ROW_RE = re.compile(
    r"<tr>\s*<td[^>]*>(?P<city>.*?)</td>\s*"
    r"<td[^>]*>(?P<dates>.*?)</td>\s*"
    r"<td[^>]*>(?P<airline>.*?)</td>\s*"
    r"<td[^>]*>(?P<price>.*?)</td>\s*"
    r"<td[^>]*><a href=\"(?P<link>[^\"]+)\"",
    re.S,
)
TAG_RE = re.compile(r"<[^>]+>")
CODE_RE = re.compile(r"\(([A-Z]{3})\)")
PRICE_RE = re.compile(r"([\d\u00a0\s]+)\s*₽")
UPDATED_RE = re.compile(r"Updated\s+(\d{1,2})\s+(\w{3})\s+(\d{4}),?\s+(\d{2}):(\d{2})\s*UTC")


def _text(chunk: str) -> str:
    return html.unescape(TAG_RE.sub(" ", chunk)).strip()


def parse_updated(page: str) -> Optional[datetime]:
    match = UPDATED_RE.search(page)
    if not match:
        return None
    day, mon, year, hour, minute = match.groups()
    months = {m.lower(): i + 1 for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}
    month = months.get(mon.lower()[:3])
    if not month:
        return None
    try:
        return datetime(int(year), month, int(day), int(hour), int(minute))
    except ValueError:
        return None


def parse_page(page: str, origin: str) -> List[Deal]:
    """Достаёт сделки из отрендеренной страницы /flights/<slug>/."""
    deals: List[Deal] = []
    for match in ROW_RE.finditer(page):
        city_text = _text(match.group("city"))
        code_match = CODE_RE.search(city_text)
        dest = code_match.group(1) if code_match else city_text.split()[0].upper()
        price_match = PRICE_RE.search(_text(match.group("price")))
        if not price_match:
            continue
        price = int(re.sub(r"\D", "", price_match.group(1)) or 0)
        if price <= 0 or not dest:
            continue
        dates = _text(match.group("dates"))
        dep, ret = _parse_dates(dates)
        deals.append(Deal(
            origin=origin,
            dest=dest.upper(),
            price=price,
            dep=dep,
            ret=ret,
            airline=_text(match.group("airline")),
            link=match.group("link"),
        ))
    return deals


DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _parse_dates(text: str):
    found = DATE_RE.findall(text)
    values = []
    for year, month, day in found[:2]:
        try:
            values.append(date(int(year), int(month), int(day)))
        except ValueError:
            continue
    if not values:
        return None, None
    return values[0], (values[1] if len(values) > 1 else None)


def load_deals(docs_dir: Path) -> List[Deal]:
    """Читает все известные витрины. Отсутствующие страницы просто пропускает."""
    deals: List[Deal] = []
    for origin, meta in ORIGINS.items():
        page_path = Path(docs_dir) / "flights" / meta["slug"] / "index.html"
        if not page_path.exists():
            continue
        deals.extend(parse_page(page_path.read_text(encoding="utf-8"), origin))
    return deals


def page_updated(docs_dir: Path) -> Optional[datetime]:
    stamps = []
    for meta in ORIGINS.values():
        page_path = Path(docs_dir) / "flights" / meta["slug"] / "index.html"
        if not page_path.exists():
            continue
        stamp = parse_updated(page_path.read_text(encoding="utf-8"))
        if stamp:
            stamps.append(stamp)
    return max(stamps) if stamps else None


# ---------------------------------------------------------------------------
# Правила подборок
# ---------------------------------------------------------------------------
CIS_ASIA = {"UZ", "TJ", "KG", "TM"}
CAUCASUS = {"AZ", "AM", "GE"}


@dataclass(frozen=True)
class Spec:
    slug: str
    title: str
    lead: str
    emoji: str
    match: Callable[[Deal], bool]
    limit: int = 6
    seo: str = ""
    min_deals: Optional[int] = None
    dedupe: bool = True


SPECS: Sequence[Spec] = (
    Spec(
        "do-15-000",
        "Билеты до 15 000 ₽",
        "Самые дешёвые перелёты из Алматы и Минска: только цены, которые реально найти.",
        "💸",
        lambda d: d.price <= 15000,
        limit=8,
        seo="Дешёвые билеты до 15 000 ₽ из Алматы и Минска",
    ),
    Spec(
        "teplye-napravleniya",
        "Тёплые направления",
        "Где зимой море и +20: Турция, ОАЭ, Египет, Юго-Восточная Азия.",
        "🌴",
        lambda d: "warm" in d.tags,
        min_deals=2,
    ),
    Spec(
        "turciya",
        "Турция",
        "Стамбул, Измир, Анталья — четыре часа в воздухе, без визы для Казахстана и Беларуси.",
        "🇹🇷",
        lambda d: d.country == "TR",
    ),
    Spec(
        "srednyaya-aziya",
        "Средняя Азия и Кавказ",
        "Ташкент, Душанбе, Баку, Ереван, Батуми — рядом, без визы, чаще всего без пересадок.",
        "🏔",
        lambda d: d.country in CIS_ASIA | CAUCASUS,
    ),
    Spec(
        "po-kazahstanu",
        "По Казахстану",
        "Шымкент, Актау, Актобе, Атырау: внутренние перелёты дешевле, чем кажется.",
        "🇰🇿",
        lambda d: d.country == "KZ" and d.origin == "ALA",
    ),
    Spec(
        "na-nedelyu",
        "На неделю и дольше",
        "Перелёты, где выходит семь и больше ночей: отпуск, а не выходные.",
        "🧳",
        lambda d: d.nights >= 7,
        dedupe=True,
    ),
)


def build_collections(deals: Iterable[Deal], min_deals: int = 3) -> List[Collection]:
    """Раскладывает сделки по подборкам: без дублей городов, без пустых страниц."""
    pool = [d for d in deals if d.price > 0]
    result: List[Collection] = []
    for spec in SPECS:
        picked = sorted((d for d in pool if spec.match(d)), key=lambda d: (d.price, d.dest))
        if spec.dedupe:
            seen, unique = set(), []
            for deal in picked:
                if deal.city in seen:
                    continue
                seen.add(deal.city)
                unique.append(deal)
            picked = unique
        picked = picked[: spec.limit]
        if len(picked) >= (spec.min_deals or min_deals):
            result.append(Collection(slug=spec.slug, title=spec.title, lead=spec.lead,
                                     emoji=spec.emoji, deals=picked, seo=spec.seo))
    return result


# ---------------------------------------------------------------------------
# Рендер страниц
# ---------------------------------------------------------------------------
def _nav(public: str) -> str:
    return (
        '<p style="margin:0 0 18px">'
        f'<a href="{public}/" style="color:#2563eb;text-decoration:none">← Все каналы</a> · '
        f'<a href="{public}/flights/" style="color:#2563eb;text-decoration:none">Билеты</a> · '
        f'<a href="{public}/collections/" style="color:#2563eb;text-decoration:none">Все подборки</a></p>'
    )


def _deal_rows(col: Collection, public: str) -> str:
    rows = []
    for deal in col.deals:
        origin = ORIGINS.get(deal.origin, {})
        rows.append(
            "<tr>"
            '<td style="padding:10px 12px;border-bottom:1px solid #eef0f4">'
            f'<div style="font-weight:600">{_esc(deal.city)}</div>'
            f'<div style="color:#6b7280;font-size:12px">{origin.get("prefix", "из " + origin.get("name", ""))} · '
            f'{_esc(geo.country_name(deal.country))}</div></td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eef0f4;white-space:nowrap">'
            f'{_esc(fmt_dates(deal.dep, deal.ret))}'
            + (f'<div style="color:#6b7280;font-size:12px">{deal.nights} ноч.</div>' if deal.nights else "")
            + "</td>"
            f'<td style="padding:10px 12px;border-bottom:1px solid #eef0f4">{_esc(deal.airline)}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eef0f4;font-weight:600;white-space:nowrap">'
            f'{deal.price_text}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eef0f4">'
            f'<a href="{_esc(deal.link)}" style="color:#2563eb;text-decoration:none">Смотреть →</a></td>'
            "</tr>"
        )
    return "".join(rows)


def _cards(cols: Sequence[Collection], public: str, exclude: str = "") -> str:
    cards = []
    for col in cols:
        if col.slug == exclude:
            continue
        cards.append(
            f'<a href="{public}/collections/{col.slug}/" style="display:block;padding:16px 18px;'
            'border:1px solid #e5e7eb;border-radius:14px;text-decoration:none;color:#111;margin:0 0 12px">'
            f'<div style="font-size:17px;font-weight:600;margin-bottom:4px">{col.emoji} {_esc(col.title)}</div>'
            f'<div style="color:#6b7280;font-size:14px">{directions(col.count)} · от {money(col.cheapest)}</div>'
            "</a>"
        )
    return "".join(cards)


def render_page(col: Collection, cols: Sequence[Collection], updated: Optional[datetime],
                public: str = PUBLIC) -> str:
    title = "%s | Content Factory" % (col.seo or ("%s — дешёвые билеты" % col.title))
    description = ("%s %s, цены от %s. Обновлено %s." % (
        col.lead, directions(col.count), money(col.cheapest), fmt_updated(updated)))[:300]
    schema = json.dumps({
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "ItemList",
                "name": col.title,
                "url": "%s/collections/%s/" % (public, col.slug),
                "numberOfItems": col.count,
                "itemListElement": [
                    {"@type": "ListItem", "position": i + 1, "name": d.route,
                     "url": d.link, "offers": {"@type": "Offer", "price": d.price, "priceCurrency": "RUB"}}
                    for i, d in enumerate(col.deals)
                ],
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Главная", "item": public + "/"},
                    {"@type": "ListItem", "position": 2, "name": "Билеты", "item": public + "/flights/"},
                    {"@type": "ListItem", "position": 3, "name": "Подборки", "item": public + "/collections/"},
                    {"@type": "ListItem", "position": 4, "name": col.title,
                     "item": "%s/collections/%s/" % (public, col.slug)},
                ],
            },
        ],
    }, ensure_ascii=False)

    return "\n".join([
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_esc(title)}</title>",
        f'<meta name="description" content="{_esc(description)}">',
        f'<link rel="canonical" href="{public}/collections/{col.slug}/">',
        '<meta property="og:type" content="article">',
        f'<meta property="og:title" content="{_esc(col.title)} — дешёвые билеты">',
        f'<meta property="og:description" content="{_esc(description)}">',
        f'<meta property="og:url" content="{public}/collections/{col.slug}/">',
        f'<script type="application/ld+json">{schema}</script>',
        "</head>",
        '<body style="margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'color:#111;background:#fff">',
        '<div style="max-width:880px;margin:0 auto;padding:32px 20px 60px">',
        _nav(public),
        '<p style="color:#6b7280;font-size:13px;text-transform:uppercase;letter-spacing:.08em;margin:0 0 8px">'
        "Подборка · дешёвые билеты</p>",
        f'<h1 style="font-size:32px;margin:0 0 10px">{col.emoji} {_esc(col.title)}</h1>',
        f'<p style="font-size:17px;color:#374151;margin:0 0 10px">{_esc(col.lead)}</p>',
        f'<p style="color:#6b7280;margin:0 0 22px">{directions(col.count)} · от {money(col.cheapest)} · '
        f"обновлено {fmt_updated(updated)} · цены в ₽ за перелёт туда-обратно</p>",
        '<table style="width:100%;border-collapse:collapse;font-size:15px">',
        '<thead><tr style="text-align:left;color:#6b7280;font-size:13px;text-transform:uppercase">'
        '<th style="padding:8px 12px">Направление</th><th style="padding:8px 12px">Даты</th>'
        '<th style="padding:8px 12px">Авиакомпания</th><th style="padding:8px 12px">Цена</th>'
        '<th style="padding:8px 12px"></th></tr></thead>',
        "<tbody>" + _deal_rows(col, public) + "</tbody></table>",
        f'<p style="margin:24px 0 6px"><a href="{AVIASALES_CTA}" style="display:inline-block;'
        'background:#f59e0b;color:#111;font-weight:600;padding:12px 20px;border-radius:100px;'
        'text-decoration:none">Проверить все билеты →</a></p>',
        '<p style="color:#6b7280;font-size:13px">Реклама · партнёрские ссылки. Цены меняются '
        "быстро; финальная цена — на странице бронирования.</p>",
        f'<p style="font-size:14px;color:#374151;margin-top:22px">Свежие цены по городам: '
        f'<a href="{public}/flights/almaty/" style="color:#2563eb;text-decoration:none">из Алматы</a> · '
        f'<a href="{public}/flights/minsk/" style="color:#2563eb;text-decoration:none">из Минска</a> · '
        f'<a href="{public}/tours/" style="color:#2563eb;text-decoration:none">пакетные туры</a></p>',
        '<h2 style="font-size:22px;margin:30px 0 14px">Другие подборки</h2>',
        _cards(cols, public, exclude=col.slug),
        f'<p style="font-size:13px;color:#6b7280;margin-top:26px">© Content Factory · '
        f'<a href="{public}/privacy.html" style="color:#6b7280">Политика</a> · '
        f'<a href="{public}/terms.html" style="color:#6b7280">Условия</a></p>',
        "</div></body></html>",
    ])


def render_hub(cols: Sequence[Collection], updated: Optional[datetime],
               public: str = PUBLIC) -> str:
    cheapest = min((c.cheapest for c in cols), default=0)
    description = ("Готовые подборки дешёвых билетов из Алматы и Минска: тёплые направления, "
                   "Турция, Средняя Азия, до 15 000 ₽. Обновляется каждый день.")
    return "\n".join([
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Подборки дешёвых билетов из Алматы и Минска | Content Factory</title>",
        f'<meta name="description" content="{_esc(description)}">',
        f'<link rel="canonical" href="{public}/collections/">',
        '<meta property="og:type" content="website">',
        '<meta property="og:title" content="Подборки дешёвых билетов">',
        f'<meta property="og:description" content="{_esc(description)}">',
        f'<meta property="og:url" content="{public}/collections/">',
        "</head>",
        '<body style="margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'color:#111;background:#fff">',
        '<div style="max-width:880px;margin:0 auto;padding:32px 20px 60px">',
        _nav(public),
        '<p style="color:#6b7280;font-size:13px;text-transform:uppercase;letter-spacing:.08em;margin:0 0 8px">'
        "Подборки</p>",
        '<h1 style="font-size:32px;margin:0 0 10px">Подборки дешёвых билетов</h1>',
        f'<p style="color:#6b7280;margin:0 0 24px">'
        f'{len(cols)} {plural(len(cols), "подборка", "подборки", "подборок")} · цены от {money(cheapest)} · '
        f"обновлено {fmt_updated(updated)}. Собраны из живых цен Авиасейлс по Алматы и Минску.</p>",
        _cards(cols, public),
        f'<p style="font-size:14px;color:#374151;margin-top:18px">Полные таблицы по городам: '
        f'<a href="{public}/flights/almaty/" style="color:#2563eb;text-decoration:none">из Алматы</a> · '
        f'<a href="{public}/flights/minsk/" style="color:#2563eb;text-decoration:none">из Минска</a> · '
        f'<a href="{public}/tours/" style="color:#2563eb;text-decoration:none">туры</a></p>',
        '<p style="color:#6b7280;font-size:13px;margin-top:8px">Реклама · партнёрские ссылки. '
        "Цены меняются быстро.</p>",
        f'<p style="font-size:13px;color:#6b7280;margin-top:22px">© Content Factory · '
        f'<a href="{public}/privacy.html" style="color:#6b7280">Политика</a> · '
        f'<a href="{public}/terms.html" style="color:#6b7280">Условия</a></p>',
        "</div></body></html>",
    ])


def render_post(col: Collection, updated: Optional[datetime], public: str = PUBLIC,
                limit: int = 5) -> str:
    """Пост для Telegram в HTML-разметке (parse_mode=HTML)."""
    deals = col.deals[:limit]
    lines = [
        f"{col.emoji} <b>{_esc(col.title)}</b>",
        f"<i>{directions(col.count)} · обновлено {fmt_updated(updated, short=True)}</i>",
        "",
    ]
    for deal in deals:
        nights = f" · {deal.nights} ноч." if deal.nights else ""
        lines.append(
            f'• <a href="{_esc(deal.link)}">{_esc(deal.city)}</a> — <b>{deal.price_text}</b>'
            f" · {_esc(fmt_dates(deal.dep, deal.ret, short=True))}{nights}"
        )
    lines += [
        "",
        f'👉 <a href="{public}/collections/{col.slug}/">Вся подборка</a> · '
        f'<a href="{AVIASALES_CTA}">Найти дешевле</a>',
        "#реклама",
    ]
    text = "\n".join(lines)
    while len(text) > TELEGRAM_LIMIT and len(deals) > 1:
        deals = deals[:-1]
        text = render_post(Collection(col.slug, col.title, col.lead, col.emoji, deals, col.seo),
                           updated, public, limit=len(deals))
    return text


# ---------------------------------------------------------------------------
# Запись результатов
# ---------------------------------------------------------------------------
def write_site(out_dir: Path, cols: Sequence[Collection], updated: Optional[datetime],
               public: str = PUBLIC, clean_stale: bool = True) -> List[Path]:
    """Пишет хаб и страницы подборок. Удаляет страницы, которых больше нет в наборе."""
    out_dir = Path(out_dir)
    written: List[Path] = []
    hub = out_dir / "index.html"
    hub.parent.mkdir(parents=True, exist_ok=True)
    hub.write_text(render_hub(cols, updated, public), encoding="utf-8")
    written.append(hub)
    keep = {col.slug for col in cols}
    if clean_stale:
        for child in sorted(out_dir.iterdir()):
            if child.is_dir() and child.name not in keep and (child / "index.html").exists():
                (child / "index.html").unlink()
                if not any(child.iterdir()):
                    child.rmdir()
    for col in cols:
        target = out_dir / col.slug / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_page(col, cols, updated, public), encoding="utf-8")
        written.append(target)
    return written


def write_posts(out_dir: Path, cols: Sequence[Collection], updated: Optional[datetime],
                public: str = PUBLIC) -> List[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    for col in cols:
        target = out_dir / ("%s.html" % col.slug)
        target.write_text(render_post(col, updated, public), encoding="utf-8")
        written.append(target)
    return written


def write_snapshot(path: Path, cols: Sequence[Collection], updated: Optional[datetime]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated": updated.isoformat(timespec="minutes") if updated else "",
        "collections": [
            {
                "slug": c.slug,
                "title": c.title,
                "count": c.count,
                "cheapest": c.cheapest,
                "deals": [
                    {"origin": d.origin, "dest": d.dest, "city": d.city, "price": d.price,
                     "dep": d.dep.isoformat() if d.dep else "", "ret": d.ret.isoformat() if d.ret else "",
                     "airline": d.airline, "link": d.link}
                    for d in c.deals
                ],
            }
            for c in cols
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def sitemap_urls(cols: Sequence[Collection], public: str = PUBLIC) -> List[str]:
    return [public + "/collections/"] + ["%s/collections/%s/" % (public, c.slug) for c in cols]


def update_sitemap(path: Path, urls: Sequence[str], today: Optional[date] = None,
                   prune_prefix: str = "") -> int:
    """Дописывает недостающие адреса и убирает устаревшие подборки.

    prune_prefix — префикс адресов, которые считаются «нашими»: если адрес с этим
    префиксом есть в sitemap, но не передан в urls, он удаляется.
    """
    path = Path(path)
    if not path.exists():
        return 0
    xml = path.read_text(encoding="utf-8")
    stamp = (today or date.today()).isoformat()
    removed = 0
    if prune_prefix:
        for block in re.findall(r"  <url>.*?</url>\n?", xml, re.S):
            loc = re.search(r"<loc>(.*?)</loc>", block)
            if not loc or not loc.group(1).startswith(prune_prefix):
                continue
            if loc.group(1) in urls:
                continue
            xml = xml.replace(block, "")
            removed += 1
    added = 0
    for url in urls:
        if "<loc>%s</loc>" % url in xml:
            continue
        entry = (
            "  <url>\n"
            "    <loc>%s</loc>\n"
            "    <lastmod>%s</lastmod>\n"
            "    <changefreq>daily</changefreq>\n"
            "    <priority>0.8</priority>\n"
            "  </url>\n" % (url, stamp)
        )
        xml = xml.replace("</urlset>", entry + "</urlset>")
        added += 1
    if added or removed:
        path.write_text(xml, encoding="utf-8")
    return added
