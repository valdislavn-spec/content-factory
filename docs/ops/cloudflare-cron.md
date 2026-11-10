# Надёжный планировщик GitHub Actions (Cloudflare Cron)

## Проблема

GitHub Actions `schedule` на free-репозиториях **опаздывает и пропускает слоты**
(наблюдали задержки до 7–10 часов). Из-за этого 4 поста Fediverse в сутки
фактически не выходили: за 10.11 было всего 2 запуска вместо 4.

## Решение

Cloudflare Worker `github-cron` с cron-триггерами вызывает
`workflow_dispatch` нужного workflow в точное время:

| Слот | UTC | Workflow |
|---|---|---|
| Fediverse-микс | 10:17, 14:17, 18:17, 22:17 | `fediverse-mix.yml` |
| Рост Mastodon | 16:17 | `mastodon-growth.yml` |
| Buffer-очередь | 03:10 | `buffer-queue.yml` |
| Tumblr-дайджест | каждые 5 ч (:00) | `tumblr-digest.yml` |

- URL: https://github-cron.valdislav-n.workers.dev
- Код: `infra/cloudflare/github-cron/worker.js`
- Деплой: `bash scripts/deploy_github_cron.sh`
- Ручной запуск: `/trigger?workflow=<file>&token=<ADMIN_TOKEN>`
- GitHub-расписания в этих workflow **убраны**, чтобы не было дублей;
  сами workflow остаются с `workflow_dispatch`.

## Секреты воркера

- `GITHUB_TOKEN` — PAT с правом Actions: write;
- `REPO` = `valdislavn-spec/content-factory`;
- `ADMIN_TOKEN` — защита `/trigger`;
- `REF` = `main`.

## Что менять

- Времена — в `schedules` (CF API) и в логике `scheduled()` воркера;
- новый workflow — добавить в массив `jobs` и в cron-выражение (лимит
  Cloudflare — 3 cron-триггера на Worker).
