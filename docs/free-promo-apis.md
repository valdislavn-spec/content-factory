# Бесплатные API для продвижения Telegram-канала: полная карта

**Дата live-проверки: 7 ноября 2026.** Проверялись официальные доки/страницы тарифов и, где
можно без аккаунтов, живые эндпоинты. Сырые отчёты (все ссылки, команды, пометки «не проверено»):

- [.research/promo/01-social-apis.md](../../.research/promo/01-social-apis.md) — API соцсетей для кросспостинга;
- [.research/promo/02-telegram-apis.md](../../.research/promo/02-telegram-apis.md) — Telegram Bot API, giveaways, MTProto, каталоги;
- [.research/promo/03-discovery-seo-ads.md](../../.research/promo/03-discovery-seo-ads.md) — поиск, SEO/лендинг, GitHub, гранты, ссылки.

**Контекст.** Живые каналы: 3 EN (США) — `ai-news`, `crypto-news`, `sport-news`;
3 ES (ЛатАм) — `tech-ai-es`, `crypto-es`, `futbol-es`. Бюджет 0, оператор в РФ,
`content-factory` публикует посты автоматически. Внимание: реклама и платные тарифы ниже
помечены явно — бесплатных API для **накрутки подписчиков** не существует в принципе.

---

## TL;DR — что реально бесплатно и работает

| # | Задача | Бесплатные API | Что даёт | Ключевое ограничение |
|---|---|---|---|---|
| 1 | **Кросспостинг в соцсети** | **Bluesky** (AT Protocol), **Mastodon**, **Threads**, **Dev.to**, **Tumblr**, **Discord webhooks** | бесплатный трафик извне Telegram: пост → ссылка на канал | X теперь платный ($0,20/пост со ссылкой); Threads/IG/FB требуют App Review |
| 2 | **Telegram-нативные механики** | **Bot API 10.3**: deep links `?start=`, inline mode, `switch_inline_query`, invite-links/join request, `getChatMemberCount` | атрибуция «откуда пришёл», виральная раздача контента в чужих чатах через inline, точка входа «подписаться» | Bot API не умеет рассылать по чужой аудитории и не создаёт giveaways |
| 3 | **Каталоги каналов** | **TelegramChannels.me** (free submit, EN), **tlgrm.eu** (EN), tlgrm.ru, tgdr.io и др. + **awesome-lists через GitHub API** | разовые SEO-страницы канала и входящий трафик | API есть только у TGStat (FREE: 2 канала/50 запросов) и Telemetr (платно); остальное — формы |
| 4 | **Поиск/партнёры** | **Brave Search API** (до $20 бесплатных вызовов/мес), **SearXNG** (self-host), HN Firebase, Product Hunt GraphQL | поиск каналов-партнёров, мониторинг упоминаний | Google CSE закрыт новым клиентам (2026-02), Bing Web Search API выведен (2025-08) |
| 5 | **Лендинг → подписка** | **GitHub Pages**, **Cloudflare Pages**, **IndexNow**, sitemap/RSS, GA4 Data API | посадочная страница канала + индексация в Bing/Yandex | Google Indexing API для лендинга не годится (только JobPosting/BroadcastEvent) |
| 6 | **Ссылки/QR/UTM** | v.gd, TinyURL `api-create.php`, goqr.me (проверены live) | UTM-разметка и QR без платных сервисов | is.gd из этой сети не ответил (то же семейство, что v.gd) |
| 7 | **Аналитика** | Bot API `getChatMemberCount`/`getChat`, TGStat FREE (2 канала), GA4/Umami/Matomo | бесплатный мониторинг подписчиков/переходов | t.me/s — это HTML, не API; парсинг — серая зона |
| 8 | **Официальные конкурсы/ads** | ❌ API нет, всё платно: giveaways — только ручные из клиента, Telegram Ads — min 0.1 TON, каналы 1000+ | — | бесплатного API конкурсов/Premium-раздач в 2026 нет |

**Итог:** бесплатных API много, но реальных каналов роста **три**: (1) Bot API-механики
(deep links + inline + join request), (2) кросспостинг в Bluesky/Mastodon/Threads/Dev.to/Tumblr,
(3) лендинг + IndexNow + каталоги/PR. Всё остальное — вспомогательное.

---

## 1. Telegram Bot API — единственный бесплатный TG-нативный канал

Bot API **10.3** (24.08.2026), `https://api.telegram.org/bot<token>/METHOD`, платы за методы нет.
Механики, полезные для роста:

| Механика | Endpoint / параметр | Что даёт |
|---|---|---|
| **Deep links** | `https://t.me/<bot>?start=<payload>`, payload ≤ **64 симв.** (`A-Z a-z 0-9 _ -`) | атрибуция: «пришёл из канала X, слота Y, поста Z» + выдача лид-магнита после `/start` |
| **Inline mode** | update `inline_query` → `answerInlineQuery` (≤ **50** результатов, `cache_time` 300 c по умолчанию) | бот отдаёт карточки постов канала **в любой чужой чат**, где его вызвали → виральная дистрибуция |
| **switch_inline_query** | кнопки `InlineKeyboardButton` в постах | читатель сам «шэрит» пост через бота в другой чат — бесплатный охват |
| **Menu button / WebApp** | `setChatMenuButton` (`web_app`) | точка входа «открыть ленту / подписаться» из профиля бота |
| **Invite links + join request** | `createChatInviteLink(creates_join_request=true)`, `approveChatJoinRequest`, update `chat_join_request` | закрытая ссылка «подписался → получи доступ/бонус» + учёт заявок |
| **getChatMemberCount / getChat** | `getChatMemberCount?chat_id=@channel` | точный счётчик подписчиков и метаданные канала |
| **sendPoll / Quiz** | `sendPoll` (`type=quiz`, `explanation`, `open_period`) | вовлечение: квизы под нишу (crypto/sport/AI) повышают досмотры и пересылки |

Ограничения (FAQ Bot API): **~30 сообщений/с** на бота, **1 сообщение/с** в один чат,
**20 сообщений/мин** в группу; при превышении — `429`. Файлы: download 20 МБ / upload 50 МБ.
**Paid broadcasts** (1000 msg/s) — 0,1 Stars за сообщение, нужны ≥100k Stars и ≥100k MAU →
для бюджета 0 не подходит.

**Чего Bot API не может:** рассылать по чужой аудитории (только `/start`-диалоги и свои чаты),
искать каналы/чаты (это MTProto), создавать официальные giveaways, закупать Telegram Ads.

### Giveaways, Premium, boost, Telegram Ads

| Что | API для ботов | Бесплатно? |
|---|---|---|
| Официальные giveaway в каналах | ❌ методов создания нет (только read-only классы `Giveaway`, `GiveawayWinners`, …) | ❌ призы Premium/Stars платные; механика — только user-клиенты (MTProto layer 166/187) |
| `sendGift` / `giftPremiumSubscription` | ✅ есть | ❌ Stars: Premium 1000/1500/2500 Stars за 3/6/12 мес |
| Boost канала | только чтение (`getUserChatBoosts`) | ❌ даётся платными Premium-подписками |
| Telegram Ads | ❌ публичного API закупки нет, только веб-кабинет | ❌ min CPM 0.1 TON, каналы 1000+ |

**Бесплатный конкурс** делается вручную: пост в своём канале + кнопка «Участвовать» +
проверка подписки через `getChatMember` (как в [tg-growth.md §2.1](tg-growth.md)).
Telegram-механику giveaway можно использовать «как оформление» из клиента вручную, но
автоматизировать ботом её нельзя.

### MTProto / TDLib — красная зона

`contacts.search` и `channels.searchPosts` — «Only users can use this method», т.е. только
с user-аккаунта; поиск каналов и парсинг = риск бана аккаунта, а full-text search в
`channels.searchPosts` после бесплатных слотов стоит Stars. **Telethon заархивирован**
(последний push 2026-02-21, ★12 064). Для автоматизации роста не использовать.

---

## 2. Кросспостинг: бесплатные API соцсетей

| API | Что постит | Endpoint | Бесплатный лимит (docs) | Требования | Риск | EN/ES |
|---|---|---|---|---|---|---|
| **Bluesky (AT Protocol)** | текст ~300 симв., ссылки/карточки, медиа | `POST /xrpc/com.atproto.server.createSession` → `POST /xrpc/com.atproto.repo.createRecord` (`app.bsky.feed.post`) | 5 000 points/ч, 35 000/день; CREATE=3 points → **≈1 666 постов/ч**; createSession 30/5 мин | аккаунт; на bsky.social `phoneVerificationRequired: true` | низкий (анти-спам Guidelines) | ✅✅ EN и ES — лучший бесплатный охват |
| **Mastodon** | статус (500 симв. по умолчанию), медиа, ссылка | `POST /api/v1/statuses`; приложение: `POST /api/v1/apps` | **300 запросов/5 мин** на аккаунт; медиа 30/30 мин | аккаунт на инстансе; правила инстанса; бота пометить как бота | низкий-средний | ✅ EN (mastodon.social, techhub.social), ES — испаноязычные инстансы (список не проверен) |
| **Threads API (Meta)** | пост (500 симв., медиа, карусель) | `POST /{user-id}/threads` → `POST /{user-id}/threads_publish` | **250 API-постов/24ч**; 1 000 ответов/24ч; лимит вызовов = 4800×impressions | Instagram/Threads-аккаунт, Meta app, **App Review** (`threads_basic`, `threads_content_publish`) | средний (правила Meta) | ✅ EN (US), ✅ ES (LatAm) |
| **Dev.to (Forem)** | статья Markdown, ссылки, теги, обложка | `POST /api/articles`, заголовок `api-key` | **10 созданий статей/30 сек**, 30 обновлений/30 сек | аккаунт + API key | низкий | ✅ EN tech/AI/crypto; ❌ ES слабо |
| **Tumblr API v2** | текст/ссылка/фото/видео в блог | `POST /v2/blog/{blog}/post` | **1 000 запросов/ч, 5 000/день** на consumer key | OAuth 1.0a приложение + блог | средний (спам-политика) | ✅ EN, ✅ ES |
| **Discord webhooks** | сообщение (текст, embed-ссылка, файлы) в **свой** сервер | `POST /api/webhooks/{id}/{token}` | **30 сообщений/мин** на webhook; 50 req/s на бота | свой сервер; webhook URL (без OAuth) | высокий при постинге в чужие серверы → бан | ✅ как community-канал, не прямой трафик |
| **Instagram Graph API** | фото/видео/карусель + caption | `POST /{ig-user-id}/media` → `media_publish` | **100 API-постов/24ч** | IG Business/Creator + FB Page + Meta app + App Review | средний; **ссылки в caption не кликабельны** | ⚠️ плохо под новости |
| **Facebook Pages API** | пост на страницу | `POST /{page-id}/feed` | 4800×engaged users/24ч (Pages) | Page + Meta app + App Review | средний | ⚠️ нужна Page на каждый канал |
| **Reddit Data API** | пост/ссылка в сабреддит, коммент | `POST /api/submit` (OAuth) | Free tier для **одобренных** клиентов: 100 QPM | **одобрение OAuth** по Responsible Builder Policy; правила сабреддитов | **высокий**: самопромо/ссылки на TG банятся; коммерческое использование — лицензия | ⚠️ EN ограниченно, ES слабо |
| **LinkedIn API** | пост в **свой профиль** | `POST /rest/posts` (`w_member_social`) | 150 запросов/день на участника; 100k/день на приложение | LinkedIn app; страницы компаний — только partner program | низкий | ✅ EN; ⚠️ ES меньше |
| **Tumblr / Pinterest** | — | Pinterest: `POST /v5/pins` | Pinterest trial: 1000 req/день, но **пины скрыты**; Standard — бесплатно после **ревью с видео-демо** | OAuth2 app | средний | ⚠️ нужны картинки |
| **YouTube Data API v3** | видео/Shorts (`videos.insert`) | `POST upload/videos` | 100 `videos.insert`/день, 10 000 units/день | Google Cloud + OAuth | средний | ⚠️ только видео |
| **TikTok Content Posting API** | видео/фото Direct Post | `POST /v2/post/publish/content/init/` | до аудита: ≤5 пользователей/24ч и посты **private** | аудит приложения TikTok | высокий до аудита | ⚠️ только видео |
| **VK / OK API** | пост в своё сообщество | `POST api.vk.com/method/wall.post` | бесплатно | приложение + сообщество | низкий | ❌ аудитория РФ — не наш трафик |
| **Matrix / Nostr** | сообщение в комнату / kind-1 в relay | Matrix `PUT /rooms/{id}/send/...`; Nostr websocket | бесплатно; лимиты — на каждом node/relay свои | аккаунт/homeserver, ключ | средний (спам в чужие) | ⚠️ ниша, малый охват |
| **Hashnode** | статья GraphQL | `publishPost` | ❌ **бесплатный GraphQL API закрывается** с мая 2026 → платно | — | — | ❌ |

**Не бесплатно:** **X/Twitter API** — бесплатного тарифа для новых разработчиков нет
(с фев. 2026 pay-per-use: **$0,015/пост**, **$0,20/пост со ссылкой**; разовые кредиты до $70 —
акция, не тариф). Telegram Ads, Reddit Ads — платно. LinkedIn Pages, TikTok публично, Pinterest
Standard, Reddit — только после ревью/одобрения.

**Красная зона:** автопостинг в чужие Discord-серверы/Matrix-комнаты/Telegram-комментарии,
дубли одного поста пачкой, массовые аккаунты, накрутка — баны и ToS-нарушения. Постить только
в свои аккаунты/серверы/комнаты, адаптируя текст под платформу.

---

## 3. Каталоги и директории: где есть API, где только форма

| Каталог | API | Бесплатная подача | Заметки |
|---|---|---|---|
| **TGStat** | ✅ API Stat: **FREE — 2 своих канала, 50 запросов/мес**, глубина 3 дня; S — 2 100 ₽/мес | каталог открыт, добавление канала через ЛК/модерацию (форма live не проверена) | лучший бесплатный API для аналитики **своих** 2 каналов |
| **Telemetr.io** | ✅ REST (`api.tlmtr.io`), docs отдают 403 при автоматическом чтении — **не проверено** | FREE: 10 Credits, 100 каналов, 5 анализов/день; API-лимиты FREE не подтверждены | Pro $25/мес, Advanced $55/мес |
| **TelegramChannels.me** | ❌ API нет | ✅ **free submit**: `telegramchannels.me/cp/media/create` | **лучший бесплатный EN-каталог**: ~350K визитов/мес, ежедневная проверка подписчиков, growth-график |
| **tlgrm.eu** | ❌ API нет | ✅ форма: `forms.tlgrm.eu/channels/suggest?lang=en` | только EN, только публичные `t.me/username`, 1 картинка-аватар |
| **tlgrm.ru** | ❌ API нет | ✅ форма `forms.tlgrm.ru/channels/suggest` | RU-витрина — для EN/ES бесполезна |
| **tgdr.io, tdirectory.me, tgscroll, tgram.me, protelegram, tgland, besttelegramchannels, search-t.me** | ❌ API нет | ✅ базовое размещение бесплатно | **live не проверялись**; только как дешёвые бэклинки, не как трафик |
| **Awesome-листы (GitHub)** | ✅ через REST API PR (`POST /repos/{o}/{r}/pulls`) | ✅ | [TGrpg/awesome-telegram](https://github.com/TGrpg/awesome-telegram) ★598 CC-BY-4.0, [kalanakt/awesome-telegram](https://github.com/kalanakt/awesome-telegram) ★272 GPL-3.0 — оба живые (push 2026-11-07) |

Для **ES-каналов** специализированных бесплатных каталогов с трафиком не найдено: ставка на
Bluesky/Threads + Bot API deep links, а каталоги — как бэклинки.

---

## 4. Поиск партнёров, индексация, лендинг, бэклинки

### 4.1. Поисковые API

| API | Endpoint | Бесплатный лимит | Что даёт |
|---|---|---|---|
| **Brave Search API** | `GET api.search.brave.com/res/v1/web/search`, header `X-Subscription-Token` | «up to **$20 in free calls** every month», prepaid | поиск каналов-партнёров/сайтов по темам, мониторинг упоминаний |
| **SearXNG (self-host)** | `GET /search?q=…&format=json` | бесплатно, ограничен только вашим сервером | свой «поисковик» без ключей — идеален для РФ |
| **Hacker News (Firebase)** | `GET hacker-news.firebaseio.com/v0/topstories.json` | бесплатно, без ключа (проверено) | темы/поводы для AI/tech каналов |
| **Product Hunt GraphQL** | `POST api.producthunt.com/v2/api/graphql` | бесплатно; rate limit не проверен | запуск «продукта» → трафик на лендинг/канал |
| **Reddit search** | `oauth.reddit.com` | free tier после одобрения OAuth (100 QPM) | поиск сабреддитов; самопромо рискованно |
| **Google Custom Search JSON** | `googleapis.com/customsearch/v1` | ❌ **закрыт для новых клиентов** (2026-02; legacy до 2027-01) | нельзя новому проекту |
| **Bing Web Search** | — | ❌ **выведен 2025-08-11** | замены от Microsoft нет |
| **DuckDuckGo** | официального API нет | — | парсинг против ToS |

### 4.2. Индексация и лендинг

| API | Бесплатно? | Применимость |
|---|---|---|
| **IndexNow** (`api.indexnow.org/indexnow`) | ✅ без регистрации; ключ 8–128 hex; файл `<key>.txt` в корне сайта | новый пост/страница → пуш в **Bing, Yandex, Seznam, Naver**; квоты в доке не указаны |
| **sitemap.xml + RSS/Atom** | ✅ | работает всегда; базовый минимум |
| **Google Search Console API** | ✅ | отправка sitemap, инспекция URL (нужна верификация) |
| **Yandex Webmaster API** | ✅ | RU-зеркало (нужна верификация) |
| **Google Indexing API** | технически да, но ❌ | только JobPosting/BroadcastEvent — для лендинга не годится |
| **GitHub Pages** | ✅ | сайт ≤1 ГБ, 100 ГБ/мес soft, 10 сборок/ч soft (в Actions не действует); API `POST /repos/{o}/{r}/pages/builds` |
| **Cloudflare Pages** | ✅ | 500 сборок/мес, 20 000 файлов, 25 MiB/файл, 100 проектов; REST/wrangler |
| **Vercel Hobby / Netlify Free** | ⚠️ | лимиты есть, доступность/оплата из РФ не проверены |

### 4.3. Бесплатные рекламные программы — важно

| Программа | Условия (проверено) | Для нас |
|---|---|---|
| **Google Ad Grants** | до **$10 000/мес** поисковых объявлений; **eligible nonprofit** (по Google for Nonprofits — 501(c)(3), live не подтверждено) | ❌ физлицу/проекту из РФ недоступно |
| **Microsoft Ad Grants** | ~$3 000/мес; только некоммерческим организациям | ❌ |
| **Telegram Ads** | веб-кабинет, min CPM 0.1 TON, каналы 1000+; API закупки нет | ❌ платно |
| **Reddit Ads** | платно | ❌ |
| **Product Hunt запуск** | бесплатно, но нужен реальный «продукт» (бот/сервис), не канал | ⚠️ возможно для бота-агрегатора |

**Вывод:** бесплатных ad-грантов для физлица/проекта из РФ нет; бесплатный «рекламный» трафик =
органический поиск (IndexNow/sitemap), GitHub-PR, каталоги, Product Hunt/Reddit/HN (аккуратно).

### 4.4. Ссылки, QR, UTM, аналитика

| Инструмент | Endpoint | Лимит | Проверено |
|---|---|---|---|
| **v.gd** | `https://v.gd/create.php?format=json&url=…` | без ключа | ✅ вернул `https://v.gd/8vTZB9` |
| **TinyURL** | `https://tinyurl.com/api-create.php?url=…` | без ключа | ✅ вернул `tinyurl.com/2cfnmoor` |
| **is.gd** | то же семейство | без ключа | ⚠️ HTTP 000 из этой сети — не проверен |
| **goqr.me** | `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=…` | fair use, лимиты в доке не указаны | ✅ PNG 200 |
| **GA4 Data API** | `POST analyticsdata.googleapis.com/v1beta/properties/{id}:runReport` | **200 000 Core-токенов/сутки** на property, 40 000/час | ✅ docs |
| **Umami / Matomo (self-host)** | свой инстанс | бесплатно | ✅ (см. tg-growth) |
| **UTM** | просто параметры `?utm_source=telegram&utm_medium=channel&utm_campaign=<channel>&utm_content=<post_id>` | — | ✅ без сервиса |

---

## 5. Применимость к нашим 6 каналам

| Канал | Приоритет 1 | Приоритет 2 | Приоритет 3 |
|---|---|---|---|
| `ai-news` (EN, США) | Bluesky | Mastodon (tech-инстанс) | Dev.to (статьи) |
| `crypto-news` (EN) | Bluesky | Mastodon | Tumblr |
| `sport-news` (EN) | Bluesky | Threads | Mastodon |
| `tech-ai-es` (ES, ЛатАм) | Bluesky | Threads | Mastodon |
| `crypto-es` (ES) | Bluesky | Threads | Mastodon |
| `futbol-es` (ES) | Threads | Bluesky | Mastodon |

Для всех каналов — общий контур: **Bot API deep links + switch_inline_query** (атрибуция и
виральность) → **лендинг на GitHub Pages + IndexNow** (поисковый трафик) → **каталоги**
(TelegramChannels.me для EN; для ES — бэклинки) → **TGStat FREE** на 2 самых крупных канала
(`crypto-news` и `ai-news`).

---

## 6. План внедрения в content-factory (0 ₽)

### P0 — сегодня/за вечер (без ревью и аккаунтов с модерацией)

1. **`integrations/telegram_inline.py` + `growth_events`** (уже запланировано в
   [tg-growth.md §5](tg-growth.md#5-план-внедрения-для-живых-uslatam-каналов-0-без-докера-30-дней)):
   deep-links `t.me/<bot>?start=<channel>_<slot>_<post_id>`, inline mode в боте
   (`answerInlineQuery` с последними постами из SQLite), кнопки `switch_inline_query`,
   invite-links с join request под лид-магнит; всё считается в SQLite.
2. **`publishers/bluesky.py`** — AT Protocol: `createSession` (app password из `.env`),
   `com.atproto.repo.createRecord` (`app.bsky.feed.post`), ссылка на пост канала в text/link-card.
   Нужен аккаунт Bluesky (bsky.social требует телефон).
3. **`publishers/mastodon.py`** — `POST /api/v1/apps` + `POST /api/v1/statuses`; токен в `.env`;
   инстанс под нишу (tech/crypto/sports; для ES — испаноязычный).
4. **`publishers/discord.py`** — webhook в **свой** сервер (30 сообщений/мин): репост постов
   в community-канал.
5. **Лендинг + IndexNow**: GitHub Pages (папка `exports/` уже есть) → 6 страниц каналов +
   `sitemap.xml`/`feed.xml`; `scripts/indexnow_ping.py` — пинг `api.indexnow.org/indexnow` при
   новом посте; UTM-ссылки через v.gd/TinyURL; QR через goqr.me.
6. **Каталоги**: submit в TelegramChannels.me (EN-каналы) и tlgrm.eu (EN); 1–2 PR в живые
   awesome-lists через GitHub API (токен в `.env`).
7. **TGStat FREE** — подключить 2 канала (`crypto-news`, `ai-news`), 50 запросов/мес: подписчики,
   охват, ER. Остальные — через Bot API `getChatMemberCount` (бесплатно без лимита 50).

### P1 — 1–2 недели (после регистраций/ревью)

8. **Threads API** — Meta app + App Review (`threads_basic`, `threads_content_publish`), 250
   постов/24ч: сильная аудитория US/ES.
9. **Dev.to** — API key, статьи-репосты для `ai-news`/`crypto-news` (EN tech-аудитория), ссылка
   на канал в конце.
10. **Tumblr API** — OAuth-приложение, для crypto/culture-нишевых постов.
11. **Brave Search API** — мониторинг упоминаний и поиск партнёров (до $20/мес бесплатных вызовов);
    альтернатива — self-host SearXNG (бесплатно, без аккаунта).
12. **GA4 Data API** (или Umami) — отчёты «какой пост/канал откуда привёл переходы» по UTM.

### P2 — когда появится бюджет/смысл

13. **Официальные Telegram giveaways** (ручные, Premium/Stars — платно) или paid Telegram Ads
    (min 0.1 TON, каналы 1000+).
14. **Instagram/Facebook/YouTube/TikTok** — только если появятся медиа/видео и пройдут ревью.
15. **Product Hunt** — запуск бота-агрегатора как «продукта».

### Как мерить

- deep-link payload `<channel>_<slot>_<post_id>` → таблица `growth_events` (source, channel,
  slot, post_id, ts);
- UTM + GA4/Umami для переходов с внешних площадок;
- Bot API `getChatMemberCount` — ежедневные дельты подписчиков по каждому каналу;
- TGStat FREE — охват/ER по 2 каналам (50 запросов/мес расходовать аккуратно).

---

## 6.1. Что уже внедрено в content-factory

Реализовано 07.11.2026 для EN/ES-каналов (US/LatAm); RU-каналы не затронуты:

- **Публикаторы**: `publishers/bluesky.py`, `publishers/mastodon.py`, `publishers/discord.py`
  (опциональные: без кредов пропускаются); `publisher_ids` в `config/channels.en.yaml` и
  `config/channels.es.yaml`.
- **Кнопки в постах**: «Подписаться» (url канала) + «Поделиться» (`switch_inline_query`) —
  включаются при заданном `TELEGRAM_GROWTH_BOT_USERNAME`.
- **Growth-бот**: deep links `?start=`, inline mode, таблица `growth_events`,
  `python -m content_factory growth --days 7`; запуск — `scripts/telegram-growth-bot.py`.
- **Лендинг + IndexNow**: `scripts/build_landing.py` (6 страниц EN/ES + sitemap),
  `scripts/indexnow_ping.py`; проверка готовности — `python -m content_factory social-check`.
- **Настройка и лимиты**: [free-promo-setup.md](free-promo-setup.md).

## 7. Красная зона — не брать

| Что | Почему |
|---|---|
| «Free subscribers API», «Telegram members API», «накрутка», «массовые подписки» | **Такого API не существует.** Bot API не умеет добавлять участников; всё под этими названиями — накрутчики/фишинг сессии → бан канала/аккаунта, обнуление охвата |
| MTProto-автоматизация (`contacts.search`, `channels.searchPosts`, массфолловинг, масс-DM) | «Only users can use this method»; userbot = нарушение ToS, бан аккаунта; Telethon archived |
| Автопостинг в чужие Discord-серверы/Matrix-комнаты/Telegram-чаты и комментарии | Спам → бан API-ключа/аккаунта |
| Дублирование одного поста пачкой по десяткам сабреддитов/серверов | Фильтры спама, бан; лимиты ≠ разрешение на спам |
| Клоакинг/обманные редиректы, чужие токены/ключи | ToS-нарушение и компрометация |
| Покупка «прогрева»/ботов/фейковых реакций | Алгоритмы Telegram отслеживают аномалии; юридические риски |

---

## 8. Ограничения и «не проверено»

1. **X API**: точные условия pay-per-use подтверждены по docs.x.com (ред. 2026-10-16), но
   страницу pricing из этой сети открыть не удалось (fetch failed) — перепроверьте перед решением.
2. **Доступность из РФ**: Bluesky/Mastodon/Dev.to/Tumblr отвечают 200 без прокси; Telegram Bot API
   и Discord из этой сети не открылись (HTTP 000) — но в проекте GitHub Actions уже ходит в Bot API,
   т.е. работает с другого IP. Threads/IG/FB/TikTok/YouTube — доступность и оплата из РФ не проверены.
3. **Telemetr API** (docs 403), формы tgdr.io/tdirectory/telegramchannels.io, точная форма подачи
   в TGStat — live не проверены.
4. **Квоты IndexNow**, цена Brave за 1k вызовов сверх $20, QPM Reddit, rate limit Product Hunt,
   лимиты Netlify/Bitly — не подтверждены первоисточником.
5. **Telegram Ads**: отсутствие публичного API — вывод из официального getting-started; закрытый
   API для агентств не проверялся.
6. **Meta App Review** сроки/требования — не проверялись; Threads/IG/FB могут потребовать
   бизнес-верификацию, недоступную из РФ.

---

## 9. Ссылки на исследования

- [01-social-apis.md](../../.research/promo/01-social-apis.md) — Mastodon/Bluesky/Threads/X/Dev.to/Tumblr/Reddit/X и др.;
- [02-telegram-apis.md](../../.research/promo/02-telegram-apis.md) — Bot API 10.3, giveaways, MTProto, TGStat/Telemetr, каталоги;
- [03-discovery-seo-ads.md](../../.research/promo/03-discovery-seo-ads.md) — IndexNow, GitHub Pages/PR, Brave, GA4, ссылки/QR, гранты.

*Итог одной фразой: бесплатных API для роста много, но реально работают три контура —
Telegram Bot API (deep links/inline/join request), кросспостинг в Bluesky/Mastodon/Threads/Dev.to/Tumblr
и лендинг+IndexNow+каталоги; всё, что обещает «подписчиков через API», — накрутка.*
