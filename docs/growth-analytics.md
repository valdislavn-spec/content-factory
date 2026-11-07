# Аналитика роста каналов

Ежедневный срез по всем каналам сети **без Telethon и без ручного экспорта**:
подписчики, просмотры на пост, реакции, ER, посты за 24 часа, дельты к
предыдущему снимку и лучший пост. Отчёт сохраняется в Markdown и отправляется
короткой сводкой в Telegram.

## Как работает

1. `scripts/growth_report.py` берёт каналы из `config/channels.en.yaml` и
   `config/channels.es.yaml` (числовые ID в конфигах).
2. Через Bot API `getChat` резолвит `@username` канала (кэш —
   `data/analytics/growth/usernames.json`) и `getChatMemberCount` даёт **точное**
   число подписчиков.
3. Скачивает публичную страницу `https://t.me/s/<username>` и разбирает её
   (`content_factory/analytics/preview.py`): подписчики, последние ~20 постов,
   просмотры, реакции, даты, текст.
4. Сравнивает с последним снимком из `data/analytics/growth/history.jsonl` и
   считает дельты (`content_factory/analytics/growth.py`).
5. Пишет `data/reports/growth-YYYY-MM-DD.md`, печатает Markdown и (с `--send`)
   отправляет короткую сводку в `TELEGRAM_ALERT_CHAT_ID`.

В GitHub Actions работает workflow `growth-report` (ежедневно 09:10 UTC +
ручной запуск). История между запусками сохраняется через `actions/cache`;
локально — в `data/analytics/growth/`.

## Метрики

| Метрика | Откуда | Комментарий |
|---|---|---|
| Подписчики | Bot API `getChatMemberCount` | точные, в отличие от «3.67K» в превью |
| Δ за сутки | сравнение снимков | пусто, если предыдущего снимка нет |
| Просмотры/пост | `t.me/s` | среднее по окну 24 ч; если постов <3 — по последним ~20 |
| ER (реакции/просмотры) | `t.me/s` | Telegram Ads-реакции тоже попадают; ER 20–50% — повод проверить накрутку |
| Просмотры/подписчик | расчёт | показывает «живость» аудитории (норма для новостей ~5–15%) |
| Постов/24 ч | `t.me/s` | сколько канал реально опубликовал |
| Лучший пост | `t.me/s` | максимум просмотров в окне, со ссылкой |

> Telegram Bot API не отдаёт просмотры и реакции. Для приватных каналов или
> полной истории нужен Telethon (`TG_API_ID`/`TG_API_HASH`/`TG_SESSION`) — он
> остаётся опциональным путём в `content_factory/analytics/collector.py`.

## Запуск

```bash
# локально: отчёт в консоль + data/reports/growth-YYYY-MM-DD.md
python scripts/growth_report.py

# ещё и короткая сводка в Telegram
python scripts/growth_report.py --send

# быстрее/короче
python scripts/growth_report.py --limit 10 --timeout 10

# только файл, без Markdown в консоль
python scripts/growth_report.py --quiet
```

В GitHub: **Actions → growth-report → Run workflow** (режим всегда «live»,
dry-run тут не нужен — бот ничего не публикует).

Переменные окружения: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALERT_CHAT_ID`
(секреты репозитория уже используются heartbeat'ом). Для запуска из РФ —
`TELEGRAM_API_BASE=https://telegram-proxy.valdislav-n.workers.dev`, но `t.me`
из РФ обычно недоступен, поэтому основной канал запуска — GitHub Actions.

## Файлы

| Файл | Назначение |
|---|---|
| `content_factory/analytics/preview.py` | парсер и загрузчик `t.me/s` (только stdlib) |
| `content_factory/analytics/growth.py` | снимки, дельты, Markdown/Telegram-формат |
| `scripts/growth_report.py` | CLI: Bot API + превью + сохранение + отправка |
| `tests/test_growth.py` | тесты парсера и снимков на реальной фикстуре `tests/fixtures/tme_preview.html` |
| `.github/workflows/growth-report.yml` | ежедневный запуск и кэш истории |

## Ограничения

- `t.me/s` показывает ~20 последних постов; у канала с 15 постами/сутки окно
  фактически меньше суток — поэтому «посты/24 ч» считается по датам постов.
- Просмотры на странице превью могут отставать на десятки минут.
- Если превью недоступно (бан/приватный канал), отчёт покажет хотя бы точных
  подписчиков из Bot API и строку «превью недоступно».
- История в Actions-кэше: если кэш вытеснен (7 дней без запусков), дельты
  теряются за один день — это не влияет на сами метрики.
