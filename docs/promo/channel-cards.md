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

## Опубликовано 08.11.2026

**Mastodon** (@amazing_Brave007) — 6 постов с картинками; из-за фильтра
mastodon.social для новых аккаунтов подписи без внешних ссылок (ссылки видны
на карточке):
- Crypto: https://mastodon.social/@amazing_Brave007/117582993196830122
- AI: https://mastodon.social/@amazing_Brave007/117582993318079174
- US Sports: https://mastodon.social/@amazing_Brave007/117582993395781914
- Cripto ES: https://mastodon.social/@amazing_Brave007/117582993538437325
- IA ES: https://mastodon.social/@amazing_Brave007/117582993625823334
- Deporte ES: https://mastodon.social/@amazing_Brave007/117582993715244517

**Akkoma** (@hoopy0007@nuages.cloud) — 6 постов с картинками и кликабельными
ссылками (Telegram + travel):
- https://nuages.cloud/notice/BCFdGuYMySRflkLAeG
- https://nuages.cloud/notice/BCFdH2sA2l1vZRf5bk
- https://nuages.cloud/notice/BCFdH9hmdjt8lHrOu8
- https://nuages.cloud/notice/BCFdHGeUoMPyJ7NNFg
- https://nuages.cloud/notice/BCFdHMg8PBIGzwBldg
- https://nuages.cloud/notice/BCFdHUhqYhPttZ3FQ0

**Tumblr** (vlad-007) — 6 photo-постов:
- https://vlad-007.tumblr.com/post/832751744479084544
- https://vlad-007.tumblr.com/post/832751745770946560
- https://vlad-007.tumblr.com/post/832751746591883264
- https://vlad-007.tumblr.com/post/832751747741188096
- https://vlad-007.tumblr.com/post/832751748550721536
- https://vlad-007.tumblr.com/post/832751749550997505

**Buffer** — 18 постов в очереди (6 Bluesky, 6 X, 6 Facebook), разойдутся по
слотам Buffer; картинки берутся с публичных URL, текст адаптирован под лимиты.

**Pinterest** — API пока недоступен: приложение Depseek007 на trial-ревью,
токены read-only и API отвечает `401 code 3`. 09.11.2026 6 пинов загружены
**через Business Hub → Массовое создание пинов** (CSV) в доску Travel ideas;
создание занимает ~2 часа. CSV: [pinterest-channel-cards.csv](../pinterest-channel-cards.csv).
После одобрения Trial/Production и scope `pins:write` включим API-постинг
workflow с `platforms: pinterest`.

![Crypto & Blockchain card](../assets/channel-cards/crypto-news.png)

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
- Mastodon.social режет новые аккаунты с внешними ссылками: по умолчанию для
  Mastodon публикуется подпись **без URL** (ссылки видны на карточке, в тексте —
  `@handle`). Для прогретого аккаунта включите `mastodon_links: 1` в workflow
  или `MASTODON_LINKS=1` локально.
- Pinterest API требует scope `pins:write` (+ `boards:read/write` для
  авто-создания доски); без него платформа пропускается с ошибкой в отчёте.
- Не публиковать все 6 карточек повторно слишком часто: это промо-серия, а не
  ежедневный контент. Ротация/повтор — не чаще 1 раза в месяц.
- Отчёт: `data/reports/channel-cards-post-<timestamp>.json`, артефакт workflow.
