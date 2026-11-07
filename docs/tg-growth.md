# Привлечение подписчиков в Telegram-каналы: готовые проекты на GitHub и Hugging Face

**Дата live-проверки: 7 ноября 2026.** Все ключевые факты проверены запросами к GitHub API,
HF API и страницам репозиториев/датасетов. Сырые исследования (все ссылки, команды, пометки
«не проверено»):

- [.research/tg/01-github-promo.md](../../.research/tg/01-github-promo.md) — GitHub: конкурсы, рефералки, каталоги, кросс-промо, красная зона;
- [.research/tg/02-github-analytics.md](../../.research/tg/02-github-analytics.md) — GitHub: аналитика роста, метрики конкурентов, кросспостинг, UTM;
- [.research/tg/03-huggingface.md](../../.research/tg/03-huggingface.md) — Hugging Face: датасеты каналов, бенчмарки, модели.

**Контекст проекта и важное уточнение.** Живые каналы сети — **3 английских (США)**:
`ai-news`, `crypto-news`, `sport-news` и **3 испаноязычных (ЛатАм)**: `tech-ai-es`,
`crypto-es`, `futbol-es`. Русские каналы из `config/channels.yaml` (`tech-ai`,
`business-finance`, `science-health`, `auto`, `travel`, `culture`) **пока не запущены** — это
отдельная будущая сеть, и RU-бенчмарки ниже помечены отдельно.

По снимку роста на 07.11.2026: `crypto-news` ~3,7 тыс. подписчиков, остальные пять каналов —
единицы подписчиков. Сеть в стадии **«первые 100»**, поэтому сравнивать её с медианами
крупных каналов бессмысленно: главный KPI сейчас — первые реальные подписки и включённый
сбор метрик, а не «мы vs рынок».

**Уже есть** `scripts/growth_report.py` (точные подписчики через Bot API + парсинг `t.me/s`),
`analytics/{collector,growth,preview,telegram_metrics}`, `content_factory/promo.py`,
`scripts/{cross_promo,partner_scan,catalog_cards}.py`, план [growth-plan-2026-11.md](growth-plan-2026-11.md),
плейбук [growth/first-100-subs-playbook.md](growth/first-100-subs-playbook.md).
Задача этого документа — добавить к этому **готовые внешние проекты**, которые закрывают
именно *привлечение* (acquisition), и дать план внедрения.

---

## TL;DR — что брать сейчас (живые US/LatAm каналы)

| # | Что | Чем помогает | Лицензия | Цена/риск |
|---|---|---|---|---|
| 1 | **[backmeupplz/randymbot](https://github.com/backmeupplz/randymbot)** | Розыгрыш с кнопкой «Участвовать» и `/subscribe @channel`: участвуют **только подписчики** → подписки + репосты поста | **MIT** | 0 ₽, 🟢; hosted @randymbot или self-host (TS, без Docker) |
| 2 | **[galeone/raf](https://github.com/galeone/raf)** | Реферальные конкурсы «приведи друга»: личная ссылка → реальный учёт пришедших, лидерборд, SQLite | **Apache-2.0** | 0 ₽, 🟢; Rust + systemd |
| 3 | **Awesome-каталоги**: [ebertti/awesome-telegram](https://github.com/ebertti/awesome-telegram), [kalanakt/awesome-telegram](https://github.com/kalanakt/awesome-telegram), [TGrpg/awesome-telegram](https://github.com/TGrpg/awesome-telegram) | Бесплатное размещение канала PR-ом в README: вечный трафик с GitHub и бэклинки (для EN-каналов; ES — свои каталоги из [growth-plan](growth-plan-2026-11.md)) | разные (см. §2.2) | 0 ₽, 🟢; ~1–2 часа |
| 4 | **[Mnilax/tg-scraper](https://github.com/Mnilax/tg-scraper)** | Метрики конкурентов в наших нишах (ERR(24)/ER/CPM) → `competitor_metrics.py` | MIT | 0 ₽, 🟢; нужен Telethon (заархивирован, но работает) |
| 5 | **Свои метрики + partner_scan + CTA deep-links** | `growth_report.py`/`t.me/s` дают просмотры и ER; `partner_scan.py` — поиск партнёров в EN/ES-нишах; deep-links — атрибуция подписок | — | 0 ₽, 🟢 |

**Для будущей RU-сети — отдельный набор, к US/LatAm не применять:** HF-датасеты
[SillyFeed](https://huggingface.co/datasets/Pershlab/sillyfeed-telegram-topics) и
[tgAtlas](https://huggingface.co/datasets/starnikovoleg/telegram-public-channels-2026-W36) +
топ-10k для RU-бенчмарков и шорт-листов RU-партнёров. Все RU-цифры и шорт-листы — в §4.3;
см. также пояснение в §4.2.

**Этап 2 (когда будет VPS/Docker или неделя времени):**
[shlinkio/shlink](https://github.com/shlinkio/shlink) (MIT) — UTM/трекинг переходов вместо TinyURL,
который сейчас не считает клики; [gitroomhq/postiz-app](https://github.com/gitroomhq/postiz-app)
(AGPL-3.0) — кросспостинг в VK/X/Mastodon/Discord.

**Красная зона:** любые накрутки, «симуляция активности», массфолловинг, мультиаккаунтные
инвайтеры и коммент-боты — это бан каналов и убитый охват (подробно в §6).

---

## 1. Что у нас уже есть (чтобы не дублировать)

| Возможность | Где в проекте | Пробел |
|---|---|---|
| Точные подписчики, просмотры, ER, дельты | `scripts/growth_report.py`, `analytics/growth.py`, `analytics/preview.py` | Нет бенчмарка «мы vs рынок» и «лучшее время постинга» |
| Карточки для каталогов и ВП-аутрич | `content_factory/promo.py`, `scripts/catalog_cards.py` | Нет самого размещения в каталогах (PR) |
| Сканирование партнёров по `t.me/s` | `scripts/partner_scan.py` | Нет готового графа «похожих каналов» и шорт-листов |
| Внутреннее кросс-промо | `scripts/cross_promo.py` + `config/cross_promo.yaml` | Нет внешнего ВП и биржи |
| Публикация в TG и VK | `content_factory/publishers/` | Нет X/Mastodon/Discord/Дзен; нет UTM-статистики |
| Отчёты | `analytics/report.py`, `report.html` | Нет конкурентной таблицы и атрибуции переходов |

Вывод: завод уже умеет **измерять** и **публиковать**; не хватает механик **привлечения**
(конкурсы, рефералки, каталоги, ВП) и **атрибуции** (какой пост/слот даёт подписки).

---

## 2. GitHub: готовые механики привлечения

### 2.1. Конкурсы и розыгрыши (🟢 зелёные, легально)

| Проект | Что делает | Лицензия | ★ | Последний push | Как применить |
|---|---|---|---|---|---|
| [backmeupplz/randymbot](https://github.com/backmeupplz/randymbot) | `/randy` → пост с кнопкой «Участвовать»; `/subscribe @channel` — участвуют только подписчики; победителя выбирает random | **MIT** | 100 | 2026-11-06 | Основной инструмент: еженедельный розыгрыш в travel/culture/auto. Приз — подписка/лид-магнит. Self-host (TypeScript) или hosted @randymbot |
| [y9san9/prizebot](https://github.com/y9san9/prizebot) | Розыгрыш с random.org, публичный лог, RU/EN | MIT | 83 | 2026-03-26 | Альтернатива для «честности»: публичный лог победителей снижает недоверие |
| [Eomm/telegram-bot-give-away](https://github.com/Eomm/telegram-bot-give-away) | Мини-бот розыгрыша (Fastify) | MIT | 11 | 2023-10-28 | Резерв, если нужна своя логика «подписка на 2–3 наших канала сразу» (у randymbot `/subscribe` — один канал) |
| [galeone/raf](https://github.com/galeone/raf) | «Refer a Friend»: личные ссылки, учёт приглашённых, лидерборд, SQLite | **Apache-2.0** | 29 | 2025-12-01 | Реферальный конкурс «приведи 3 друзей → приз» в auto/tech-ai. Только реальные приглашения, без userbot-накрутки |
| [kevin-kidd/telegram-referral-bot](https://github.com/kevin-kidd/telegram-referral-bot) | Уникальные реф-ссылки, защита от self-referral, PostgreSQL | MIT | 26 | 2024-10-14 | Трекинг источников; без Docker можно поднять на venv+Postgres |
| [DeepBlue-dot/GrowBot](https://github.com/DeepBlue-dot/GrowBot) | Реферальные кампании через Mini Apps, антифрод, атрибуция | нет license | 7 | 2026-07-30 | **Только референс архитектуры** (7★, без лицензии) |

> Telegram сам проводит официальные giveaways (Premium/Stars) — максимально «белый» вариант,
> но требует бюджета. Сторонние боты (randymbot) остаются легальными и бесплатными.

### 2.2. Каталоги и awesome-листы (🟢 бесплатный трафик)

| Репозиторий | Что это | Лицензия | ★ | Push | Как использовать |
|---|---|---|---|---|---|
| [ebertti/awesome-telegram](https://github.com/ebertti/awesome-telegram) | Крупнейший curated-каталог каналов/ботов, есть раздел `## Channels` | нет license (PR — ок) | 6207 | 2026-11-02 | PR с каналами в тематические разделы (AI, finance, travel, culture) |
| [kalanakt/awesome-telegram](https://github.com/kalanakt/awesome-telegram) | Каталог с `Contributing.md`, мейнтейнер активен | GPL-3.0 | 272 | 2026-11-07 | По одному каналу = 6 PR; правила описаны |
| [TGrpg/awesome-telegram](https://github.com/TGrpg/awesome-telegram) | Ежедневно обновляемый список | CC-BY-4.0 | 595 | 2026-11-07 | Полезнее для EN-каналов; RU — если есть раздел |
| [palark/awesome-devops-telegram](https://github.com/palark/awesome-devops-telegram) | RU DevOps/SRE-каналы | нет license (PR — ок) | 301 | 2026-08-24 | Узкий целевой трафик для tech-ai |

Тактика: 4 списка × 6 каналов = 1–2 часа работы, 0 ₽, 0 риска. Повторять при обновлении списков.

### 2.3. Кросс-промо и Telegram Ads: OSS почти пуст

| Проект | Статус | Вердикт |
|---|---|---|
| [mokevnin/crossmatch](https://github.com/mokevnin/crossmatch) | RU-бот подбора каналов для **взаимного пиара**, push 2026-11-04, но **0★, без лицензии, «в разработке»** | 🟡 Наблюдать 1–2 месяца; идея (матчинг по теме/охвату + отсев накрутки) — правильная |
| [karipov/cross-prom](https://github.com/karipov/cross-prom) | **archived** с 2019 | 🔴 не брать |
| [kresswell/OptimusPromotions](https://github.com/kresswell/OptimusPromotions), [itsAPK/cross-promotion-bot](https://github.com/itsAPK/cross-promotion-bot) | README без кода | 🔴 не брать |
| [felixcake618/tg-ads-kit](https://github.com/felixcake618/tg-ads-kit) | Парсер отчётов ads.telegram.org (только чтение), 1★, MIT | 🟡 для отчётности по TG Ads; нужны cookie рекламного аккаунта |
| [Trustat-Analytics/trustat-python](https://github.com/Trustat-Analytics/trustat-python) | SDK к платному API (аналитика конкурентов и база TG Ads), 2★, MIT | 🟡 только если появится бюджет |

**Практика:** внешний кросс-промо — вручную, 5–10 обменов с каналами сопоставимого охвата
(условия: равные просмотры, нативный пост с пользой, не «подпишись»). Внутреннее ВП между
нашими каналами уже автоматизировано (`cross_promo.py`) — но включать, когда у канала
≥500–1000 подписчиков, иначе обмен бессмыслен.

---

## 3. GitHub: аналитика роста и дистрибуция

### 3.1. Метрики конкурентов (находка №1 по ROI)

| Проект | Что даёт | Лицензия | ★ | Push | Как применить |
|---|---|---|---|---|---|
| [Mnilax/tg-scraper](https://github.com/Mnilax/tg-scraper) | Telethon-сбор: подписчики, средний охват за 50 постов, **ERR(24)**, ER%, CPM, язык/гео, XLSX/JSON/CSV | **MIT** | 7 | 2026-10-02 | Взять формулы → `scripts/competitor_metrics.py` → таблица в `factory.sqlite3` → блок в `report.html` |
| [TheMyxa/telegram-parser](https://github.com/TheMyxa/telegram-parser) | Экспорт постов/комментов/реакций, дашборд с **activity heatmap**, Parquet/Postgres | **нет license** | 222 | 2026-11-07 | Только локально/референс UX: heatmap «час × день» |
| [antalkon/telegram-tools](https://github.com/antalkon/telegram-tools) | Идея **audience overlap** (пересечение аудиторий конкурентов) | MIT | 2 | 2026-11-07 | Для выбора партнёров под ВП/закупку; реализуемо SQL-запросом по экспорту |
| [mlomb/chat-analytics](https://github.com/mlomb/chat-analytics) | Heatmap активности из экспорта чатов, AGPL | AGPL-3.0 | 1 195 | 2025-10-19 | Референс отчёта «когда аудитория активна» |

### 3.2. Кросспостинг и дистрибуция (расширение охвата)

| Проект | Что делает | Лицензия | ★ | Push | Как применить |
|---|---|---|---|---|---|
| [gitroomhq/postiz-app](https://github.com/gitroomhq/postiz-app) | Self-hosted планировщик: провайдеры **telegram, vk, x, mastodon, discord, bluesky** и ещё ~20 | AGPL-3.0 | 41 080 | 2026-11-07 | Главный кандидат на «расширение охвата»; нужен VPS + Docker + Postgres + Redis → этап 2 |
| [inovector/mixpost](https://github.com/inovector/mixpost) | Self-hosted SMM-планировщик, ядро MIT | MIT (ядро) | 3 913 | 2026-03-16 | Альтернатива Postiz на PHP; список сетей (TG/VK) не подтверждён — проверить |
| [vakovalskii/transfer-channel-rss](https://github.com/vakovalskii/transfer-channel-rss) | Зеркало TG → сайт/PWA + кросспост в VK/**Дзен**/OK из RSS | AGPL-3.0 | 10 | 2026-06-15 | Единственная живая идея для Дзена; архитектура «канал → RSS → соцсети» — изучить |
| [Rongronggg9/RSS-to-Telegram-Bot](https://github.com/Rongronggg9/RSS-to-Telegram-Bot) | RSS-бот с подписками пользователей, фильтрами, OPML | AGPL-3.0 | 2 174 | 2026-11-06 | Не для публикации, а для **удержания**: читатель подписывается на наши рубрики в боте → возвраты в канал |
| [shpaker/feedforbot](https://github.com/shpaker/feedforbot) | Простой RSS→TG, дедуп, фильтры | MIT | 58 | 2026-07-10 | Лёгкий fallback-публикатор |
| [FreshRSS/FreshRSS](https://github.com/FreshRSS/FreshRSS) / [miniflux/v2](https://github.com/miniflux/v2) / [RSS-Bridge/rss-bridge](https://github.com/RSS-Bridge/rss-bridge) | Хаб источников: 200+ лент по 6 темам, API; RSS там, где его нет | AGPL-3.0 / Apache-2.0 / Unlicense | 16 526 / 9 897 / 9 337 | 2026-11 | Расширить `sources/rss.py`; ставить на VPS при необходимости |

### 3.3. UTM и трекинг переходов

| Проект | Что даёт | Лицензия | ★ | Push | Как применить |
|---|---|---|---|---|---|
| [shlinkio/shlink](https://github.com/shlinkio/shlink) | Сокращатель ссылок: короткие ссылки, теги, клики, рефереры, устройств, гео, REST API | **MIT** | 5 408 | 2026-11-07 | Заменить TinyURL (`integrations/shortlink.py` **не считает клики**) на свой домен: `post → our.link/abc` + UTM. Нужен VPS/PHP |
| [umami-software/umami](https://github.com/umami-software/umami) | Веб-аналитика с UTM-кампаниями | MIT | 39 974 | 2026-11-07 | Для лендингов/экспортов каналов |
| [plausible/analytics](https://github.com/plausible/analytics) | Privacy-first веб-аналитика | AGPL-3.0 | 29 790 | 2026-11-07 | Легче по функциям, тяжелее по стеку (Elixir+ClickHouse) |

**Бесплатная альтернатива без VPS:** deep-links через собственного бота —
`t.me/our_bot?start=<channel>_<slot>_<post_id>`, обработчик `/start` в 30 строк + таблица
`growth_events` в SQLite. Этого достаточно, чтобы понять, какой канал/слот/пост даёт подписки.

### 3.4. Инфраструктурный риск: Telethon заархивирован

| Проект | Статус | Что делать |
|---|---|---|
| [LonamiWebs/Telethon](https://github.com/LonamiWebs/Telethon) (★12 064, MIT) | **archived=True, последний push 2026-02-21** | Код работает; версию пиним в `requirements-optional.txt`; не строить новые фичи только на нём |
| [pyrogram/pyrogram](https://github.com/pyrogram/pyrogram) (★4 613, LGPL-3.0) | **archived=True** (2024-12-23) | Как замена не годится |
| [gotd/td](https://github.com/gotd/td) (★2 380, MIT) | ✅ живой (push 2026-11-07) | План Б на Go, если Telethon начнёт ломаться на новых слоях Telegram API |

Для аналитики и роста лучше опираться на **официальный Bot API** и `t.me/s` — они не завязаны
на userbot-сессии.

---

## 4. Hugging Face: готовые данные для решений

### 4.1. Датасеты (live, HF API)

| Датасет | Что внутри | Объём | Лицензия | Свежесть | Как применить |
|---|---|---|---|---|---|
| [Pershlab/sillyfeed-telegram-topics](https://huggingface.co/datasets/Pershlab/sillyfeed-telegram-topics) | 19 тем/122 подтемы: реакции/1k, длина поста, % медиа, час/день постинга, темп, вечерний uplift | 192 884 канала, 1 837 893 поста, 15 CSV | **CC BY 4.0** | 2026-10-27 | KPI и контент-формат по каждой нише (см. §4.3) |
| [JohnRicoco/top-telegram-channels](https://huggingface.co/datasets/JohnRicoco/top-telegram-channels) | Топ-10k каналов: subs, avg views, **er_percent**, язык, страна, категории, posts_30d + агрегаты 42 стран / 44 языков | 10 000 строк, 1,76 МБ | **CC BY 4.0** | 2026-10-25 | Бенчмарк ER по нишам; пул партнёров; размер рынка |
| [starnikovoleg/telegram-public-channels-2026-W36](https://huggingface.co/datasets/starnikovoleg/telegram-public-channels-2026-W36) | 5 177 каналов + **10 911 рёбер графа «похожих»** + 20 тем + `recommended_by` | 5 177 каналов | **CC BY 4.0** | 2026-09-17 | Готовый инструмент подбора партнёров для кросс-промо (сильнее самодельных эмбеддингов) |
| [ScoutieAutoML/russian-news-telegram-dataset](https://huggingface.co/datasets/ScoutieAutoML/russian-news-telegram-dataset) | 30 RU новостных каналов: posts, **views**, sentiment, spam, кластеры, векторы | ~1,8 ГБ JSON | **не указана** | 2024-11-19 | Только внутренние тесты: «какой пост даёт просмотры» |
| [desllre/ru_telegram_news_detection](https://huggingface.co/datasets/desllre/ru_telegram_news_detection) | 14 958 TG-постов: news/not_news + тематики + confidence | 14 958 | **MIT** | 2026-02-10 | Фильтр «новость vs промо/мем»; тематическая разметка |
| [rustemgareev/lenta-news](https://huggingface.co/datasets/rustemgareev/lenta-news) | 424 822 статьи Lenta.ru: заголовки, темы, теги | 424 822 | unknown | 2026-10-07 | Майнинг заголовков/тематик для рубрик; внутренние тесты |
| [ai-forever/headline-classification](https://huggingface.co/datasets/ai-forever/headline-classification) | RU-заголовки с topic-метками | 36 000 | **MIT** | 2024-05-24 | Обучение лёгкого классификатора темы заголовка |

**Размер RU-рынка Telegram (проверено по JohnRicoco):** 70 740 активных каналов 1 000+
подписчиков, 1,12 млрд суммарных подписчиков, медиана 3 364. Русский язык — 193 621 канал.

### 4.2. Что применимо к нашим US/LatAm-каналам (главное)

Коротко: **RU-датасеты из §4.3 к нашим живым каналам не применимы** — там русский язык,
RU-партнёры и RU-форматы. Открытых данных по Telegram именно для США/ЛатАм на HF почти нет:

| Источник | Для US/LatAm? | Почему |
|---|---|---|
| SillyFeed | ❌ | только RU-каналы |
| tgAtlas (5 177 + граф) | ❌/частично | снапшот RU-центричный, поля языка нет; шорт-листы — RU |
| [top-10k](https://huggingface.co/datasets/JohnRicoco/top-telegram-channels) | ⚠️ ограниченно | топ **по подписчикам**: минимум ~117 тыс.; `country` пуст у 6 543 из 10 000; строк `US` всего 24 (из них 18 — русскоязычные!), `es` — 99 (95 активных) |
| Scoutie / desllre / lenta | ❌ | русский язык |
| Spaces | ❌ | мертвы (см. §4.5) |

Что top-10k всё-таки даёт — «потолок» крупных каналов (не бенчмарк для канала с 3 подписчиками):

| Ниша | Язык | Каналов | Медиана подписчиков | Медиана ER |
|---|---|---|---|---|
| AI/tech | en | 175 | 186 182 | **0,40 %** |
| crypto | en | 267 | 227 627 | **0,76 %** |
| sports | en | 37 | 194 219 | **0,96 %** |
| AI/tech | es | 15 | 141 811 | **0,87 %** |
| sports | es | 6 | 124 208 | 0,54 % |
| crypto | es | 2 | — | данных мало |

Вывод: у крупных EN/ES-каналов ER 0,4–1 %, но это каналы на 120–230 тыс. подписчиков —
переносить эти цифры на новичков нельзя (у маленьких каналов ER в разы выше). Единого
открытого US/LatAm-бенчмарка «как у маленьких» нет — его нужно собрать самим.

**Чем заменить рыночные медианы на стадии «первые 100»:**

1. **Свои метрики.** Bot API даёт точных подписчиков, `t.me/s` — просмотры и ER. Важно:
   в сети, откуда запускался снимок 07.11, `t.me/s` недоступен (timeout) → в отчёте роста
   просмотры/ER пустые. Запускать `growth_report.py` там, где `t.me` доступен
   (GitHub Actions/VPS), иначе динамику просмотров не увидеть.
2. **`scripts/partner_scan.py`** по 10–20 EN/ES-каналам своей ниши (просмотры/пост, частота
   постинга, признаки накрутки) — свои шорт-листы партнёров для ВП, без чужих датасетов.
3. **Каталоги/биржи с фильтрами:** TGStat/Telemetr (бесплатные лимиты), для US —
   англоязычные каталоги, Reddit/X; для LatAm — испаноязычные каталоги (см.
   [growth-plan-2026-11.md](growth-plan-2026-11.md): grupostelegramlatam и др.).
4. **A/B на своих 3 постах/день** (2–4 недели): слоты, формат, длина, медиа — единственный
   честный источник «что работает» на старте.
5. Когда канал дорастёт до 1–5 тыс. подписчиков — пересмотреть top-10k/новые датасеты по
   нужной стране/языку.

### 4.3. Что данные говорят про RU-каналы (только для будущей RU-сети)

> ⚠️ **Всё в этом разделе — про русскоязычный Telegram.** К живым US/LatAm-каналам эти
> цифры и шорт-листы **не применять**: другой язык, аудитория и конкуренция. Раздел оставлен
> на случай запуска RU-сети из `config/channels.yaml`.

**KPI по размеру канала (медиана, SillyFeed).** Ставить цели по своей полосе, а не «как у больших»:

| Подписчиков | Реакций/1k просмотров | Реакций/пост | Просмотров/пост |
|---|---|---|---|
| до 200 | 43,7 | 7 | 156 |
| 200–500 | 38,8 | 9 | 239 |
| 500–1 000 | 29,3 | 11 | 397 |
| 1–5 тыс. | **20,7** | 16 | 844 |
| 5–20 тыс. | 15,3 | 34 | 2 590 |
| 20–100 тыс. | 13,9 | 104 | 8 690 |
| >100 тыс. | 14,2 | 423 | 39 750 |

**Наши ниши (SillyFeed):**

| Канал | Тема | Реакций/1k | Длина поста p50 | % длиннее 1000 зн. | % с медиа | Час p50 (MSK) | Топ-день | Доля темы 2026 / Δ vs 2024 |
|---|---|---|---|---|---|---|---|---|
| tech-ai | technology | **11,0** (самая низкая) | 923 | 46,4 | 57,2 | 14 | чт | 5,02 % / +0,62 pp |
| business-finance | business_finance | 17,6 | 1 420 | 67,9 | 46,8 | 13 | ср | 11,34 % / +1,05 pp |
| science-health | health / science | 22,9 / 27,3 | 1 168 / 850 | 57,4 / 42,5 | 58,5 / 66,1 | 13 / 14 | ср | 9,99 / 9,33 % |
| travel | travel_places | **33,3** | 610 | 31,8 | **83,9** | 14 | пн | 5,51 % / +1,05 pp |
| culture | arts_design | **44,8** | **238** | 15,9 | **87,3** | 15 | чт | 9,96 % / **+3,07 pp** (растёт быстрее всех) |
| auto | — (нет темы) | бенчмарк из top-10k: ER 1,04 % | — | — | — | 13–14 | — | — |

**Вечерний uplift** (вечер vs день): карьера +41 %, путешествия +37 %, здоровье +25 %,
искусство +20 %, деньги/бизнес +16 %, наука +15 %, мода +11 %. При этом конкуренты постят
в основном **13–15 MSK** — значит, вечерний слот (после 18:00 MSK) даёт больше отклика при
меньшей конкуренции. Воскресенье — минимум публикаций по всем темам.

**Выводы по форматам:**
- **tech-ai** — не брать объёмом: короткий объясняющий пост ~900 зн., 1 медиа, вечер;
  тема очень конкурентная (4 717 каналов), ER низкий.
- **business-finance** — длинные посты 1 400+ зн. нормальны, но медиа меньше (46,8 %) →
  график/карточка = дифференциатор.
- **science-health** — высокий ER; длинные посты ок для health, наука — 850 зн. + медиа 66 %.
- **travel** — «картинка + 3 факта»: почти всё с медиа (83,9 %), текст ~610 зн., ER 33,3.
- **culture** — самый высокий ER и самый быстрый рост доли: короткий текст ~240 зн. + медиа.
- **auto** — в SillyFeed темы нет: ориентир ER 1,04 % (RU `cars` в top-10k), нужен свой бенчмарк.

**Бенчмарк ER для крупных RU-каналов (top-10k, медиана):** tech 0,83 %, auto 1,04 %,
business 1,14 %, travel 1,32 %, science/health 1,65 %, culture 2,56 %. Это *крупные* каналы,
для маленьких смотреть SillyFeed (по размеру); сравнение — только внутри одного датасета.

### 4.4. Шорт-листы партнёров для кросс-промо (из графа tgAtlas, только RU)

> ⚠️ Шорт-листы ниже — **RU-каналы**; для US/LatAm они не подходят. Свои EN/ES-шорт-листы
> собираются через `scripts/partner_scan.py` и каталоги (см. §4.2).

Каналы 5–150 тыс. подписчиков, отсортированы по числу входящих рекомендаций (`recommended_by`).
**Перед обменом открыть каждый вручную**: живой ли канал, тон, гео, условия рекламы.

| Ниша | Кандидаты (username / подписчики / recommended_by) |
|---|---|
| tech-ai | `@denissexy` 136 566 / 15 · `@machinelearning_interview` 30 265 / 14 · `@IT_Portal` 100 545 / 11 · `@ai_newz` 96 678 / 11 · `@seeallochnaya` 78 639 / 11 · `@startupoftheday` 59 812 / 11 · `@frontendnoteschannel_ru` 31 525 / 11 · `@pythonl` 58 978 / 10 |
| business-finance | `@tradehaven` 9 278 / 7 · `@marketsAlpha` 25 714 / 4 · `@zerodhain` 54 096 / 5 (тема зашумлена индийскими/крипто-каналами) · вручную из top-10k: `@avito_b2b` 158 992 · `@sberbusiness` 236 917 · `@filatovcorr` 167 561 |
| science-health | `@data_secrets` 93 025 / 11 · `@grantscholar` 45 765 / 9 (фильтровать по языку: есть IELTS-шум) |
| travel | `@ranarod` 123 589 / 16 · `@uletet_1` 97 390 / 12 · `@dmitrii_visanews` 76 230 / 7 · `@intouristpro` 22 148 / 7 · `@tourdom` 79 873 / 6 · `@atorus` 45 565 / 6 · `@CoralTravel` 38 254 / 6 |
| culture | `@a_study` 47 306 / 13 · `@DesignWorld` 47 230 / 13 · `@AEStorage` 86 562 / 10 (дизайн/моушн) |
| news-общий | `@smmrus` 125 228 / 16 · `@vcnews` 111 693 / 13 · `@rozetked` 659 701 / 24 — общие примеры discoverability |

Методика: `JohnRicoco` → фильтр `country=RU`, `language=ru`, наша категория, 5–150 тыс.
подписчиков, ER выше медианы ниши → сверить с графом tgAtlas (`recommended_by`) → вручную
открыть 10–15 кандидатов → 5 лучших в `docs/promo/partner-candidates.txt` для `partner_scan.py`.

### 4.5. Модели (локально, MIT) под задачи роста

> ⚠️ `rubert*`, `seara`, `mxlcw`, `DiTy` — русскоязычные, для будущей RU-сети. Для живых
> EN/ES-каналов брать мультиязычные: `intfloat/multilingual-e5-large`, `XLM-R` (тональность),
> `sentence-transformers/paraphrase-multilingual-*` — матчинг партнёров и brand safety.

| Модель | Назначение | Лицензия |
|---|---|---|
| [cointegrated/rubert-tiny2](https://huggingface.co/cointegrated/rubert-tiny2) | эмбеддинги постов/каналов, «похожие каналы» (когда нет графа) | MIT |
| [ai-forever/ru-en-RoSBERTa](https://huggingface.co/ai-forever/ru-en-RoSBERTa) | RU↔EN-матчинг тем (для EN/ES-каналов) | MIT |
| [intfloat/multilingual-e5-large](https://huggingface.co/intfloat/multilingual-e5-large) | сильный baseline для заголовков | MIT |
| [seara/rubert-tiny2-russian-sentiment](https://huggingface.co/seara/rubert-tiny2-russian-sentiment) | тональность новостей перед публикацией | MIT |
| [mxlcw/rubert-tiny2-russian-financial-sentiment](https://huggingface.co/mxlcw/rubert-tiny2-russian-financial-sentiment) | бизнес-канал: тон рыночных новостей | MIT |
| [DiTy/cross-encoder-russian-msmarco](https://huggingface.co/DiTy/cross-encoder-russian-msmarco) | rerank поиска похожих каналов/тем | MIT |

**Spaces на HF для нашей задачи мертвы:** все проверенные RU-тональность/кликбейт/виральность
и «telegram»-спейсы — в `BUILD_ERROR`/`RUNTIME_ERROR`/`PAUSED`/`SLEEPING`; публичного API нет.
Поэтому модели гоняем локально (у нас уже есть qwen3.5:9b).

---

## 5. План внедрения для живых US/LatAm-каналов (0 ₽, без Docker, 30 дней)

### P0 — один вечер (сегодня)

1. **Включить сбор просмотров/ER.** Сейчас в локальной сети `t.me/s` недоступен, поэтому
   в отчёте роста есть подписчики, но просмотры/ER — пустые. Запустить `growth_report.py`
   в GitHub Actions (где `t.me` доступен) или на VPS — иначе динамику роста не увидеть.
2. **CTA-воронка и атрибуция.** В публикатор добавить inline-кнопки «Subscribe/Share»,
   deep-link `t.me/our_bot?start=<channel>_<slot>_<post_id>`, обработчик `/start` (30 строк)
   → таблица `growth_events` в SQLite (**source, channel, slot, post_id, ts**). Это заменяет
   платный UTM-сервис и показывает, какой канал/слот даёт подписки.
3. **PR в EN-каталоги.** [ebertti](https://github.com/ebertti/awesome-telegram),
   [kalanakt](https://github.com/kalanakt/awesome-telegram),
   [TGrpg](https://github.com/TGrpg/awesome-telegram) — `ai-news`, `crypto-news`, `sport-news`.
   Для ES — испаноязычные каталоги из [growth-plan-2026-11.md](growth-plan-2026-11.md).
4. **Проверить внутреннее ВП.** `crypto-news` (~3,7 тыс.) → `ai-news`/`sport-news` уже в
   `config/cross_promo.yaml`; убедиться, что публикация работает, а ES-связки добавлять,
   когда у каналов будет ≥500 подписчиков.

### P1 — 1–2 недели

5. **Розыгрыш `randymbot`** — на `crypto-news` (единственный канал с аудиторией) или в ES-нише:
   приз — подписка/лид-магнит; `/subscribe @channel`; KPI: участники, подписки за 48 ч, отписки.
   Self-host (TS, без Docker) или hosted @randymbot.
6. **Свои шорт-листы партнёров** — `scripts/partner_scan.py` по 10–20 EN/ES-каналам каждой ниши
   (просмотры/пост, частота, признаки накрутки); список → `docs/promo/partner-candidates.txt`.
7. **Реф-конкурс `raf`** — на `crypto-news`/`ai-news`: «приведи 3 друзей → приз», лидерборд;
   антифрод — реальные приглашения + ручная проверка (без userbot!).
8. **A/B слотов и форматов** (2–4 недели) на своих данных: гипотезы из RU-цифр (§4.3) не
   переносить — для EN/ES проверять заново.

### P2 — 1–2 месяца

9. **Кросспостинг** — Postiz (Docker на VPS) либо свои публикаторы Mastodon/Bluesky
   (Mastodon API бесплатный — 15 минут кода).
10. **UTM-трекинг** — Shlink (MIT) на VPS, если нужна статистика внешних переходов.
11. **Удержание** — RSS-to-Telegram-бот с подписками на рубрики (возвраты в канал).
12. **Модели** — multilingual `intfloat/multilingual-e5-large` + `XLM-R` для EN/ES
    (матчинг партнёров, тональность); `rubert`/`seara` — только для будущей RU-сети.
13. **Когда запустим RU-сеть** (`config/channels.yaml`) — `scripts/growth_benchmark.py`
    с SillyFeed/top-10k/tgAtlas (RU-цифры §4.3 и шорт-листы §4.4) + RU-специфичные механики.

### KPI, которые мерить

- **первые 100 подписчиков на канал** (сейчас у пяти каналов по 3), подписки/неделя с источником;
- ER/1k просмотров по своим данным (и появятся ли просмотры после включения `t.me/s`-сбора);
- пересылки/пост (виральность), отписки после промо (<10 %);
- участники розыгрыша → подписки (конверсия), качество рефералов (антифрод).

Сравнивать с чужими медианами **не раньше 1–5 тыс. подписчиков** — до этого они не показатель.

---

## 6. Красная зона — не брать

| Проект | Почему |
|---|---|
| [svtcore/telegram-referral-bot](https://github.com/svtcore/telegram-referral-bot) (190★) | Мультиаккаунтная эмуляция `/start` = накрутка рефералов; прямое нарушение ToS, бан аккаунтов |
| [esemi/telegram-activity-emulator](https://github.com/esemi/telegram-activity-emulator) | «Симуляция органической активности» = фейковые просмотры/реакции: убивает реальный охват и репутацию |
| [tgMember/tdAds](https://github.com/tgMember/tdAds) | Bulk sender / auto joiner: массфолловинг и спам, проект мёртв с 2019 |
| Коммент-автоматизация (PALMOCEAN/palmos-telegram, NeyroComment и подобные) | Все найденные OSS-инструменты — userbot-рассылки по чужим каналам; не проверял детально, вердикт от этого не меняется |
| [LonamiWebs/Telethon](https://github.com/LonamiWebs/Telethon) и [danog/MadelineProto](https://github.com/danog/MadelineProto) — **для роста** | Userbot от лица личного аккаунта = риск бана номера; массовые действия запрещены. Технически живые/качественные, но для роста не годятся |
| «Посевы» через ботов | Покупка поста у админа — только вручную и легально; автоматизация = спам |

**Правило:** только официальный Bot API, только боты, только реальные подписки; розыгрыши —
по правилам Telegram; никаких userbot-массовых действий от личных аккаунтов.

---

## 7. Риски и ограничения

1. **Telethon заархивирован** (2026-02-21), pyrogram — тоже; проект на Telethon для
   необязательного Telegram-источника. Код работает, версию пиним; план Б — `gotd/td` (Go).
2. **Лицензии:** CC BY 4.0 (датасеты) — можно коммерчески только с атрибуцией;
   `TheMyxa/telegram-parser`, `ScoutieAutoML`, `lenta-news` — **без лицензии** → только
   внутренние тесты, не публиковать производные без юр. проверки; NC-датасеты — нельзя
   коммерчески. AGPL (Postiz, RSS-бот, Plausible) — можно self-host, но не вендорить.
3. **HF Spaces для роста мертвы** (BUILD/RUNTIME_ERROR), RU-трендовых датасетов на HF нет —
   тренды брать вне HF (Wordstat, Trends, TGStat) или из наших RSS.
4. **`t.me` недоступен из сети проверки** → живость hosted-ботов (@randymbot, @crossmatch_bot)
   не подтверждена, подтверждён только код/README. Перед внедрением открыть вручную.
5. **Telegram Ads из РФ** — не проверялось (нужен рекламный аккаунт/карта); OSS здесь только
   отчётность и разведка, не управление кампаниями.
6. **HF доступность из РФ нестабильна** — датасеты скачать один раз и положить в `data/`
   (gitignored), не тянуть каждый прогон.
7. **SillyFeed: «когда постят» ≠ «когда эффективно»** — `posting_hour` это время публикации,
   для рекомендаций использовать `evening_uplift` + собственные A/B; выборки датасета
   (корпус/каталог/панель/архив) не складывать.
8. **Данные датасетов — публичные тексты каналов**; не деанонимизировать, партнёров проверять
   вручную, правила рекламы и Telegram соблюдать.

---

## 8. Методика проверки

- **GitHub:** `curl https://api.github.com/repos/{owner}/{repo}` — `stargazers_count`,
  `license.spdx_id`, `pushed_at`, `archived`; `raw.githubusercontent.com/.../README.md` и
  `.../LICENSE` — назначение и наличие лицензии. Анонимный лимит API 60/ч: часть проверок
  шла через GitHub MCP, часть — через `raw` (лимит не тратит).
- **HF:** `curl https://huggingface.co/api/datasets/{id}` и `/models/{id}` — лицензия,
  `lastModified`, `downloads`; `/api/spaces/{id}` — `runtime.stage`; ключевые CSV скачаны и
  посчитаны (SillyFeed, top-10k, tgAtlas); ссылки на карточки — в §4.
- **Дата:** 2026-11-07. Платформы меняются — перед внедрением перепроверять звёзды/лицензии
  и доступность hosted-ботов.

**Исходные исследования:** [01-github-promo](../../.research/tg/01-github-promo.md) ·
[02-github-analytics](../../.research/tg/02-github-analytics.md) ·
[03-huggingface](../../.research/tg/03-huggingface.md).

---

*Вывод одной фразой: для **живых US/LatAm-каналов** HF практически ничего не даёт по росту
(открытых данных EN/ES нет, а RU-датасеты неприменимы) — работают GitHub-механики
(randymbot, raf, awesome-каталоги), свои метрики `t.me/s` + Bot API и ручной `partner_scan`;
а HF-датасеты SillyFeed/top-10k/tgAtlas пригодятся только когда запустим RU-сеть.*
