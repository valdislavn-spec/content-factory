# Мониторинг, алерты и починка с iPhone

## Что уже настроено

| Что | Как | Куда приходит |
|---|---|---|
| Падение публикации | шаг `Notify on failure` в `content-factory.yml` | Telegram @Novyi0007Bot |
| Cloudflare не смог запустить Actions | Worker `tg-cron` → функция `tgAlert` | Telegram |
| Cloudflare Worker упал / запусков нет | **health-endpoint** Worker | UptimeRobot (push/email) → iOS |
| Ежедневный heartbeat 09:00 UTC | workflow `heartbeat` | Telegram: жив, запусков/ошибок за сутки, ссылки на ошибки |
| Бэкап раз в неделю | workflow `backup` | GitHub artifact, хранится 90 дней |

**Health-endpoint:** https://tg-cron.valdislav-n.workers.dev/

Возвращает JSON и HTTP-код:

- `200` — последний запуск content-factory был ≤ 2 часов назад, завершился успешно;
- `503` — запусков нет/старше 2 часов/последний упал → внешний монитор шлёт тревогу.

```bash
curl -s https://tg-cron.valdislav-n.workers.dev/
```

## UptimeRobot (внешний монитор, 5 минут)

1. Зарегистрироваться на uptimerobot.com (Free: 50 мониторов, 5-минутный интервал).
2. Add New Monitor → **HTTP(s)**:
   - URL: `https://tg-cron.valdislav-n.workers.dev/`
   - Interval: 5 минут.
3. Alert contacts: email (push на iPhone через Mail) и/или приложение **UptimeRobot** для iOS.
4. Если health начнёт отдавать 503 — придёт push/письмо; после восстановления придёт «UP».

Дополнительно можно поставить монитор на `https://github.com` (не нужно) — достаточно health-воркера.

## Тест уведомлений

Actions → **heartbeat** → Run workflow. В Telegram должно прийти сообщение со статистикой.
Если сообщения нет — открой @Novyi0007Bot и нажми **Start** (бот не может писать первым).

## Починка с iPhone

1. **GitHub** (iOS) — Actions → красный run → лог → **Re-run failed jobs**; правка `config/*.yaml` и workflow — через github.com в Safari (кнопка Edit).
2. **Telegram** — алерты и посты; здесь же можно быстро написать боту/в канал.
3. **Cloudflare** — dashboard в Safari: Worker `tg-cron`, cron-триггеры, секреты; официальное приложение Cloudflare — для обзора.
4. **UptimeRobot** — push о недоступности (если настроен).
5. **Shortcuts** (опционально) — кнопка, дергающая GitHub workflow_dispatch через API (токен хранить в Shortcuts как секрет).

Типовые причины и что сделать:

| Симптом | Причина | Действие |
|---|---|---|
| В Telegram нет heartbeat | Cloudflare/GitHub токены, Actions отключены | проверить health, GitHub Actions, секреты |
| health 503, запусков нет | Cloudflare cron/токен | Cloudflare dashboard → Worker triggers; проверить секреты |
| run падает на публикации | Telegram токен/бот не админ, лимиты LLM | лог run → исправить секрет/канал, Re-run |
| посты дублируются | гонка запусков/кэш | `delete-messages`, дождаться нового state |
| Actions-минуты кончились | лимит 2000/мес | уменьшить cron, сделать репо публичным |
