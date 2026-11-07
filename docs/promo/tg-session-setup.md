# Как включить автоматическую отправку ВП (Telethon user-session)

Бот не может писать первым чужим владельцам каналов — нужен вход **от аккаунта
человека** через user-session. Это делается один раз, ~5 минут.

## Шаг 1. Получить TG_API_ID и TG_API_HASH

1. Открой https://my.telegram.org (нужен вход по номеру телефона).
2. **API development tools** → заполни: App title (например `content-factory`),
   Short name (`cfactory`), Platform (`Desktop`) → Create application.
3. Скопируй **api_id** (число) и **api_hash** (строка).

## Шаг 2. Создать TG_SESSION на своём компьютере

```bash
cd ~/Documents/deepseek-harness/default-workspace/content-factory
./.venv/bin/pip install "Telethon>=1.34"
./.venv/bin/python scripts/make_tg_session.py
```

Скрипт спросит:
- `TG_API_ID` и `TG_API_HASH` — из шага 1;
- телефон в формате `+7999...`;
- код из Telegram (придёт в приложение);
- пароль 2FA, если включён.

В конце выведет строку `TG_SESSION` — **скопируй её целиком в одну строку**.

> Если терминал не подключается к Telegram (блокировка сети) — включи VPN
> и повтори, либо выполни шаг с телефона/другого устройства. Скрипт только
> логинится и печатает сессию; посты он не публикует.

## Шаг 3. Добавить 3 секрета в GitHub

GitHub → репозиторий `content-factory` → **Settings → Secrets and variables →
Actions → New repository secret**:

| Имя | Значение |
|---|---|
| `TG_API_ID` | число из шага 1 |
| `TG_API_HASH` | строка из шага 1 |
| `TG_SESSION` | строка из шага 2 |

## Шаг 4. Запустить рассылку

Actions → **vp-outreach** → Run workflow:

1. `region: en`, `limit: 3`, `dry_run: true` — проверить, что сообщения выходят в лог;
2. `dry_run: false` — реальная отправка 3 сообщений (пауза 20–45 с);
3. повторить для `region: es`, `limit: 2` (там платные офферы).

Сообщения и адресаты — в `docs/promo/vp-messages-final-2026-11-08.md`,
контакты — в `docs/promo/outreach-tracker.csv`.

## Безопасность

- `TG_SESSION` = полный доступ к аккаунту. Только в GitHub Secrets, не в файлах
  репозитория и не в чатах.
- Если строка засветилась: Telegram → Settings → Devices → завершить сеанс
  (и при необходимости сменить пароль 2FA), затем создать новую сессию.
- Лимиты: 3–5 новых контактов в день, ответа ждать 2–3 дня. Иначе — ограничение
  аккаунта за спам.
