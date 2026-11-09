# Telegram Health: наш скрипт проверки аккаунта и бота

Дата: 09.11.2026. Сделано «своё» вместо готовых скриптов с GitHub — с учётом наших
каналов, VPN-доступа и требования **не навредить аккаунту**.

## Что делает

`scripts/tg_account_health.py` — два режима:

| Режим | Что проверяет | Нужен вход в аккаунт |
|---|---|---|
| `bot` | бот жив (`getMe`), админ-права в 6 каналах, частота постов, affiliate-раскрытие, рискованные сессии/паттерны | нет (только Bot API) |
| `user` | @SpamBot (`/start`), активные сессии (`account.GetAuthorizations`), 2FA, число администрируемых каналов | да (наша Telethon-сессия) |
| `auto` | bot + user, если сессия найдена | — |

Оценка **0–100** и рекомендации: ограничения @SpamBot, лишние сессии, 2FA, flood-wait.

```bash
./.venv/bin/python scripts/tg_account_health.py            # bot + user (если есть сессия)
./.venv/bin/python scripts/tg_account_health.py --mode bot # только Bot API
./.venv/bin/python scripts/tg_account_health.py --json
./.venv/bin/python scripts/tg_account_health.py --out docs/reports/tg-health.md
```

Сессия для user-режима: `TG_SESSION_STRING` (StringSession) или
`data/content_factory.session`. Без неё user-режим аккуратно пропускается с подсказкой —
локально сессии нет, она создаётся workflow
[`tg-session.yml`](../../.github/workflows/tg-session.yml) на GitHub Actions (там Telegram
доступен), строка кладётся в секрет `TG_SESSION`.

## Безопасность (почему это не приведёт к бану)

- user-режим: **только чтение** + один `/start` официальному `@SpamBot` (это его штатный
  сценарий); никаких сообщений людям/каналам, вступлений, парсинга, массовых действий.
- Bot-режим: только `getMe`/`getChatMember` — read-only Bot API.
- IP сторонних сессий маскируются (`1.2.*.*`), телефон сокращается (`+7…98`).
- Никаких tdata/чужих сессий (в отличие от «tdata checker» скриптов — это про украденные
  сессии, нам не нужно).
- Flood-wait (429 `retry_after`) парсится, но скрипт не ретраит сам — только сообщает.

## Чем отличается от готовых скриптов с GitHub

Смотрели живые проекты (09.11.2026):

| Проект | Что делает | Почему не взяли целиком |
|---|---|---|
| [bellingcat/telegram-phone-number-checker](https://github.com/bellingcat/telegram-phone-number-checker) ★1.9k | проверка регистрации номеров (OSINT) | не про здоровье аккаунта; нам не нужен перебор номеров |
| tdata/session-checker’ы (например, `TDataChecker-V2`) | аудит tdata/сессий, premium | tdata — это файлы чужих/украденных сессий; используем только свою официальную Telethon-сессию |
| «spam/bulk» userbot-репозитории | рассылки/накрутка | прямо ведёт к бану — не используем |
| [Telethon docs](https://docs.telethon.dev/) `account.GetAuthorizations` | официальный API сессий | берём как источник методов, обвязка — своя |

Наш плюс: один отчёт для **бота и аккаунта**, маскирование чувствительных данных,
интеграция с нашими каналами (6 EN/ES), affiliate-дисклеймеры и частота постов,
ничего не меняет в аккаунте.

## Что добавить дальше (по желанию)

1. Запуск `--mode user` в GitHub Actions раз в неделю и коммит отчёта в `docs/reports/`.
2. Алерт в Telegram-чат админа, если @SpamBot вернул `limited` или появилась новая
   подозрительная сессия.
3. Проверка «застрявших» постов (429/flood) по логам пайплайна.
