# Growth Funnel publisher

Автопубликация очереди GOODTRAVEL007.

- D1-очередь: `https://links-tracker.valdislav-n.workers.dev/admin/queue`
- `auto_publish.py` — публикатор Telegram (GitHub Actions).
- `pinterest_playwright_publish.cjs` — Pinterest fallback через UI.
- `pinterest_scheduler.cjs` — локальный планировщик Pinterest, раз в 6 часов.
- `travel_report.py` — ежедневный отчёт по воронке.
- `build_future_pins.py` — генерация следующих Pinterest-пинов.
- `AUTOMATION.md` — полная схема, команды и ограничения.

Workflow:

- `.github/workflows/growth-funnel.yml` — Telegram, 09:05 UTC;
- `.github/workflows/travel-report.yml` — отчёт, 09:30 UTC;
- `.github/workflows/deploy-surge.yml` — лендинг `travel-finds.surge.sh`.

Pinterest API ждёт Standard access. Пока работает локальный Playwright
fallback с профилем `tools/playwright-mcp/profile-tp2`.

Секреты GitHub: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_API_BASE`,
`LINK_TRACKER_ADMIN_TOKEN`, `GROWTH_STATS_TOKEN`, `PINTEREST_ACCESS_TOKEN`
(на будущее), `SURGE_LOGIN`, `SURGE_TOKEN`.
