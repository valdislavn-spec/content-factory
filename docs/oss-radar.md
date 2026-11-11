# OSS Radar: рубрика «свежие open-source релизы» (0 ₽)

Готовый инструмент для `ai-news` (EN) и `tech-ai-es` (ES): собирает новые релизы
open-source проектов и готовит Telegram-пост. **Сам ничего не публикует** — только
печатает/сохраняет готовый текст, публикацию решает пайплайн или редактор.

## Зачем

Наши tech-каналы живут новостями; «что вышло за сутки/неделю в open source» — дешёвая
регулярная рубрика без LLM и без платных API. Источник — GitHub Releases API:
бесплатно, без ключа, с release notes и датами.

## Быстрый старт

```bash
# суточный дайджест для EN-канала (без ключей, анонимный лимит 60 запросов/час)
./.venv/bin/python scripts/oss_radar.py --channel ai-news --hours 24

# испанская версия для тех же релизов
./.venv/bin/python scripts/oss_radar.py --channel tech-ai-es --hours 48 --limit 8

# оба канала + сохранить HTML/TXT в каталог
./.venv/bin/python scripts/oss_radar.py --channel all --hours 48 --out data/reports/oss-radar

# машинный вывод (для интеграции с пайплайном)
./.venv/bin/python scripts/oss_radar.py --channel ai-news --hours 24 --json

# включить prerelease/beta-релизы (по умолчанию в конфиге уже включены)
./.venv/bin/python scripts/oss_radar.py --channel all --include-prereleases
```

Выход: заголовок, список `• репозиторий — версия`, ссылки и хэштеги
(`#opensource #ai #github` для EN, `#opensource #IA #github` для ES). Pre-release
помечается `(pre-release)`.

## Что внутри

| Файл | Роль |
|---|---|
| `content_factory/oss_radar.py` | GitHub/libraries.io клиенты, кэш, отбор за N часов, рендер EN/ES |
| `scripts/oss_radar.py` | CLI: каналы, часы, лимит, JSON, сохранение |
| `config/oss_radar.yaml` | список репозиториев на канал, `per_repo`, `include_prereleases`, запросы libraries.io |
| `tests/test_oss_radar.py` | 17 тестов без сети (моки API, кэш, рендер, конфиг) |

## Лимиты и кэш

- **GitHub без ключа**: 60 запросов/час. Один полный прогон двух каналов = 12 запросов
  (репозитории общие, забираются один раз).
- **С `GITHUB_TOKEN`** в `.env` — 5000/час (в GitHub Actions токен уже есть).
- Ответы кэшируются в `data/cache/oss_radar/` на **1 час** (TTL): повторный запуск в тот же
  час не тратит лимит; при `403/429` отдаётся устаревший кэш с предупреждением.
- `--refresh` игнорирует кэш.

## Настройка

`config/oss_radar.yaml`:

```yaml
channels:
  ai-news:
    language: en
    max_items: 8          # сколько релизов в посте
    per_repo: 1           # максимум релизов одного репозитория (0 = все)
    include_prereleases: true
    repos: [ollama/ollama, huggingface/transformers, ...]
```

Добавить/убрать канал или репозиторий — просто отредактировать YAML; неизвестный канал
даст понятную ошибку со списком доступных.

## libraries.io (опционально)

Для «кросс-экосистемного» фида (PyPI/npm/crates одним запросом) можно добавить ключ:

```bash
# .env
LIBRARIES_IO_API_KEY=...
```

```bash
./.venv/bin/python scripts/oss_radar.py --channel ai-news --source all --hours 24
```

Ключ бесплатный: вход на [libraries.io](https://libraries.io) через GitHub → Account → API key.
Без ключа `--source libraries_io` вернёт понятную ошибку; `--source all` работает как `github`
с предупреждением. Лимит — 60 запросов/мин.

## Ограничения и правила

- Пост — **не новость**, а «радар»: версии/ссылки. Не выдавать за эксклюзив, не добавлять
  кликбейт; для `tech-ai-es` — испанский заголовок и подписи.
- Не публиковать `(pre-release)` как стабильный релиз: маркер уже проставлен.
- Не запускать чаще 1 раза в час при анонимном GitHub-лимите.
- Один пост на канал за запуск; на Free-плане каналов не касается (рубрика бесплатна).

## Следующий шаг (если рубрика зайдёт)

Подключить как источник в пайплайне `ai-news`/`tech-ai-es` (1 пост в сутки/неделю,
`formats: digest`), с проверкой редактора и сохранением в SQLite как обычный пост.
Пока — ручной запуск, чтобы не раздувать поток каналов.

См. также: [libraries-io.md](libraries-io.md) — почему libraries.io не основной источник.
