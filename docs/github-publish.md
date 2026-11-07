# Публикация через GitHub Actions (EN + ES)

Локальная сеть блокирует `api.telegram.org` (и OpenAI/Groq по региону), а
раннеры GitHub Actions — нет. Поэтому публикация целиком живёт в облаке:
workflow **`content-factory-cloud-en-es`** по слотам каналов запускает
`daemon --once` и публикует посты. Один cron, **один джоб**: сначала EN-тик,
затем ES-тик (если заданы chat_id) — вдвое меньше минут Actions, чем матрица
из двух джобов.

## Что уже готово в репозитории

- `.github/workflows/content-factory.yml` — workflow **`content-factory-cloud-en-es`**:
  - плавающее расписание: 16 запусков/сутки со сдвигом +2…+19 минут от ровного
    часа (посты не выходят в одинаковые минуты);
  - EN → `config/channels.en.yaml` (3 канала, 16 слотов/сутки = 48 постов),
    затем ES → `config/channels.es.yaml` (3 канала, 6 слотов/сутки = 18 постов);
  - общий кэш состояния (`cf-state-*`), один concurrency, один artifact;
  - cron публикует live; **ручной запуск — dry-run по умолчанию**, live только
    при явном выборе `publish=live`;
  - ES-тик работает сразу: ID испанских каналов прописаны в `channels.es.yaml`.
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
   - `language = en` → бот `@Novyi0007Bot` и 3 EN-канала (`administrator`, `can_post=True`);
   - `language = es` → 3 испанских канала с теми же правами.
2. Actions → **publish-once** → Run workflow:
   `channel = ai-news`, `language = en`, **`dry_run = true`** (по умолчанию) —
   безопасная проверка. Для реальной публикации осознанно выберите `false`.
3. Actions → **content-factory-cloud-en-es** → Run workflow: по умолчанию
   `dry-run` (проверка без постов). Для боевого ручного прогона выберите
   `publish = live`.
4. Дальше cron **`content-factory-cloud-en-es`** сам публикует по расписанию
   каналов (EN — 16 слотов/сутки, ES — 6 слотов/сутки).

## Ограничения

- Плавающее расписание: 16 запусков/сутки; GitHub может задержать запуск на
  5–15 минут. Испанские слоты (ES) догоняются ближайшим запуском — задержка до
  ~1.5 часов.
- Один джоб на запуск (EN, затем ES) — это ~3–5 минут: ≈ 60–80 минут в день,
  ≈ 1800–2400 минут/мес. Для приватного репозитория (лимит 2000 мин/мес)
  следите за расходом; при риске: уменьшите число слотов EN или временно
  уберите ES-тик, либо сделайте репозиторий публичным (секреты остаются
  секретами).
- Кэш `actions/cache` эфемерный: при редких запусках состояние может
  откатываться; дубли отсекаются окном `post_duplicate_window_hours`.
- Русские каналы (`config/channels.yaml`) в этот workflow не входят. Чтобы
  добавить: отдельный шаг с `CONTENT_FACTORY_CHANNELS=config/channels.yaml` и
  `TELEGRAM_CHAT_ID_*` для ru-каналов.
