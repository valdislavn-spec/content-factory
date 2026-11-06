# Публикация через GitHub Actions

Локальная сеть блокирует `api.telegram.org` (и OpenAI/Groq по региону), а
раннеры GitHub Actions — нет. Поэтому публикацию можно целиком перенести в
облако: workflow раз в 10 минут проверяет расписание каналов и публикует посты.

## Что уже готово в репозитории

- `.github/workflows/content-factory.yml` — cron каждые 10 минут:
  `daemon --once`, состояние (SQLite, слоты, кэш LLM) сохраняется через
  `actions/cache`, outbox/логи уходят в artifacts.
- `.github/workflows/telegram-check.yml` — ручная проверка бота и прав в
  каналах (Actions → telegram-check → Run workflow).
- `.github/workflows/publish-once.yml` — ручная публикация одного поста в
  выбранный канал (входы: `channel`, `dry_run`).
- Английские каналы в `config/channels.en.yaml` уже прописаны числовыми ID,
  поэтому отдельные `TELEGRAM_CHAT_ID_*` для них не нужны.

## 1. Создать репозиторий

На github.com создайте **пустой приватный** репозиторий (без README),
например `content-factory`, и запушьте проект:

```bash
cd ~/Documents/deepseek-harness/default-workspace/content-factory
git remote add origin git@github.com:<username>/content-factory.git
git push -u origin main
```

SSH-ключ этой машины уже авторизован в GitHub (аккаунт `valdislavn-spec`).

## 2. Добавить секреты

Settings → Secrets and variables → Actions → **Secrets** (по одному):

| Secret | Откуда взять |
|---|---|
| `TELEGRAM_BOT_TOKEN` | токен @Novyi0007Bot (уже в `.env`) |
| `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` | Cloudflare Workers AI |
| `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `SAMBANOVA_API_KEY`, `HUGGINGFACE_API_KEY`, `OPENAI_API_KEY` | ключи LLM (на раннере доступны, из РФ — нет) |
| `NEWSDATA_API_KEY`, `GDELT_CLOUD_API_KEY`, `TAVILY_API_KEY`, `TAVILY_API_KEY_2` | новостные/поисковые API |
| `DIFY_API_KEY`, `DIFY_POSTS_API_KEY` | если используется Dify |

Значения — из `.env` (файл в git не попадает). Пустые секреты безопасны:
источник/провайдер просто пропускается.

## 3. Режим публикации

Settings → Secrets and variables → Actions → **Variables**:

- `CONTENT_FACTORY_DRY_RUN = false` — реальная публикация;
- не задана или `true` — безопасный dry-run (посты в artifacts).

## 4. Проверка и первый пост

1. Actions → **telegram-check** → Run workflow. В логе должно быть
   `Бот: @Novyi0007Bot` и 6 каналов со статусом `administrator` и
   `can_post=True`.
2. Actions → **publish-once** → Run workflow:
   `channel = ai-news`, `dry_run = false`. Проверьте канал — должен выйти
   один пост.
3. После этого cron-воркфлоу `content-factory-cloud` сам публикует по
   расписанию каналов (16 слотов/сутки, UTC).

## Ограничения

- GitHub cron запускается с задержкой 5–15 минут; для новостей это нормально.
- Кэш `actions/cache` эфемерный: при редких запусках состояние может
  откатываться, дубли отсекаются окном `post_duplicate_window_hours`.
- GitHub Actions бесплатен для приватных репозиториев в пределах лимита
  минут (2000/мес); 10-минутный cron укладывается в лимит с запасом.
- Русские каналы (`config/channels.yaml`) в этом workflow не публикуются:
  он читает `app.channels_file` из `config/settings.yaml`
  (`config/channels.en.yaml`). Испанские каналы — отдельный workflow с
  `CONTENT_FACTORY_CHANNELS=config/channels.es.yaml`, когда дойдём до них.
