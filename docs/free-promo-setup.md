# Бесплатное продвижение: что внедрено и как включить

**Статус:** внедрено 7 ноября 2026. Только для живых каналов **США (EN)** и
**ЛатАм (ES)** — RU-каналы из `config/channels.yaml` не затронуты.

Карта API и лимиты — в [free-promo-apis.md](free-promo-apis.md). Здесь — что уже
работает в коде, как заполнить `.env` и как проверить.

## Что внедрено

| Модуль | Что делает | Файл |
|---|---|---|
| Bluesky-публикатор | AT Protocol: `createSession` + `repo.createRecord`, app password, лимит ~1666 постов/ч | `content_factory/publishers/bluesky.py` |
| Mastodon-публикатор | `POST /api/v1/statuses` на любом инстансе, Bearer-токен | `content_factory/publishers/mastodon.py` |
| Discord-публикатор | webhook в **свой** сервер (30 сообщений/мин) | `content_factory/publishers/discord.py` |
| Кнопки в постах | «Подписаться» + «Поделиться» (`switch_inline_query`) под постом | `content_factory/publishers/telegram.py` |
| Growth-бот | deep links `?start=`, inline mode, запись событий в SQLite | `content_factory/integrations/telegram_growth.py`, `scripts/telegram-growth-bot.py` |
| Лендинг | 6 страниц каналов + index + sitemap (GitHub Pages) | `content_factory/integrations/landing.py`, `scripts/build_landing.py` |
| IndexNow | бесплатная индексация лендинга в Bing/Yandex/Seznam | `content_factory/integrations/indexnow.py`, `scripts/indexnow_ping.py` |
| CLI | `social-check`, `growth` | `content_factory/cli.py` |
| Хранилище | таблица `growth_events` + сводка | `content_factory/storage.py` |
| Тесты | 29 тестов по соцсетям/growth/лендингу | `tests/test_social_publishers.py`, `tests/test_telegram_growth.py`, `tests/test_landing_indexnow.py` |

**Как включается.** В `config/channels.en.yaml` и `config/channels.es.yaml` у всех
6 каналов теперь `publisher_ids: [telegram, bluesky, mastodon, discord]`.
Соцсети — опциональные: если креды не заданы, конвейер тихо пропускает их
(ошибки в публикации нет). Telegram работает как раньше.

## 1. Публикаторы соцсетей

Ключи — только в `.env` (gitignored). Для каждого канала можно задать свой аккаунт
суффиксом id: `AI_NEWS`, `CRYPTO_NEWS`, `SPORT_NEWS`, `TECH_AI_ES`, `CRYPTO_ES`, `FUTBOL_ES`.

### Bluesky (рекомендуется: бесплатно, без ревью, EN+ES)

1. Создайте аккаунт на [bsky.app](https://bsky.app) (bsky.social требует телефон).
2. Settings → **App Passwords** → создайте пароль (не основной пароль).
3. В `.env`:
   ```bash
   BLUESKY_HANDLE=your-handle.bsky.social
   BLUESKY_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
   # или отдельные аккаунты на каналы:
   BLUESKY_HANDLE_AI_NEWS=ai-news.bsky.social
   BLUESKY_APP_PASSWORD_AI_NEWS=...
   ```

### Mastodon (бесплатно, без ревью)

1. Аккаунт на инстансе под нишу (например `mastodon.social`, `techhub.social`;
   для ES — испаноязычный инстанс).
2. Preferences → Development → **New application**, scope `write:statuses`.
3. В `.env`:
   ```bash
   MASTODON_BASE_URL=https://mastodon.social
   MASTODON_TOKEN=...
   # или per-channel: MASTODON_BASE_URL_CRYPTO_ES / MASTODON_TOKEN_CRYPTO_ES
   ```

### Discord (бесплатно, только свои серверы)

Server Settings → Integrations → Webhooks → **New Webhook** → скопировать URL:
```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```
Постить в чужие серверы нельзя — это спам и бан.

### Проверка

```bash
./.venv/bin/python -m content_factory social-check
```
Показывает по каждому EN/ES-каналу: `✓` настроен / `—` нет кредов.

## 2. Growth-бот: deep links и inline mode

Даёт бесплатную атрибуцию («откуда пришёл подписчик») и виральность (бот отдаёт
посты канала в чужие чаты по `@bot запрос`).

1. В [@BotFather](https://t.me/BotFather): `/setinline` (включить inline mode),
   `/setcommands` (например `start - открыть каналы`). Тот же бот, что публикует.
2. В `.env`:
   ```bash
   TELEGRAM_GROWTH_BOT_USERNAME=your_bot_username   # без @
   # ссылки каналов (по умолчанию уже есть в channels.*.yaml: public_url)
   TELEGRAM_CHANNEL_URL_AI_NEWS=https://t.me/AINEWS0007
   ```
3. Запуск (long-polling, отдельный процесс):
   ```bash
   ./.venv/bin/python scripts/telegram-growth-bot.py --dry-run  # проверить ссылки
   ./.venv/bin/python scripts/telegram-growth-bot.py --once     # один цикл
   ./.venv/bin/python scripts/telegram-growth-bot.py            # слушать постоянно
   ```
4. Deep link для поста/канала:
   `https://t.me/<bot>?start=<channel>__<slot>__<post_id>` (строится через
   `content_factory.integrations.telegram_growth.start_link`).
5. `TELEGRAM_GROWTH_BOT_USERNAME` также включает кнопки под постами:
   «Подписаться» (ссылка на канал) и «Поделиться» (inline mode).
6. Статистика:
   ```bash
   ./.venv/bin/python -m content_factory growth --days 7
   ```
   События: `/start` по deep link, inline-запросы — по каналам и источникам.

## 3. Лендинг + IndexNow (поисковый трафик)

```bash
# 1) сгенерировать 6 страниц + index.html + sitemap.xml
./.venv/bin/python scripts/build_landing.py \
    --out exports/landing \
    --base-url https://<user>.github.io/<repo>

# 2) залить exports/landing/ в GitHub Pages (Settings → Pages → branch /docs или Actions)

# 3) проверить и отправить в Bing/Yandex/Seznam
INDEXNOW_KEY=<ключ 8–128 символов> LANDING_HOST=<user>.github.io \
  ./.venv/bin/python scripts/indexnow_ping.py --out exports/landing --dry-run
INDEXNOW_KEY=... LANDING_HOST=... \
  ./.venv/bin/python scripts/indexnow_ping.py --out exports/landing
```

- ключ IndexNow — придумать самому (8–128 символов `[A-Za-z0-9-]`), скрипт сам
  создаст `<key>.txt` для проверки домена;
- `--base-url` должен совпадать с реальным адресом GitHub Pages, иначе sitemap
  будет с неверными URL;
- RU-каналы в лендинг не попадают (только EN/ES).

## 4. Что проверить перед реальной публикацией

1. `./.venv/bin/python -m content_factory social-check` — все соцсети (Bluesky/Mastodon/Discord/Tumblr) `✓`.
2. `./.venv/bin/python -m content_factory run --channel ai-news --dry-run` —
   прогон без сети (dry-run подменяет публикаторы).
3. Один реальный пост: `run --channel ai-news --publish` (или дождаться демона) и
   проверить, что пост появился в Bluesky/Mastodon/Discord.
4. `growth --days 1` — события появляются после первого `/start` по deep link.

## 5. Лимиты и красная зона (напоминание)

| Платформа | Бесплатный лимит | Нельзя |
|---|---|---|
| Bluesky | ~1666 постов/ч, 300 симв. | спам/дубли |
| Mastodon | 300 запросов/5 мин, 500 симв. | чужие инстансы-правила, массовые посты |
| Discord | 30 сообщений/мин на webhook | постинг в чужие серверы |
| Telegram Bot API | 30 msg/с, 1 msg/с в чат | рассылки по чужой аудитории, парсинг MTProto |
| IndexNow | без квот в доке | спам URL |

**Не внедряем:** X/Twitter (с 02.2026 платный: $0,20/пост со ссылкой), Telegram Ads
(платно), накрутку/«API подписчиков» (не существует), userbot-автоматизацию (бан).

## 6. Следующие шаги (P1)

- **Threads API** — Meta app + App Review (`threads_content_publish`), 250 постов/24ч:
  сильная аудитория US/ES.
- **Dev.to** — API key, статьи-репосты для `ai-news`/`crypto-news` (EN tech).
- **Tumblr API** — OAuth, crypto/culture.
- **TGStat FREE** — 2 канала (лимит FREE), 50 запросов/мес.
- **TelegramChannels.me / tlgrm.eu** — бесплатная подача EN-каналов (формы, не API).

См. также: [free-promo-apis.md](free-promo-apis.md) — полная карта API и лимитов.
