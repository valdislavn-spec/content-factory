# Публикация через GitHub Actions (EN + ES)

Локальная сеть блокирует `api.telegram.org` (и OpenAI/Groq по региону), а
раннеры GitHub Actions — нет. Поэтому публикация целиком живёт в облаке:
workflow **`content-factory-cloud-en-es`** по слотам каналов запускает
`daemon --once` и публикует посты. Один cron, матрица языков `lang = [en, es]`:
английские и испанские каналы обслуживаются независимыми джобами.

## Что уже готово в репозитории

- `.github/workflows/content-factory.yml` — workflow **`content-factory-cloud-en-es`**:
  - матрица `lang: [en, es]`; `en` → `config/channels.en.yaml` (6 каналов,
    16 слотов/сутки), `es` → `config/channels.es.yaml` (3 канала,
    6 слотов/сутки);
  - каждый язык — свой кэш состояния (`cf-state-<lang>-*`), свой concurrency
    и свои artifacts (`content-factory-<lang>-<run>`);
  - публикация включена по умолчанию (dry-run — переменная
    `CONTENT_FACTORY_DRY_RUN=true`).
- `.github/workflows/telegram-check.yml` — ручная проверка бота и прав в
  каналах (вход `language`: `en`/`es`).
- `.github/workflows/publish-once.yml` — ручная публикация одного поста
  (входы: `channel`, `language`, `dry_run`).
- `.github/workflows/set-title.yml` — ручная смена названия канала
  (`setChatTitle`; входы: `chat_id`, `title`).
- Английские каналы в `config/channels.en.yaml` прописаны числовыми ID;
  испанские — chat_id берутся из секретов (см. ниже).

## 1. Репозиторий

Приватный репозиторий `content-factory` уже создан и запушен
(SSH-ключ этой машины авторизован в GitHub, аккаунт `valdislavn-spec`).

## 2. Секреты

Settings → Secrets and variables → Actions → **Secrets** (по одному):

| Secret | Откуда взять |
|---|---|
| `TELEGRAM_BOT_TOKEN` | токен @Novyi0007Bot (уже в `.env`) |
| `TELEGRAM_CHAT_ID_TECH_AI_ES`, `TELEGRAM_CHAT_ID_CRYPTO_ES`, `TELEGRAM_CHAT_ID_FUTBOL_ES` | ID/`@username` испанских каналов (без них ES-каналы пропускаются) |
| `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` | Cloudflare Workers AI |
| `OLLAMA_API_KEY` | Ollama Cloud (open-модели) |
| `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `SAMBANOVA_API_KEY`, `HUGGINGFACE_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY` | резервные LLM (на раннере доступны и заблокированные в РФ) |
| `NEWSDATA_API_KEY`, `GDELT_CLOUD_API_KEY`, `TAVILY_API_KEY`, `TAVILY_API_KEY_2` | новостные/поисковые API |
| `DIFY_API_KEY`, `DIFY_POSTS_API_KEY` | если используется Dify |

Значения — из `.env` (файл в git не попадает). Пустые секреты безопасны:
источник/провайдер просто пропускается.

## 3. Режим публикации

Settings → Secrets and variables → Actions → **Variables**:

- по умолчанию workflow **публикует по-настоящему** (в workflow
  `CONTENT_FACTORY_DRY_RUN: ${{ vars.CONTENT_FACTORY_DRY_RUN || 'false' }}`);
- `CONTENT_FACTORY_DRY_RUN = true` — безопасный dry-run (посты только в
  outbox/artifacts, в Telegram не уходят).

## 4. Проверка и первый пост

1. Actions → **telegram-check** → Run workflow:
   - `language = en` → бот `@Novyi0007Bot` и 6 каналов со статусом
     `administrator`, `can_post=True`;
   - `language = es` → 3 испанских канала (если chat_id заданы).
2. Actions → **publish-once** → Run workflow:
   `channel = ai-news`, `language = en`, `dry_run = false`.
3. После этого cron **`content-factory-cloud-en-es`** сам публикует по
   расписанию каналов (EN — 16 слотов/сутки, ES — 6 слотов/сутки).

## Ограничения

- GitHub cron запускается с задержкой 5–15 минут; испанские слоты
  (07:00/08:00, 10:00/11:00 … MSK) догоняются ближайшим запуском общего cron —
  задержка до ~1.5 часов.
- Матрица — это **два джоба на каждый cron**: для приватного репозитория
  следите за минутами (16 cron/сутки × 2 джоба). Если упираетесь в лимит
  2000 мин/мес: уменьшите слоты, уберите `es` из матрицы на время или сделайте
  репозиторий публичным (секреты остаются секретами).
- Кэш `actions/cache` эфемерный: при редких запусках состояние может
  откатываться; дубли отсекаются окном `post_duplicate_window_hours`.
- Русские каналы (`config/channels.yaml`) в этот workflow не входят. Чтобы
  добавить: `lang: [en, es, ru]` + `TELEGRAM_CHAT_ID_*` для ru-каналов.
