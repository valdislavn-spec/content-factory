# Telegram-метрики: просмотры, реакции, репосты, ER

Документ про сбор **точных Telegram-метрик** без сайта и без GA4/GSC.
Подходит для каналов, где единственная площадка — Telegram: подписчики,
просмотры постов, реакции, репосты и вовлечённость.

Есть два дополняющих инструмента:

| Инструмент | Что даёт | Telethon |
|---|---|---|
| `scripts/growth_report.py` | ежедневный отчёт роста из публичного `t.me/s` | не нужен |
| `python -m content_factory telegram-metrics` | точные просмотры/реакции/репосты в SQLite + основной отчёт | нужен (опционально) |

## Что собирается

| Метрика | Источник |
|---|---|
| Подписчики | Bot API `getChatMemberCount` |
| Просмотры постов | Telethon (MTProto), `message.views` |
| Реакции | Telethon, сумма всех реакций поста |
| Репосты | Telethon, `message.forwards` |
| Комментарии | Telethon, `message.replies` |
| ER | расчёт: (реакции + репосты) / просмотры × 100 |
| Топ-посты | сортировка по просмотрам |
| Рост подписчиков | разница с предыдущим срезом |

## Установка Telethon

Telethon — необязательная зависимость. Без него собираются только подписчики,
а просмотры/реакции пропускаются.

```bash
./.venv/bin/pip install -r requirements-optional.txt
```

`requirements-optional.txt` содержит `Telethon>=1.34`.

## Ключи и сессия

В `.env`:

```bash
TG_API_ID=123456
TG_API_HASH=abcdef1234567890
TG_SESSION=content_factory
```

`api_id`/`api_hash` — бесплатно на <https://my.telegram.org>.
При первом запуске Telethon попросит номер телефона и код; сессия сохранится
в файл `TG_SESSION` (храните его как пароль, не коммитьте).

Нужен **user-аккаунт**, который состоит в каналах или администрирует их.
Бот-токен для чтения просмотров не подходит — Bot API их не отдаёт.

## Запуск

```bash
# все каналы, последние 30 постов
python -m content_factory telegram-metrics --channel all --limit 30

# один канал
python -m content_factory telegram-metrics --channel sport-news --limit 50
```

Вывод:

```
Telegram-метрики: 3 каналов
  sport-news         подписчиков:    12500 (рост  +120) постов:  30 ср. просмотры:  4200.5 ER:  4.25%
  ...
```

Метрики сохраняются в SQLite:

- `telegram_posts` — по одному посту: `message_id`, `views`, `reactions`,
  `forwards`, `replies`, `posted_at`, `text_preview`, `url`;
- `telegram_channel_metrics` — срезы канала: подписчики, средние просмотры,
  ER, сумма реакций/репостов.

Повторный запуск обновляет существующие посты (upsert), а не дублирует.

## GitHub Actions

Готовый workflow: [`.github/workflows/telegram-metrics.yml`](../.github/workflows/telegram-metrics.yml).
Запускается ежедневно в 09:20 UTC (после growth-report) и вручную
(Actions → telegram-metrics → Run workflow, можно задать `limit`).

Что делает:

1. восстанавливает SQLite из кэша `cf-state-*`;
2. собирает подписчиков через Bot API;
3. если задан секрет с сессией Telethon — просмотры/реакции/репосты/ER;
4. строит `report.html`/`report.md` и загружает их артефактом.

Секреты/переменные:

| Имя | Зачем |
|---|---|
| `TELEGRAM_BOT_TOKEN` | подписчики, getChatMemberCount |
| `TELEGRAM_API_BASE` (Variable) | релей Bot API из РФ (опционально) |
| `TELEGRAM_CHAT_ID_TECH_AI_ES` и др. | chat_id ES-каналов |
| `TG_API_ID`, `TG_API_HASH` | Telethon |
| `TG_SESSION_B64` | сессия Telethon в base64 (опционально) |

Как получить `TG_SESSION_B64`:

```bash
# 1. Локально создайте сессию (Telethon спросит телефон/код):
TG_SESSION=content_factory.session \
  python -m content_factory telegram-metrics --channel sport-news --limit 1

# 2. Закодируйте файл и положите в GitHub Secret TG_SESSION_B64:
base64 -i content_factory.session | tr -d '\n'
```

Workflow декодирует секрет в `data/telegram.session` и передаёт путь в
`TG_SESSION`. Без секрета workflow всё равно соберёт подписчиков; посты
пропустятся.

> Сессия Telethon = доступ к аккаунту. Не коммитьте её, не публикуйте и
> отзывайте при компрометации (завершить сеансы в Telegram → Настройки →
> Устройства).

## В основном отчёте

```bash
python -m content_factory report --days 7
```

В HTML/Markdown появляется раздел **«Telegram-метрики»**: подписчики, рост,
постов проанализировано, средние просмотры, ER, реакции, репосты, лучший пост.

Также `metrics` и `report --collect` вызывают сбор автоматически (если заданы
ключи/токен). Отключить сбор постов можно в `config/settings.yaml`:

```yaml
analytics:
  collect_subscribers: true
  collect_post_metrics: true    # false = не ходить в Telethon
  telegram_posts_limit: 30
```

## Отличие от `growth_report.py`

`scripts/growth_report.py`:

- не требует Telethon;
- берёт публичное превью `t.me/s/<username>`;
- делает отдельный Markdown-отчёт и сводку в Telegram;
- подходит для ежедневного мониторинга и публичных каналов.

`telegram-metrics`:

- точные данные через MTProto (включая приватные каналы, где аккаунт состоит);
- хранит историю в SQLite;
- встраивается в основной отчёт завода;
- требует Telethon и user-сессию.

Если не хотите ставить Telethon — используйте growth report; если нужны точные
метрики в базе и отчёте — `telegram-metrics`.

## TGStat / Telemetr / UTM

- **TGStat/Telemetr** — внешний бенчмарк и поиск каналов; веб бесплатно, API
  обычно платно. Свои просмотры они не заменяют.
- **UTM** — без сайта бесполезны. Если в постах есть ссылки на внешние
  ресурсы (YouTube, VK, Дзен, лендинг), UTM можно добавить, но считать клики
  придётся на стороне получателя.

## Ограничения и безопасность

- Bot API не отдаёт просмотры/реакции — только подписчиков.
- Telethon — MTProto, а не официальный Bot API: используйте отдельный
  user-аккаунт, только свои каналы, без массовых действий и спама.
- Лимиты Telegram и риск ограничений при агрессивном чтении; не запускайте
  сбор чаще раза в сутки на канал.
- Приватные каналы требуют, чтобы аккаунт состоял в канале.
- Просмотры в Telegram могут обновляться с задержкой.
- Не публикуйте `TG_SESSION` и токены; сессия = доступ к аккаунту.
- Для РФ `api.telegram.org` может быть недоступен; используйте
  `TELEGRAM_API_BASE` (релей) или GitHub Actions.

## Если метрик нет

1. Проверьте, что `telethon` установлен: `python -c "import telethon"`.
2. Проверьте `TG_API_ID`, `TG_API_HASH`, `TG_SESSION`.
3. Убедитесь, что user-аккаунт состоит в канале.
4. Для подписчиков: бот — админ канала, `telegram_chat_id` заполнен.
5. Запустите с `--limit 5` и посмотрите лог `data/logs/factory.log`.
