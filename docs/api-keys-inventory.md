# API-ключи: инвентаризация и бесплатные лимиты (09.11.2026)

Цель — максимум бесплатного доступа для завода каналов: постинг, аналитика,
SEO, email, travel-монетизация, LLM/новости. Значения ключей здесь не
публикуются — только статус и где лежат.

## Где хранятся ключи

- **GitHub Secrets** — для облачных workflow: `Settings → Secrets and variables →
  Actions` (51 секрет).
- **`.env`** — локально (51 непустой ключ; не коммитится).
- **Cloudflare Worker secrets** — для `cf-subscribe`/трекера ссылок.

## Что уже работает (бесплатные тарифы)

| Категория | Сервисы | Статус |
|---|---|---|
| Telegram | Bot API (`TELEGRAM_BOT_TOKEN`), chat_id каналов | ✅ работает |
| Fediverse | Mastodon (`MASTODON_*`), Akkoma (`AKKOMA_*`), Pixelfed (`PIXELFED_*`) | ✅ работает |
| Tumblr | OAuth1 (`TUMBLR_*`), фото/текст | ✅ работает |
| Buffer | X / Bluesky / Facebook через Buffer (`BUFFER_API_KEY`) | ✅ 3 канала, очередь |
| X | `X_API_KEY`/`X_API_SECRET`/`X_ACCOUNT_BLOB` | ✅ настроено (проверять через `x-check`) |
| Pinterest | `PINTEREST_ACCESS_TOKEN` | ⚠️ токен не работает: приложение на trial-ревью; пины — через Business Hub CSV |
| Reddit | — | ⛔ API закрыт с 31.10.2026 (новые ключи не выдают) |
| Email | — | ❌ нет провайдера (Brevo/Resend/MailerLite не подключены) |
| LLM | OpenAI, DeepSeek, Groq, Cohere, OpenRouter, SambaNova, HuggingFace, Gemini (в GitHub), Ollama | ✅ ключи есть |
| LLM (резерв) | GigaChat, YandexGPT | ⚠️ переменные есть, значения **пустые** |
| Новости/поиск | GDELT, NewsData, Tavily ×2 | ✅ работает |
| Аналитика | GA4 (`GA4_SA_JSON` + property) | ✅ работает |
| SEO | IndexNow (`INDEXNOW_KEY`) | ✅ работает |
| Travel | Travelpayouts API token + marker, Twelvedata | ✅ добавлено в GitHub 09.11.2026 |
| Ссылки | Свой трекер (`LINK_TRACKER_*`, admin token) | ✅ работает |
| Инфраструктура | GitHub, Cloudflare (Workers/KV), Rclone | ✅ работает |
| Автоматизация | Pipedream, Postman | ✅ добавлено в GitHub 09.11.2026 |
| MTProto | `TG_API_ID`/`TG_API_HASH`/`TG_SESSION` | ⚠️ локально есть имена, но **значения пустые** |

## Добавлено 09.11.2026 (в GitHub Secrets)

`TRAVELPAYOUTS_API_TOKEN`, `TRAVELPAYOUTS_MARKER`, `TWELVEDATA_API_KEY`,
`PIPEDREAM_API_KEY`, `POSTMAN_API_KEY`, `LINK_TRACKER_ADMIN_TOKEN`.
Существующие секреты не перезаписывались.

## Чего не хватает и почему нельзя взять «само»

| Сервис | Что даёт | Почему блок | Что нужно |
|---|---|---|---|
| **Brevo** (300 писем/день) | email-дайджест | нет аккаунта/подтверждения email | зарегистрировать на твой ящик + подтвердить ссылку (могу сделать, если дашь доступ/подтвердишь) |
| **Resend** (3 000/мес) | email API | нужен свой домен для отправки чужим адресатам | домен + DNS (сейчас только `github.io`) |
| **Google AI Studio / Gemini** | LLM free tier | профиль Google разлогинен | войти в Google в браузерном профиле — создам ключ |
| **Google Search Console** | индексация, sitemap API | нет Google-логина | войти в Google; добавлю HTML-верификацию и service account |
| **Bing Webmaster** | Bing-индексация + API key | нет Microsoft-логина | войти в Microsoft/Bing |
| **Yandex Webmaster** | Яндекс-индексация | нет Yandex-логина | войти в Yandex |
| **Discord** | вебхук в канал | нет аккаунта/сервера | создать сервер или дать доступ |
| **Bluesky (напрямую)** | API постинга | нет app password | пока покрыто Buffer |
| **VK** | постинг | `VK_ACCESS_TOKEN` пустой | токен из VK ID/сообщества |
| **TikTok/YouTube/Threads/LinkedIn** | видео/посты | app review + телефон/аудит | не бесплатно «сразу», долгий ревью |
| **Telegram MTProto** | сбор метрик/сессии | `TG_API_ID/HASH` пустые + телефон/код | заполнить my.telegram.org и код |
| **Pinterest** | API пинов | trial pending, токены read-only | ждать аппрув Pinterest |

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
