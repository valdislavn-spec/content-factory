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

## Партия 3: каталоги и индексы (08.11.2026)

| Площадка | Размер | Подача | Статус/что сделать |
|---|---|---|---|
| **TDirectory** (tdirectory.me) | 78K каналов, 2.6M визитов | модалка Submit | ❌ reCAPTCHA — вручную, по 1 каналу |
| **TGMania** (tgmania.com) | 96K каналов | `/submit`, ревью 24–48 ч | ❌ SPA без публичного API — вручную |
| **TelegramRadar** (telegramradar.com) | 22K | только поиск/авто-индекс | ✅ ничего не нужно, индексирует сам |
| **TeleJoiner** (telejoiner.com/submit) | 65K посещений | форма (JS-поля) | ❌ отправить вручную из браузера |
| **TelXplorer** (telxplorer.com/en/create_group) | free promote | форма + Telegram-бот | ❌ подтверждение канала через бота |
| **TGCamp** (tgcamp.com/channels) | 19 550 | Angular SPA | ❌ подача внутри приложения/аккаунта |
| **TelegramLobby** (telegramlobby.com) | 4 024 проверенных | публичной формы нет | ❌ похоже, редакционный отбор/аккаунт |
| **TelegramHub.app** (telegramhub.app/submit) | 2 905 каналов | форма есть, но: подписаться на @TGHubDiscover + подключить Telegram в их боте, затем «Return to submission» | ❌ нужен твой Telegram-аккаунт |
| **TelegramChannels.me** | категорийный каталог | аккаунт в кабинете | ❌ из нашей сети сайт недоступен; вручную |
| **Metricgram Directory** | ревью | trial 14 дней + подключить группу | ❌ аккаунт/подписка |
| **Telekit** | из обзора telegrammassdm | ссылка не найдена | нужна точная ссылка |

## Рекламные биржи — где продают рекламу (монетизация)

Это не листинги, а маркетплейсы: регистрируешь канал как админ, ставишь цену —
рекламодатели покупают посты. Приоритет по трафику и простоте:

| Площадка | Ссылка | Что нужно | Приоритет |
|---|---|---|---|
| **Telega.io** | https://telega.io/catalog/cryptocurrencies | регистрация (email), добавить канал Crypto & Blockchain, цена поста (по медиакиту $7–10) | 🔥 высокий (474K визитов/мес) |
| **Collaborator.pro** | https://collaborator.pro/catalog-tg/cryptocurrency | регистрация админа канала, карточка + цена; сайт из нашей сети сейчас недоступен (таймаут) | 🔥 высокий (255K, долгое время на сайте) |
| **Tagio** | https://tagio.pro/register/ → `/adex/posts/add/` | регистрация админа, добавить канал, разместить пост-оффер | средний (2.9K) |
| **AdsGram** | https://adsgram.ai/ | реклама в Telegram Mini Apps (не каналы) — отдельный продукт, нужен mini app | низкий (нет mini app) |

Цены/форматы уже в `docs/promo/media-kit.md`: при ~200 просмотрах/пост ставьте
$7 за натив 24 ч (CPM ~$35), закреп $10, неделя $28.

**Что нужно от владельца:** аккаунты на биржах (email) + Telegram-подтверждение
админа канала. После регистрации пришли ссылку на кабинет/канал — проверю
карточку, цену и статус модерации.

## Партия 4: уточнения по каталогам (08.11.2026)

| Площадка | Проверено | Вывод |
|---|---|---|
| **TelXplorer** | форма + **CAPTCHA** + ручная проверка | вручную (или скрипт не пройдёт капчу) |
| **TlgramGo** | нужна регистрация | вручную |
| **GroupsGyani** | вход в аккаунт | вручную |
| **TelegramChannels.me** | базовая подача после регистрации; платное выделение | вручную (бесплатного достаточно) |
| **TelegramHub.app** | подписка на @TGHubDiscover + подтверждение Telegram через бота | вручную |
| **TGSelect** | бесплатная подача; подтверждение владения через бот-администратора | **нужна точная ссылка** — домены tgselect.* не отвечают |
| **TGMetrix** | авто-индекс с минимальным порогом подписчиков/свежести | ✅ **@HOOPY0007 уже в каталоге** (`tgmetrix.com/en/channel/hoopy0007`); остальные 5 — 404 (порог не пройден, действий не требует) |
| **Dyora** | финансовая тематика, от 100 подписчиков + свежий пост; подходит только HOOPY0007 | домены `dyora.app`/`dyora.io` — парковочные страницы (`/lander`), реального сайта не нашли → **нужна точная ссылка** |
| **WebGrupos** | бесплатно, есть 18+ разделы | ✅ **карточка @HOOPY0007 уже опубликована** (подтверждено), остальные 5 live |

### Что это меняет
- **Действий не требуется:** TGMetrix (HOOPY уже там; малые каналы не пройдут порог),
  TelegramRadar, Telemetry, ChatCrawler, Lyzem, TeleSearch (авто-индексы).
- **Только вручную:** TelXplorer, TlgramGo, GroupsGyani, TelegramChannels.me,
  TelegramHub.app, TGSelect, Dyora, TDirectory, TGMania, TeleJoiner, TGCamp,
  TelegramLobby, Metricgram, Telega.io/Collaborator.pro/Tagio (биржи).
- **Ждут модерации:** WebGrupos ✅ (live), BuscadorTelegram (6 отправлено),
  search-t.me (5 принято, 1 rate-limit — повторю позже), TGStat (5 — подтверждение).

## Партия 4 (08.11.2026): TelegramHub, TelegramDir, TGMania, TelegramRankings, TGBlue

| Каталог | Отправлено | Статус/детали |
|---|---:|---|
| **TelegramHub.org** | 6/6 | ✅ API `POST https://telegramhub.org/api/submissions/` → 201 «提交成功，等待审核» (pending review) |
| **BuscadorTelegram** | 6/6 | ✅ отправлены ранее (08.11.2026), см. раздел выше |
| **TGBlue** (tgblue.com) | 3/3 ES | ✅ API `POST https://tgblue.com/api/channels` → `{"ok":true}`: ES Crypto → categoryId 3 (Crypto), ES AI и ES Sports → categoryId 6 (News) |
| **TelegramDir** | 6/6 | ✅ Все 6 каналов отправлены (pending review). AI и Crypto — через Firecrawl; US Sports — повторно подтверждён как pending; ES AI/ES Crypto/ES Sports — отправлены 08.11.2026 после снятия лимита |
| **TelegramRankings** | 1/6 было | HOOPY0007 уже подавался ранее. Остальные 5: форма пишет в Supabase `channel_submissions`, но анонимный insert получает `401 42501 row-level security`; нужен ручной браузер/аккаунт или их поддержка |
| **TGMania** (tgmania.com) | 0/6 | ❌ многошаговая Next.js-форма; JS-чанки не загружаются (ERR_TIMED_OUT), форма без гидрации не отправляется. Нужен ручной браузер |

### Ручные повторы

- **TelegramDir**: ✅ все 6 отправлены; повторно подавать не нужно.
- **TelegramRankings**: `https://telegramrankings.com/submit` — обязателен username; остальное опционально; HOOPY0007 не дублировать.
- **TGMania**: `https://tgmania.com/submit` — шаг 1 username, шаг 2 категория (Crypto & Finance / Technology / News), шаг 3 детали; ревью 24–48 ч.

## Партия 5 (08.11.2026): TGMania + TelegramRankings

| Каталог | Отправлено | Статус/детали |
|---|---:|---|
| **TGMania** (tgmania.com) | 6/6 | ✅ AI News подтверждён («Channel Submitted!»); остальные 5 отправлены пачкой, форма несколько раз показала «Channel Submitted!» — pending review 24–48 ч |
| **TelegramRankings** | 6/6 | ✅ HOOPY0007 ранее; AI News, US Sports, ES AI, ES Crypto, ES Sports — «Channel submitted successfully» (ES Sports повторно 08.11.2026). Pending review |

Повтор ES Sports не нужен — отправлен 08.11.2026, подтверждение «Channel submitted successfully».
