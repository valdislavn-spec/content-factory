# Бесплатная реклама каналов по гео: US / LatAm (ноябрь 2026)

Цель: бесплатно привести первые подписки в 6 живых каналов, разделив кампанию
по гео: **EN-каналы → США**, **ES-каналы → ЛатАм (MX/AR/CO/CL) + Испания**.
Бюджет — 0 ₽. Основной принцип: не накрутка, а дискаверибилити (поиск, каталоги,
кросспостинг) + контент.

Связанные документы: [free-promo-apis.md](../free-promo-apis.md) (API и лимиты),
[free-promo-setup.md](../free-promo-setup.md) (как включить Bluesky/Mastodon/
Discord и growth-бота), [link-placement.md](link-placement.md) (реестр всех
размещений), [catalog-package.md](catalog-package.md) (карточки каналов).

## 1. Что уже сделано (08.11.2026)

| Что | Статус | Где смотреть |
|---|---|---|
| **6 гео-лендингов каналов** (EN → US, ES → LatAm/España) + индекс | ✅ в репозитории, деплой на GitHub Pages | `docs/channels/`, генератор `scripts/build_geo_landing.py` |
| **Sitemap со всеми лендингами** | ✅ | `docs/sitemap.xml` |
| **IndexNow-пинг** всех URL | ✅ (Bing — 200, Яндекс — 202) | `docs/40b6ae40a1da513993ba194f8f2048c5.txt` |
| **Бесплатный каталог besttelegramchannels.com**: 6 каналов подано (EN + ES) | ⏳ на модерации | заявки приняты: «successful! … live shortly after approval» |
| **TeleJoiner (гео-каталог)**: 6/6 каналов опубликованы (US / Mexico, EN/ES) | ✅ live | ссылки в §1a |
| Хаб-лендинг, README, профиль GitHub, topics | ✅ ранее | [link-placement.md](link-placement.md) |

Лендинги: `https://valdislavn-spec.github.io/content-factory/channels/`
(EN: `us-crypto-news-telegram`, `ai-news-telegram-us`, `us-sports-news-telegram`;
ES: `noticias-cripto-telegram`, `noticias-ia-telegram`, `futbol-deportes-telegram`).
На каждой странице — язык, гео-описание, кнопка «Открыть в Telegram» и кнопки
«Поделиться» (Telegram share + X intent) — бесплатная виральная механика.

## 1a. Новые площадки, найденные поиском 08.11.2026

| Площадка | Что это | Статус у нас | Условия |
|---|---|---|---|
| **TeleJoiner** (telejoiner.com) | EN-каталог каналов/групп с фильтрами по категории, языку и **стране** | ✅ **6/6 каналов опубликованы** (проверено live) | Бесплатно, без логина: link, category, country, language, tags, description |
| besttelegramchannels.com | EN-каталог (общий) | ⏳ 6 заявок поданы ранее, ждут модерации | Бесплатно, без логина, нужен PNG-аватар |
| Telegramic.org | Международный каталог (языки/категории) | ☐ не подавали | Бесплатно; модерация долгая (по отзывам до 3 месяцев) |
| TDirectory.me | Крупный каталог каналов/групп/ботов | ☐ не подавали | Бесплатная подача через форму на сайте |
| TGbox.cc | Каталог с авто-обновлением метрик | ☐ не подавали | Бесплатно, через бота **@tgboxccbot** (нужен Telegram-аккаунт) |
| Grupos24h.com | ES-каталог для Испании и ЛатАм | ☐ не подавали | Бесплатная карточка (**обязателен email** владельца) |
| Metricgram community directory | Каталог групп (категории) | ☐ не подавали | Нужен аккаунт/подключённая группа |
| nidium.com → addcatalogbot | Бот-каталог каналов | ☐ не подавали | Через Telegram-бота (нужен аккаунт) |

**TeleJoiner — живые ссылки (08.11.2026):**

- Crypto & Blockchain (US, English): https://telejoiner.com/invite/1003891468537
- AI News (US, English): https://telejoiner.com/invite/1004351191643
- US Sports News (US, English): https://telejoiner.com/invite/1003802742871
- ES Crypto & Blockchain (Mexico, Spanish): https://telejoiner.com/invite/1004304574421
- ES AI News (Mexico, Spanish): https://telejoiner.com/invite/1004355563628
- ES Sports News (Mexico, Spanish): https://telejoiner.com/invite/1004391544104

Вывод: TeleJoiner и besttelegramchannels — единственные найденные каталоги, куда
можно подать **без логина**; у обоих есть гео-поля (страна/язык), что для
«рекламы по гео» важнее общего каталога. Остальные — через Telegram-бота или
нужен email владельца.

## 2. Гео-матрица

| Канал | Гео | Язык | Часы (локальные) | Куда сеять бесплатно |
|---|---|---|---|---|
| Crypto & Blockchain `@HOOPY0007` | США | EN | 07:00–21:00 ET | besttelegramchannels (подано), TelegramChannels.me, tlgrm.eu, awesome-lists, Reddit r/CryptoCurrency, Bluesky/Mastodon EN |
| AI News `@AINEWS0007` | США | EN | 08:00–20:00 ET | те же + r/artificial, r/MachineLearning (правила!), Hacker News (Show/новости), Bluesky EN |
| US Sports News `@SPORTNews0007` | США | EN | 09:00–23:00 ET | те же + r/nfl, r/nba, r/baseball (только по правилам сабов), Bluesky EN |
| ES Crypto `@TechnologiesNews01` | MX/AR/CO/CL + ES | ES | 08:00–22:00 UTC−5 | TeleJoiner ✅ (Mexico), Grupos24h (нужен email), GruposTelegramLatAm (форма 404), TelegramChannels.me (ES-раздел), Bluesky/Mastodon ES, r/mexico, r/argentina, r/Colombia |
| ES AI `@WORLDNews0007` | MX/AR/CO/CL + ES | ES | 08:00–22:00 UTC−5 | те же + r/programacion, r/IA, foros de tecnología ES |
| ES Sports `@SPORTSAnalytics007` | MX/AR/CO/CL + ES | ES | 08:00–23:00 UTC−5 | те же + r/futbol, r/LigaMX, r/fulbo (18+, аккуратно с правилами) |

**Каталоги:** TeleJoiner — ✅ все 6 каналов live (US / Mexico); besttelegramchannels — ⏳ модерация. Полный список новых площадок — §1a.

## 3. Готовые тексты (копировать как есть)

### EN — США / Bluesky, Mastodon, Telegram-чаты (≤300 симв.)

```
US crypto without the noise: Bitcoin, Ethereum, ETF flows, SEC/CFTC regulation.
Daily Telegram digest — free, sourced, no signals.
https://t.me/HOOPY0007
```

```
AI news for US readers: model releases, products, chips, policy.
Daily Telegram channel, sourced from TechCrunch / The Verge / MIT TR.
https://t.me/AINEWS0007
```

```
NFL, NBA, MLB, NHL and college football — scores, trades, injuries, analysis.
Free Telegram channel for US fans: https://t.me/SPORTNews0007
```

### ES — LatAm / Bluesky, Mastodon, foros (≤300 симв.)

```
Cripto en español, sin humo: Bitcoin, Ethereum, mercados y regulación en LatAm y España.
Resumen diario gratis en Telegram → https://t.me/TechnologiesNews01
```

```
IA en español: modelos, productos, empresas y políticas. Para LatAm y España.
Canal diario y gratuito en Telegram → https://t.me/WORLDNews0007
```

```
Fútbol y datos en español: LaLiga, Liga MX, Argentina, MLS y Champions.
Resultados, fichajes y análisis → https://t.me/SPORTSAnalytics007 (18+)
```

### Хэштеги по гео

- EN/US: `#crypto #bitcoin #AI #ArtificialIntelligence #NFL #NBA #sports`
- ES/LatAm: `#criptomonedas #bitcoin #IA #InteligenciaArtificial #fútbol #LaLiga #LigaMX #deportes`

### Красные линии

- Не постить ссылки в сабы/чаты, где самопромо запрещено (бан аккаунта и канала).
- Не покупать «подписчиков/просмотры», не использовать юзерботов и массфолловинг.
- Не дублировать один и тот же текст в 10 местах за час — это спам-паттерн.
- В каждом сообществе — сначала польза (ответ/пост по теме), ссылка в профиле или
  вторым сообщением, если правила разрешают.

## 4. План на 7 дней (0 ₽, 20–30 минут в день)

| День | Действие | Канал/гео |
|---|---|---|
| 1 | Проверить, что лендинги в индексе (Bing/Яндекс по названию канала); дождаться модерации каталога | все |
| 2 | Создать бесплатные аккаунты Bluesky + Mastodon (EN), вписать креды в `.env` → автопостинг включится | EN/US |
| 3 | Создать Bluesky + Mastodon (ES), вписать креды | ES/LatAm |
| 4 | 1 полезный пост в r/artificial или r/CryptoCurrency (без ссылки) + ссылка в профиле | EN/US |
| 5 | 1 пост в r/mexico или r/argentina (по теме, без спама) | ES/LatAm |
| 6 | Подать каналы в TelegramChannels.me и tlgrm.eu (нужен вход через Telegram — вручную) | EN/US |
| 7 | Замер: `python scripts/growth_report.py --send`, сравнить дельту подписчиков; отключить нерабочее | все |

## 5. Что нужно от владельца (одноразово, ~15 минут)

1. **Bluesky** (бесплатно, без ревью): bsky.app → Settings → App Passwords →
   прислать `handle` + `app password` (или вписать в `.env`).
2. **Mastodon** (бесплатно): аккаунт на `mastodon.social` (EN) и
   испаноязычном инстансе (ES) → Preferences → Development → New application →
   `write:statuses` → токен.
3. После этого конвейер сам кросспостит каждый пост в соцсети
   (см. [free-promo-setup.md](../free-promo-setup.md)); реклама каналов
   становится автоматической и бесплатной.
4. Каталоги, где нужен твой Telegram-вход: TGStat, Telemetr, TelegramChannels.me,
   tlgrm.eu, GruposTelegramLatAm, а также боты `tgdr.io`/`tdirectory.me` —
   команда `/add` в боте каталога.
5. Личный профиль Telegram и GitHub website — по [link-placement.md](link-placement.md).

## 6. Атрибуция

- `t.me`-ссылки не поддерживают UTM → считаем дельту подписчиков за 48 ч после
  размещения (`scripts/growth_report.py`), а также переходы на лендинги по
  логам GitHub Pages (если включить аналитику).
- Для точной атрибуции позже: отдельные invite-ссылки под каждую площадку
  (Bot API `createChatInviteLink`) или growth-бот с deep links (`?start=`).
