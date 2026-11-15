# API-ключи: инвентаризация и бесплатные лимиты (обновлено 15.11.2026)

Цель — максимум бесплатного доступа для завода каналов: постинг, аналитика,
SEO, email, travel-монетизация, LLM/новости. Значения ключей здесь не
публикуются — только статус и где лежат.

## Где хранятся ключи

- **GitHub Secrets** — для облачных workflow: `Settings → Secrets and variables →
  Actions` (70 секретов на 15.11.2026).
- **`.env`** — локально (78 непустых значений; не коммитится).
- **Cloudflare Worker secrets** — для `cf-subscribe`/трекера ссылок.

## Что уже работает (бесплатные тарифы)

| Категория | Сервисы | Статус |
|---|---|---|
| Telegram | Bot API (`TELEGRAM_BOT_TOKEN`), chat_id каналов | ✅ работает |
| Fediverse | Bluesky (`BLUESKY_*`) на `crypto-news` | ✅ работает |
| Fediverse | Mastodon (`MASTODON_*`) | ⛔ аккаунт отключён (`403 login disabled`), направление снято с публикации |
| Fediverse | Akkoma (`AKKOMA_*`) на `crypto-news` | ✅ проверено живым слотом: публикация проходит |
| Discord | Webhook (`DISCORD_WEBHOOK_URL`) на 3 EN-каналах | ✅ проверено `discord-check`: отправка и удаление работают |
| Tumblr | OAuth1 (`TUMBLR_*`), фото/текст | ✅ креды есть; дайджест приостановлен |
| Buffer | `BUFFER_API_KEY`, `BUFFER_X_CHANNEL_ID` | ⚠️ ключ рабочий: API видит X (`@NValdislav`) и Facebook; в `config/buffer.yaml` только X. Автоочередь `buffer-queue` в архиве, но для `crypto-news` включён `buffer-x` (shareNow) |
| X | `BUFFER_API_KEY` (+ `X_*` для direct) | ✅ автопостинг `crypto-news` → `@NValdislav` работает через Buffer (`buffer-x`), живой пост 15.11.2026. Прямой OAuth1: `users/me` 200, но POST → 403 `oauth1-permissions`; нужны права Read+Write и новый access token |
| Pinterest | `PINTEREST_ACCESS_TOKEN`, `PINTEREST_API_BASE`, `PINTEREST_BOARD_ID` | ✅ sandbox API проверен 15.11.2026 (`GET /boards` 200, 2 доски); production ожидает Standard access |
| Reddit | — | ⛔ API закрыт с 31.10.2026 (новые ключи не выдают) |
| Email | Brevo (`BREVO_API_KEY`, `BREVO_LIST_ID_EN/ES`, `EMAIL_FROM`) | ✅ API 200, free 300 писем/день, EN/ES-списки созданы; подписчиков 0, weekly-рассылка пока в архиве |
| LLM | Groq, Cloudflare, Cohere, OpenRouter, Pollinations, Gemini | ✅ реальные вызовы 15.11.2026 вернули `OK`; Ollama Cloud — `402 credits depleted`, оставлен последним fallback |
| LLM (резерв) | GigaChat, YandexGPT | ⚠️ переменные есть, значения **пустые** |
| Новости/поиск | GDELT, NewsData, Tavily ×2 | ✅ работает |
| Аналитика | GA4 (`GA4_SA_JSON` + property) | ✅ работает |
| SEO | IndexNow (`INDEXNOW_KEY`) | ✅ работает |
| Travel | Travelpayouts API token + marker, Twelvedata | ✅ добавлено в GitHub 09.11.2026 |
| Ссылки | Свой трекер (`LINK_TRACKER_*`, admin token) | ✅ работает |
| Инфраструктура | GitHub, Cloudflare (Workers/KV), Rclone | ✅ работает |
| Автоматизация | Pipedream, Postman | ⚠️ секреты есть, но в коде фабрики не используются (только хранятся) |
| MTProto | `TG_API_ID`/`TG_API_HASH`/`TG_SESSION` | ⚠️ локально есть имена, но **значения пустые** |

## Добавлено 09.11.2026 (в GitHub Secrets)

`TRAVELPAYOUTS_API_TOKEN`, `TRAVELPAYOUTS_MARKER`, `TWELVEDATA_API_KEY`,
`PIPEDREAM_API_KEY`, `POSTMAN_API_KEY`, `LINK_TRACKER_ADMIN_TOKEN`.
Существующие секреты не перезаписывались.

## Чего не хватает и почему нельзя взять «само»

| Сервис | Что даёт | Почему блок | Что нужно |
|---|---|---|---|
| **Brevo** (300 писем/день) | email-дайджест | аккаунт подключён, но списки EN/ES пусты, weekly workflow в архиве | включить рассылку и набрать подписчиков через `/subscribe/` |
| **Resend** (3 000/мес) | email API | нужен свой домен для отправки чужим адресатам | домен + DNS (сейчас только `github.io`) |
| **Google AI Studio / Gemini** | LLM free tier | профиль Google разлогинен | войти в Google в браузерном профиле — создам ключ |
| **Google Search Console** | индексация, sitemap API | нет Google-логина | войти в Google; добавлю HTML-верификацию и service account |
| **Bing Webmaster** | Bing-индексация + API key | нет Microsoft-логина | войти в Microsoft/Bing |
| **Yandex Webmaster** | Яндекс-индексация | нет Yandex-логина | войти в Yandex |
| **Bluesky (напрямую)** | API постинга | ✅ работает для `crypto-news`; Buffer не нужен | — |
| **VK** | постинг | `VK_ACCESS_TOKEN` пустой | токен из VK ID/сообщества |
| **TikTok/YouTube/Threads/LinkedIn** | видео/посты | app review + телефон/аудит | не бесплатно «сразу», долгий ревью |
| **Telegram MTProto** | сбор метрик/сессии | `TG_API_ID/HASH` пустые + телефон/код | заполнить my.telegram.org и код |
| **Pinterest** | API пинов | sandbox-токен работает; production закрыт | получить Standard access и production-токен |

## Бесплатные API без ключей (можно использовать сразу)

Open-Meteo (погода), CoinGecko (крипто-цены), Frankfurter/ECB (валюты),
YouTube RSS, Hacker News API, Wikipedia API, Pollinations (картинки), BingX
public market API, Telegram Bot API. Ключи для них не нужны.

## Принципы

- Не покупаем и не парсим чужие ключи/базы; не создаём мультиаккаунты.
- Для каждого сервиса — один аккаунт владельца; ключи только в Secrets/.env.
- Бесплатные лимиты проверяем перед запуском (`docs/free-promo-apis.md`,
  `docs/promo/email-newsletter-free.md`).
- Приоритет: email (Brevo) → Google Search Console/Bing → Discord/Bluesky
  напрямую → Pinterest API (после аппрува).
