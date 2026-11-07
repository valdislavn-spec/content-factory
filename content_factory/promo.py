"""Пакет продвижения: карточки каналов для каталогов и ВП-аутрича.

Каталоги (TGStat, Telemetr, Tlgrm.eu, GramPedia, GruposTelegramLatAm) просят
короткое описание 120–200 символов, категорию и ключевые слова. Писать это
руками каждый раз лень и легко рассинхронизировать с конфигом каналов, поэтому
здесь карточки собираются программно: курируемые тексты по known-id каналов +
fallback на описание из ``channels.*.yaml``.

Результат — Markdown-пакет (``docs/promo/catalog-package.md``) и JSON
(``docs/promo/catalog-cards.json``); генерируются ``scripts/catalog_cards.py``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from .models import ChannelConfig

#: Курируемые описания 120–200 символов (лучше, чем описание канала как есть).
DESCRIPTIONS: Dict[str, str] = {
    "sport-news": (
        "NFL, NBA, MLB, NHL and college football: scores, trades, injuries and "
        "sharp analysis for US sports fans. Daily updates from trusted sources."
    ),
    "ai-news": (
        "AI for a US audience: model releases, products, policy and the companies "
        "building them. Clear, sourced updates — no hype."
    ),
    "crypto-news": (
        "US crypto news: Bitcoin, Ethereum, markets, regulation and blockchain. "
        "Daily coverage from CoinDesk, The Block, Decrypt, SEC and CFTC."
    ),
    "tech-ai-es": (
        "Inteligencia artificial en español: modelos, productos, empresas y "
        "políticas de IA. Resúmenes diarios de Hipertextual, La Nación y FayerWayer."
    ),
    "crypto-es": (
        "Cripto y blockchain en español: Bitcoin, Ethereum, mercados y regulación. "
        "Noticias diarias de CriptoNoticias, BeInCrypto y CriptoTendencia."
    ),
    "futbol-es": (
        "Deporte en español: fútbol, LaLiga, Liga MX, Argentina, MLS y Champions. "
        "Resultados, fichajes y análisis para aficionados."
    ),
}

#: Категории для каталогов (одна точная категория, как просят каталоги).
CATEGORIES: Dict[str, str] = {
    "sport-news": "Sports / Спорт",
    "ai-news": "Technology / AI / Технологии",
    "crypto-news": "Crypto / Blockchain / Криптовалюты",
    "tech-ai-es": "Tecnología / IA",
    "crypto-es": "Criptomonedas / Blockchain",
    "futbol-es": "Deportes / Fútbol",
}

KEYWORDS: Dict[str, List[str]] = {
    "sport-news": ["NFL", "NBA", "MLB", "NHL", "college football", "US sports"],
    "ai-news": ["AI", "OpenAI", "Anthropic", "LLM", "Nvidia", "AI policy"],
    "crypto-news": ["Bitcoin", "Ethereum", "crypto", "blockchain", "ETF", "regulation"],
    "tech-ai-es": [
        "inteligencia artificial",
        "IA",
        "tecnología",
        "innovación",
        "modelos",
        "empresas",
    ],
    "crypto-es": ["criptomonedas", "Bitcoin", "Ethereum", "blockchain", "regulación", "DeFi"],
    "futbol-es": ["fútbol", "LaLiga", "Liga MX", "Champions", "fichajes", "deportes"],
}

#: Легаси-хэштеги каналов (используются и в постах через config).
HASHTAGS: Dict[str, List[str]] = {
    "sport-news": ["#Sports", "#NFL", "#NBA"],
    "ai-news": ["#AI", "#ArtificialIntelligence", "#TechNews"],
    "crypto-news": ["#Bitcoin", "#Crypto", "#Blockchain"],
    "tech-ai-es": ["#Tecnología", "#IA", "#InteligenciaArtificial"],
    "crypto-es": ["#Bitcoin", "#Cripto", "#Blockchain"],
    "futbol-es": ["#Deportes", "#Fútbol", "#LaLiga"],
}

#: Куда добавлять канал. Порядок — по отдаче/простоте.
CATALOGS: List[Dict[str, str]] = [
    {
        "name": "TGStat",
        "url": "https://tgstat.com/",
        "action": "Кабинет → «Добавить канал» → ссылка t.me → категория и описание",
        "note": "бесплатная карточка, модерация; самая крупная база в RU/СНГ",
    },
    {
        "name": "Telemetr",
        "url": "https://telemetr.io/",
        "action": "Кабинет → «Добавить канал» → ссылка t.me → подтвердить владение",
        "note": "подтверждение через бота-верификатора; англоязычная аудитория тоже",
    },
    {
        "name": "Tlgrm.eu",
        "url": "https://tlgrm.eu/channels",
        "action": "«Add channel» → ссылка t.me → описание и категория",
        "note": "EN-каталог, хорошо индексируется поиском",
    },
    {
        "name": "GramPedia",
        "url": "https://t.me/Grampedia_bot",
        "action": "Запустить бота → /add → ссылка на канал",
        "note": "бесплатный бот-каталог, добавление за минуту",
    },
    {
        "name": "TelegramChannels.me",
        "url": "https://telegramchannels.me/",
        "action": "«Add channel» → ссылка t.me → описание",
        "note": "EN-каталог для US-аудитории",
    },
    {
        "name": "GruposTelegramLatAm",
        "url": "https://grupostelegramlatam.com/",
        "action": "Форма добавления канала → ссылка t.me",
        "note": "ES-каталог для ЛатАм — профильный для испанской ветки",
    },
]

#: Рекомендации по упаковке (и почему это важно) — попадают в Markdown-пакет.
PACKAGING_NOTES: List[str] = [
    "Ключевые слова важнее красоты: в описании канала должны быть 2–3 поисковых "
    "слова (например, «Bitcoin», «inteligencia artificial», «NFL»).",
    "Название канала — понятное и с темой, без «лучший канал» и эмодзи-мусора.",
    "Аватар и обложка — единый стиль сети; обложка читаема на телефоне.",
    "Контакт для рекламы/ВП: укажите @username владельца в описании или "
    "закрепе — без контакта входящие предложения теряются.",
]

#: Легаси-хэндлы: @username не отражает тему → хуже поиск и доверие.
USERNAME_NOTES: List[Dict[str, str]] = [
    {"channel": "crypto-news", "current": "HOOPY0007", "suggested": "CryptoBlockchainUS"},
    {"channel": "ai-news", "current": "AINEWS0007", "suggested": "AINewsUS"},
    {"channel": "sport-news", "current": "SPORTNews0007", "suggested": "USSportsDaily"},
    {"channel": "tech-ai-es", "current": "WORLDNews0007", "suggested": "IAenEspanol"},
    {"channel": "crypto-es", "current": "TechnologiesNews01", "suggested": "CriptoEspanol"},
    {"channel": "futbol-es", "current": "SPORTSAnalytics007", "suggested": "DeporteEspanol"},
]


def channel_url(username: str) -> str:
    return "https://t.me/" + username.lstrip("@") if username else ""


def _normalize(value: Optional[str]) -> str:
    return " ".join(str(value or "").split())


def build_cards(
    channels: Sequence[ChannelConfig],
    usernames: Optional[Dict[str, str]] = None,
    *,
    contact: str = "@Novyi0007Bot",
) -> List[Dict[str, Any]]:
    """Собирает карточки каналов для каталогов.

    ``usernames`` — ``channel.id → @username`` (из data/analytics/growth/
    usernames.json). Для неизвестных каналов описание берётся из YAML.
    """
    usernames = usernames or {}
    cards: List[Dict[str, Any]] = []
    for channel in channels:
        username = usernames.get(channel.id, "")
        description = DESCRIPTIONS.get(channel.id) or _normalize(channel.description)
        if len(description) < 120:
            description = description + " " + " ".join(channel.topics[:5]).strip()
        if len(description) > 200:
            description = description[:197].rstrip() + "…"
        cards.append(
            {
                "id": channel.id,
                "title": channel.title,
                "username": username,
                "url": channel_url(username),
                "language": channel.language,
                "category": CATEGORIES.get(channel.id, "Новости и СМИ"),
                "description": description,
                "keywords": KEYWORDS.get(channel.id, list(channel.topics[:6])),
                "hashtags": HASHTAGS.get(channel.id, ["#" + channel.id]),
                "contact": contact,
            }
        )
    return cards


def cards_to_json(cards: Sequence[Dict[str, Any]], *, generated_at: Optional[str] = None) -> Dict[str, Any]:
    return {
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "channels": list(cards),
        "catalogs": CATALOGS,
    }


def cards_to_markdown(
    cards: Sequence[Dict[str, Any]],
    *,
    generated_at: Optional[str] = None,
    contact: str = "@Novyi0007Bot",
) -> str:
    """Готовый к копированию пакет: каталоги, карточки, рекомендации."""
    moment = generated_at or datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    lines: List[str] = [
        "# Пакет для каталогов — {} каналов".format(len(cards)),
        "",
        "Сгенерировано: {}. Контакт: `{}`.".format(moment, contact),
        "",
        "## Куда добавлять",
        "",
        "| Каталог | Ссылка | Что делать | Примечание |",
        "|---|---|---|---|",
    ]
    for catalog in CATALOGS:
        lines.append(
            "| {name} | [{url}]({url}) | {action} | {note} |".format(**catalog)
        )
    lines += ["", "Чек-лист: добавь каждый канал во все 6 каталогов, отметь галочкой.", ""]
    for catalog in CATALOGS:
        lines.append("- [ ] {}".format(catalog["name"]))
    lines += ["", "## Карточки каналов", ""]
    for card in cards:
        lines += [
            "### {} ({})".format(card["title"], card["language"].upper()),
            "",
            "- **Канал:** [@{}]({})".format(card["username"], card["url"]) if card["username"] else "- **Канал:** (username не найден)",
            "- **Категория:** {}".format(card["category"]),
            "- **Описание (120–200):** {}".format(card["description"]),
            "- **Ключевые слова:** {}".format(", ".join(card["keywords"])),
            "- **Хэштеги:** {}".format(", ".join(card["hashtags"])),
            "- **Контакт:** {}".format(card["contact"]),
            "",
        ]
    lines += ["## Рекомендации по упаковке", ""]
    lines += ["- " + note for note in PACKAGING_NOTES]
    lines += [
        "",
        "## Легаси-юзернеймы (опционально)",
        "",
        "Смена @username улучшает поиск и доверие, но ломает старые ссылки. "
        "Если меняете — обновите `config/cross_promo.yaml`, закрепы и интро-посты.",
        "",
        "| Канал | Сейчас | Предлагается |",
        "|---|---|---|",
    ]
    for note in USERNAME_NOTES:
        lines.append("| {} | @{} | @{} |".format(note["channel"], note["current"], note["suggested"]))
    lines += [
        "",
        "> Проверьте доступность нового @username в Telegram перед изменением.",
        "",
    ]
    return "\n".join(lines)
