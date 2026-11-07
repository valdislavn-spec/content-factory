# План запуска канала «Спорт-аналитика и ставки»

Дата: 08.11.2026. Цель: отдельный EN-канал про спортивные данные, коэффициенты и
аналитику рынков (18+), с монетизацией через букмекерские CPA/партнёрки.

## Решение (принято 08.11.2026): добавляем в существующий ES-канал

Новый канал не создаём. Аналитика и ставки (18+) добавляются в текущий
`futbol-es` — он же `@SPORTSAnalytics007`, ID `-1004391544104`
(прежнее название «ES Sports News»). Канал уже заведён, бот админ, а
юзернейм `SPORTSAnalytics007` точно подходит под тему.

Что изменено в `config/channels.es.yaml` (ветка `fix/content-gates`):

- title → **ES Sports Analytics**, описание — данные/аналитика/куоты, 18+;
- topics += `apuestas deportivas, cuotas, probabilidad, hándicap, valor
  esperado, análisis de datos, pronóstico, mercado de apuestas, bankroll,
  modelo estadístico`;
- из `exclude_keywords` убрано `apuestas`; добавлены защитные стоп-слова
  (`apuesta segura`, `partido arreglado`, `ganancia garantizada`,
  `bono casino`, `código promocional casino`);
- `tone: science`, CTA: `18+ | Juega con responsabilidad…`;
- добавлен источник `newsdata-apuestas` (запрос `apuestas deportivas cuotas
  análisis`, `language: es`, `daily_limit: 100`) — ключ newsdata в Actions есть.

Применить title/description в Telegram: Actions → `apply-profile` →
language: `es` (после merge конфига).

## Шаг 1. Канал и доступ

1. Создать публичный канал (EN, гео US), аватар/описание с ключами:
   «sports betting analytics, odds, NFL/NBA/MLB picks, data models, 18+».
2. Добавить бота-публішера админом с правами публикации.
3. Получить numeric ID (бот должен быть админом; `getChat` → `-100…`).
4. Внести в `config/channels.en.yaml` (пример ниже) на ветке, не в main.

## Шаг 2. Конфиг (готовый фрагмент)

```yaml
- id: betting-analytics
  title: Sports Betting Analytics
  description: >-
    Odds, data models and evidence-based betting analysis for NFL, NBA, MLB.
    Research, not tips. 18+ | Bet responsibly.
  telegram_chat_id: '-100XXXXXXXXXX'
  language: en
  topics: [sports betting, odds, implied probability, line movement, nfl, nba,
           mlb, model, value bet, market, closing line, bankroll]
  exclude_keywords: [guaranteed win, fixed match, sure bet, casino, free money,
                     spam, promo code]
  tone: science
  hashtags: [Betting, SportsAnalytics, Odds]
  cta: '18+ | Bet responsibly'
  formats: [analysis, story, digest]
  schedule: ['12:00','13:30','15:00','16:30','18:00','19:30','21:00','22:30']
  posts_per_day: 8
  timezone_offset: -5
  min_relevance: 0.25
  min_cluster_chars: 400
  sources:
    - {id: espn-nfl, type: espn, url: https://site.api.espn.com/apis/site/v2/sports/football/nfl/news, name: ESPN/NFL, weight: 1.2, options: {sport: football/nfl, max_items: 10}}
    - {id: espn-nba, type: espn, url: https://site.api.espn.com/apis/site/v2/sports/basketball/nba/news, name: ESPN/NBA, weight: 1.1, options: {sport: basketball/nba, max_items: 10}}
    - {id: guardian-sport, type: rss, url: https://www.theguardian.com/uk/sport/rss, name: Guardian/Sport, weight: 1.0, options: {max_items: 8}}
    - {id: newsdata, type: newsdata, url: https://newsdata.io/api/1/latest, name: newsdata.io, weight: 1.0, options: {query: 'sports betting odds analysis', language: en, max_items: 10, daily_limit: 100}}
```

## Шаг 3. Контент (не «ставки-прогнозы»)

- Форматы, которые не банят и не обманывают: объяснение линии, движение
  коэффициентов, implied probability, банкролл-менеджмент, разбор матча по данным.
- Запрещено: гарантированные прогнозы, «договорные матчи», накрутка, продажа
  «инсайдов». Дисклеймер 18+ в каждом посте/закрепе.
- Юридическое: проверить правила Telegram по гемблингу и локальные ограничения
  (US-штаты), не давать персональные инвестиционные рекомендации.

## Шаг 4. Запуск и рост

1. 2 недели — контент без партнёрок, 8 постов/сутки, закрепы.
2. Кросс-промо: 1 пост в crypto-канале (3,6 тыс.) + 1 в US Sports (аудитория
   пересекается), 2–3 кросс-поста/нед.
3. Каталоги: TGStat, TelegramChannels.me, tlgrm.eu (спортивные разделы).
4. Канал добавляется в каталоги сети и в growth-report.

## KPI и монетизация

| Срок | Цель |
|---|---|
| 30 дней | 100–200 подписчиков, 20+ просмотров/пост |
| 60 дней | 500 подписчиков, рекламные посты $5–10 |
| 90 дней | первая партнёрка (CPA/RevShare), 2 рекламодателя |

Риски: гемблинг-реклама ограничена в ряде гео; низкий доверительный уровень →
больше «аналитики», меньше «прогнозов». Приоритет безопасности — не публиковать
промокоды казино.
