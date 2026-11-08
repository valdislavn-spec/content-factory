# Каталоги и листинги каналов (бесплатное продвижение)

Обновлено: 08.11.2026.

## WebGrupos — webgrupos.net

Бесплатный каталог Telegram-сообществ (11 500+): заявка без регистрации,
мгновенная публикация, постоянная обратная ссылка, заявлена индексация
Google/Bing за 24–72 часа. Подходит для органического трафика.

| Канал | Листинг | Статус |
|---|---|---|
| Crypto & Blockchain (@HOOPY0007) | https://webgrupos.net/p/11969-crypto-blockchain | ✅ live |
| AI News (@AINEWS0007) | https://webgrupos.net/p/11970-ai-news | ✅ live |
| US Sports News (@SPORTNews0007) | https://webgrupos.net/p/11971-us-sports-news | ✅ live |
| ES AI News (@WORLDNews0007) | https://webgrupos.net/p/11972-es-ai-news | ✅ live |
| ES Crypto & Blockchain (@TechnologiesNews01) | https://webgrupos.net/p/11973-es-crypto-blockchain | ✅ live |
| ES Sports News (@SPORTSAnalytics007) | https://webgrupos.net/p/11974-es-sports-news | ✅ live |

Как добавлено: форма `webgrupos.net/upload` (preview → publish) или скрипт
[`scripts/submit_webgrupos.py`](../scripts/submit_webgrupos.py) (идемпотентный,
пропускает уже опубликованные).

```bash
cd content-factory
../tools/markitdown-venv/bin/python scripts/submit_webgrupos.py \
  --channels @AINEWS0007,@SPORTNews0007
```

Проверка через 72 часа: `site:webgrupos.net` в Google, переходы в Telegram
по utm нельзя — смотрим недельный прирост подписчиков в growth-report.

## Что ещё стоит добавить (бесплатные каталоги)

- TGStat (tgstat.com) — верификация канала, страница в каталоге.
- Telemetr (telemetr.me) — карточка канала и аналитика.
- Tlgrm.eu — каталог каналов.
- Каталоги из `docs/promo/catalog-package.md` (медиакит уже готов).

## Матрица каталогов (проверено 08.11.2026)

| Каталог | Как попасть | Статус наших каналов | Кто может сделать |
|---|---|---|---|
| **WebGrupos** | публичная форма/API (без логина) | ✅ все 6 live | сделано |
| **TGStat** | автопарсинг + подтверждение владельца через Telegram | ✅ @HOOPY0007 (verified, 3 665 подп., статистика постов); ❌ остальные 5 (404) | **вручную** |
| **telegramchannels.me** | аккаунт в кабинете | ❌ не поданы | **вручную** |
| **tdirectory.me** | модалка с reCAPTCHA | ❌ не поданы (капча) | **вручную** |
| **telegramic.org** | «Add Channel» → их Telegram-бот | ❌ не поданы | **вручную** |
| **tlgrm.eu** | форма forms.tlgrm.eu (из нашей сети недоступна) | ❌ не поданы | **вручную** (из браузера) |

## Что сделать вручную (~10–15 минут, самое ценное — TGStat)

TGStat — главный каталог для рекламодателей: если канала нет, рекламу не купят.
Крипто-канал уже там и подтверждён; добавьте остальные 5:

1. Откройте TGStat и войдите через Telegram: <https://tgstat.com/>
2. Для каждого канала: `tgstat.com/channel/@<username>` → кнопка
   **«Is this your channel? Confirm»** → подтверждение через TGStat-бота.
   - @AINEWS0007
   - @SPORTNews0007
   - @WORLDNews0007
   - @TechnologiesNews01
   - @SPORTSAnalytics007
   (если страницы «Channel not found» — в кабинете TGStat → «Добавить канал»,
   либо @TGStat_Bot → `/add`.)
3. **telegramchannels.me**: регистрация → <https://telegramchannels.me/cp/media/create>
   → добавить 6 каналов (по статье: список появляется < 1 дня).
4. **tdirectory.me**: на главной кнопка «Submit» → вставить ссылку + решить
   reCAPTCHA → опубликовать (по 1 каналу).
5. **telegramic.org**: «Add Channel» → их бот в Telegram → добавить каналы.
6. **tlgrm.eu**: <https://tlgrm.eu/channels/suggest> (или форма из карточки канала).

## Проверка результата

- Через 72 ч: `site:webgrupos.net` / `site:tgstat.com @HOOPY0007` в Google.
- Подписчики: недельная дельта в `growth-report` (Telegram-отчёт).
- TGStat: после подтверждения появится статистика канала — её можно
  использовать в медиаките для продажи рекламы.

## Дополнительные каталоги (08.11.2026)

| Каталог | Страница добавления | Барьер | Что делать |
|---|---|---|---|
| **TeleJoiner** | https://telejoiner.com/submit | форма на сайте отдаёт только CSRF (поля рендерятся/ломаются), автоматическая отправка невозможна | добавить вручную из браузера: ссылка на канал, категория, язык, страна; по заявлению сайта листинг публикуется сразу |
| **TelXplorer** | https://telxplorer.com/en/create_group | после формы — подтверждение через Telegram-бота (у нас нет user-сессии), автопостинг с cookies блокируется CSRF/бот-проверкой | отправить вручную: тип (Channel), имя, описание (≤200 символов), затем подтвердить канал через их бота |
| **Metricgram** | https://www.metricgram.com/directory | нужен аккаунт **с платным планом или trial**, подключённая Telegram-группа, затем Growth → Directory Listing → Publish (AI-модерация) | регистрация + 14-дневный trial → подключить канал → создать листинг |
| **Telega.io** | https://telega.io/ | каталог рекламных каналов; добавление канала — только из личного кабинета после регистрации (email/контакт) | регистрация → кабинет → «Добавить канал»; после модерации канал смогут покупать рекламодатели |

**Можно подготовить один раз и копировать:** ссылки каналов и описания:
- @HOOPY0007 — Crypto & Blockchain; US crypto news: Bitcoin, Ethereum, markets, regulation, blockchain.
- @AINEWS0007 — AI News; AI for a US audience: models, products, policy, companies.
- @SPORTNews0007 — US Sports News; NFL, NBA, MLB, NHL, college football: scores, trades, injuries.
- @WORLDNews0007 — ES AI News; IA en español: modelos, productos, empresas y políticas.
- @TechnologiesNews01 — ES Crypto & Blockchain; Bitcoin, Ethereum y mercado cripto en español.
- @SPORTSAnalytics007 — ES Sports News; Deporte en español con datos y análisis (18+).

**Приоритет по эффекту:** TGStat (подтвердить 5 каналов) → Telega.io (может дать рекламодателей) → TeleJoiner/TelXplorer (SEO-ссылки) → Metricgram (нужен trial, слабый эффект).

## BuscadorTelegram — buscadortelegram.com (испанский каталог)

Публичная форма/API без логина и капчи, категория **Criptomonedas (34)**,
Deportes (38), Noticias y Medios (39). Email необязателен, авто-подстановка
имени/описания/аватара из t.me. Модерация, затем публикация.

- ✅ **Все 6 каналов отправлены** 08.11.2026 (после модерации появятся в каталоге):
  HOOPY0007, AINEWS0007, SPORTNews0007, WORLDNews0007,
  TechnologiesNews01, SPORTSAnalytics007.
- Скрипт: [`scripts/submit_buscador.py`](../scripts/submit_buscador.py)
  (rate-limit 60 с, категории/страны в коде, `--dry-run`).
- Проверить через 24–48 ч: `https://buscadortelegram.com/?s=HOOPY0007`
  (или страница канала в каталоге).

## Остальные из списка (требуют ручного шага)

| Каталог | Статус | Что сделать |
|---|---|---|
| **TelegramHub.org** | форма есть, но сайт SPA (нет server-rendered полей) → программно не отправить | вручную: ссылка, описание, категория **Crypto**, язык; email необязателен |
| **TGBlue** (tgblue.com) | страница `/en/publish` с полями (имя, ссылка, категория, описание, email), но submit — JS/серверный экшен | вручную: https://www.tgblue.com/en/publish — бесплатно |
| **TGMania** (tgmania.com) | `/submit` — многошаговая SPA, API не найден; заявленное рассмотрение 24–48 ч | вручную: https://tgmania.com/submit → категория **Crypto & Finance** |
| **TlgramGo** (tlgramgo.com) | нужна регистрация (по FAQ рассмотрение 24–48 ч) | вручную: регистрация → добавление канала |
| **GroupsGyani** (groupsgyani.com) | нужен вход в аккаунт, редакционная проверка | вручную: регистрация → submit листинга (категория, теги, описание) |
| **TGSelect** | домен не найден (tgselect.* не отвечает) | пришли точную ссылку — проверю и добавлю |

## Поисковики-индексы Telegram (08.11.2026)

Это в основном поисковые системы по публичным каналам: они **индексируют
автоматически**, отдельная подача чаще не нужна или требует аккаунта.
Проверено:

| Сервис | Тип | Подача | Наши каналы |
|---|---|---|---|
| **TGStat** (tgstat.com / tgstat.ru) | каталог + аналитика (7.4M визитов) | подтверждение владельца через Telegram | 1/6: @HOOPY0007 verified + статистика; 5 ждут подтверждения (вручную) |
| **Telemetr** (telemetr.me) | каталог + статистика (823K) | автопарсинг; ручное добавление через аккаунт | **2/6**: `telemetr.me/c/HOOPY0007`, `telemetr.me/c/AINEWS0007`; остальные 4 не найдены |
| **search-t.me** | поисковик (2M каналов) | публичная форма `/add` → API `/api/submit` (модерация, бесплатно) | **6/6 отправлены** 08.11.2026: 5 принято сразу, @SPORTSAnalytics007 ретраится (rate-limit 429); появятся после модерации (`search?q=<username>`) |
| **Telemetry** (telemetryapp.io) | индекс 1.23M каналов | «Request Chats» требует аккаунт; иначе автопарсинг | без действия; проверять `telemetryapp.io/browse` по названию |
| **ChatCrawler** (chatcrawler.link) | поисковик | автопарсинг | без действия (Cloudflare блокирует автоматическую проверку) |
| **Nicegram Hub** (hub.nicegram.app) | каталог в приложении | внутри приложения/авто | без действия |
| **Lyzem** (lyzem.com) | поисковик | автопарсинг | пока 0 результатов по нашим (маленькие каналы), отдельной подачи не нашли |
| **TeleSearch** (telesearch.me) | поисковик | автопарсинг | без действия |

Итог: из индексов вручную имеет смысл только **TGStat** (подтвердить 5 каналов —
это смотрят рекламодатели); остальные либо уже индексируют, либо требуют
аккаунтов и дают мало трафика.
