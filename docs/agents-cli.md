# Google Agents CLI: установка и использование

Установлен `google-agents-cli` (Agents CLI) — инструмент Google для сборки,
оценки и деплоя ADK-агентов на Gemini/Google Cloud. Он не нужен для работы
контент-завода, но может пригодиться для агентных экспериментов.

## Что было выполнено

```bash
# uv/uvx не было в системе — поставили uv в venv проекта
content-factory/.venv/bin/pip install uv

# запуск через uvx с Python 3.12 (системный 3.9 не подходит)
UV_CACHE_DIR=... UV_TOOL_DIR=... UV_PYTHON_INSTALL_DIR=... \
  content-factory/.venv/bin/uvx --python 3.12 google-agents-cli setup \
  --skip-auth --workspace
```

Флаги:

- `--workspace` — скиллы установлены в `content-factory/.agents/skills`,
  а не глобально;
- `--skip-auth` — **вход в Google не выполнялся**, доступ к аккаунту,
  Gmail, контактам и Google Cloud не запрашивался;
- `AGENTS_CLI_TELEMETRY=0`, `DO_NOT_TRACK=1` — телеметрия отключена.

## Что установлено

- `agents-cli` v1.13.0 → `.uv-bin/agents-cli`
  (симлинк на `.uv-tools/google-agents-cli/`);
- 7 скиллов в `content-factory/.agents/skills/`:
  `adk-code`, `deploy`, `eval`, `observability`, `publish`, `scaffold`, `workflow`;
- скиллы также слинкованы в обнаруженные агенты (Zed, OpenClaw, Devin,
  Windsurf).

## Проверка

```bash
cd /Users/vd/Documents/deepseek-harness/default-workspace
.uv-bin/agents-cli --version
.uv-bin/agents-cli info
```

## Команды

```bash
.uv-bin/agents-cli --help
.uv-bin/agents-cli create my-agent -y
.uv-bin/agents-cli run "твой промпт"
.uv-bin/agents-cli eval run
.uv-bin/agents-cli deploy
```

Для локальной работы без Google Cloud нужен API-ключ AI Studio
(`GEMINI_API_KEY`/AI Studio); для деплоя — Google Cloud проект.

## Важно

- `setup` с `--skip-auth` не трогал Google-аккаунт и контакты.
- Не запускайте `agents-cli login`, пока не готовы дать доступ к Google
  Cloud/AI Studio.
- Скиллы выполняются с правами агента; просмотрите их перед использованием.
