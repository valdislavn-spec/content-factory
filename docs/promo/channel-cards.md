# Карточки Telegram-каналов (Pinterest-style) — публикация в Mastodon и другие сети

**Дата: 08.11.2026.** 6 карточек 1000×1500 (2:3, формат Pinterest): логотип
канала, язык/тема, крупный заголовок, описание, 3 пункта пользы, CTA
`t.me/<handle>` и travel-партнёрская ссылка с пометкой «Ad».

## Что где лежит

| Что | Где |
|---|---|
| PNG карточки | [docs/assets/channel-cards/](../assets/channel-cards/) — `crypto-news.png`, `ai-news.png`, `sport-news.png`, `crypto-es.png`, `tech-ai-es.png`, `futbol-es.png` |
| Манифест (подписи под каждую платформу) | `docs/assets/channel-cards/manifest.json` |
| Pinterest payload | `docs/assets/channel-cards/<channel>.json` |
| Генератор | [scripts/generate_channel_cards.py](../../scripts/generate_channel_cards.py) + [content_factory/channel_cards.py](../../content_factory/channel_cards.py) |
| Публикатор | [scripts/post_channel_cards.py](../../scripts/post_channel_cards.py) |
| Workflow | [.github/workflows/channel-cards.yml](../../.github/workflows/channel-cards.yml) |

Публичные URL: `https://raw.githubusercontent.com/valdislavn-spec/content-factory/main/docs/assets/channel-cards/<file>.png`
(Buffer/Pinterest/Tumblr берут картинку по URL; Mastodon/Akkoma загружают файл напрямую).

## Куда публикуется

| Платформа | Как | Что нужно |
|---|---|---|
| **Mastodon** (@amazing_Brave007) | `POST /api/v2/media` + `/api/v1/statuses` | `MASTODON_BASE_URL`, `MASTODON_TOKEN` |
| **Akkoma** (@hoopy0007) | те же endpoints | `AKKOMA_BASE_URL`, `AKKOMA_TOKEN` |
| **Buffer** (X / Bluesky / Facebook) | GraphQL `createPost` + `assets[image.url]`, в очередь | `BUFFER_API_KEY` |
| **Tumblr** | legacy photo post (`source`=URL) | `TUMBLR_*` (5 секретов) |
| **Pinterest** | `POST /v5/pins` (board авто-создаётся) | `PINTEREST_ACCESS_TOKEN` (+ опц. `PINTEREST_BOARD_ID`); сейчас токен возвращает 401 — нужен refresh |

Каждая подпись содержит:
- описание канала и 3 пункта;
- **ссылку на Telegram** (`t.me/...`);
- **travel-ссылку** (Aviasales/Airalo/Kiwitaxi/Yesim через трекер) + `Ad`;
- хэштеги (3).

Travel-ссылки ротируются по карточкам (см. `TRAVEL_OFFERS` в
`content_factory/channel_cards.py`), клики считаются
[трекером](../monetization/link-tracker.md).

## Запуск

```bash
# 1. Сгенерировать PNG + manifest (локально или в CI)
python scripts/generate_channel_cards.py

# 2. Dry-run: показать, что уйдёт (без публикации)
python scripts/post_channel_cards.py

# 3. Опубликовать во все сети, где есть креды
python scripts/post_channel_cards.py --live

# Только Mastodon + Akkoma, только EN-каналы
python scripts/post_channel_cards.py --live --platforms mastodon,akkoma --channels crypto-news,ai-news,sport-news
```

В GitHub: **Actions → channel-cards → Run workflow**:
- `publish: live` — публикация; `dry-run` — только генерация/коммит;
- `platforms` — список сетей; `channels` — подмножество каналов;
- `commit_cards: true` — PNG/JSON коммитятся в `docs/assets/channel-cards`
  (нужно, чтобы публичные URL картинок работали для Buffer/Pinterest/Tumblr).

## Ограничения

- Mastodon/Akkoma требуют описательный `User-Agent` и лимит 500 символов —
  подписи укладываются в 480.
- Mastodon.social может резать новые аккаунты с внешними ссылками
  (`MASTODON_NO_LINKS=1`) — для карточек ссылки нужны, поэтому публикуем с
  основного аккаунта, где это разрешено.
- Pinterest API требует scope `pins:write` (+ `boards:read/write` для
  авто-создания доски); без него платформа пропускается с ошибкой в отчёте.
- Не публиковать все 6 карточек повторно слишком часто: это промо-серия, а не
  ежедневный контент. Ротация/повтор — не чаще 1 раза в месяц.
- Отчёт: `data/reports/channel-cards-post-<timestamp>.json`, артефакт workflow.
