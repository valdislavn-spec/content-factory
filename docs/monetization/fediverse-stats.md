# Fediverse-метрики: Mastodon + Akkoma + трекер

Скрипт `scripts/fediverse_stats.py` собирает недельный отчёт:

- **Mastodon** и **Akkoma**: подписчики, подписки, число постов;
- топ-5 постов по вовлечённости (❤/🔁/💬);
- **клики** по трекаемым партнёрским ссылкам (наш Cloudflare-трекер).

Запуск:

```bash
python scripts/fediverse_stats.py            # markdown в data/reports/
python scripts/fediverse_stats.py --json     # JSON в stdout
python scripts/fediverse_stats.py --limit 30 # больше постов
```

Автоматизация: `.github/workflows/fediverse-stats.yml` — каждый понедельник
09:00 UTC, результат в артефакте `fediverse-stats`.

Секреты: `MASTODON_BASE_URL/MASTODON_TOKEN`, `AKKOMA_BASE_URL/AKKOMA_TOKEN`,
`LINK_TRACKER_BASE`, `LINK_TRACKER_STATS_TOKEN`.

Зачем: видеть, какие темы (крипто/AI/travel) и офферы реально дают
вовлечённость и клики, и корректировать ротацию/частоту.
