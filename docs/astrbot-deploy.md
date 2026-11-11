# AstrBot: AI-ассистент канала (GitHub Actions / Northflank)

AstrBot — отдельный Telegram-бот с LLM (Groq / OpenRouter / DeepSeek), который
отвечает на вопросы и принимает ссылки/текст. Он не публикует посты сам: публикации
идут через `content_factory`, а AstrBot закрывает роль «ассистент в личке».

## Что нужно в секретах

| Переменная | Обязательна | Зачем |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | да | токен бота AstrBot |
| `GROQ_API_KEY` / `OPENROUTER_API_KEY` / `DEEPSEEK_API_KEY` | хотя бы один | LLM-провайдер |
| `HUGGINGFACE_API_KEY` (`HF_TOKEN`) | для state | приватный dataset `ERPSAS/cf-astrbot-state` |
| `HF_REPO` | нет | по умолчанию `ERPSAS/cf-astrbot-state` |
| `CLOUDFLARE_ACCOUNT_ID` / `CLOUDFLARE_API_TOKEN` | для RAG | эмбеддинги Cloudflare Workers AI `@cf/baai/bge-m3` |
| `ASTRBOT_DASHBOARD_INITIAL_PASSWORD` | для WebUI | пароль администратора Dashboard |

Конфиг рендерится из [`.astrbot/cmd_config.template.json`](../.astrbot/cmd_config.template.json).
Провайдеры без ключа автоматически убираются; если не осталось ни одного — запуск
падает с понятной ошибкой, а не с битым `cmd_config.json`.

## Вариант 1: GitHub Actions (бесплатно, сменами)

Workflow [`.github/workflows/astrbot-run.yml`](../.github/workflows/astrbot-run.yml):

1. restore `data/` из HF dataset;
2. render `data/cmd_config.json`;
3. `astrbot run` до 5 ч 30 мин;
4. save state обратно в HF.

Cron — раз в 6 часов, поэтому возможны паузы 10–25 минут. Для 24/7 без пауз
используй Northflank.

## Вариант 2: Northflank (24/7)

В контейнер `soulter/astrbot` добавь start command:

```bash
curl -fsSL https://raw.githubusercontent.com/valdislavn-spec/content-factory/main/.astrbot/northflank_bootstrap.sh | bash
```

Bootstrap скачивает `state_sync.py`, `render_config_image.py` и шаблон, ставит
`huggingface_hub`, восстанавливает state, рендерит конфиг, каждые 5 минут
синхронизирует `data/` в HF и запускает `astrbot`.

Нужны env-переменные из таблицы выше. Dashboard в шаблоне слушает `0.0.0.0:6185` —
если он не нужен, выключи `dashboard.enable` в шаблоне или закрой порт.

## Проверка и откат

```bash
# локальная проверка рендера (без запуска бота)
ASTRBOT_ROOT=/tmp/astrbot \
ASTRBOT_TEMPLATE=$PWD/.astrbot/cmd_config.template.json \
TELEGRAM_BOT_TOKEN=test GROQ_API_KEY=test \
python .astrbot/render_config_image.py

# тесты
python -m pytest -q tests/test_astrbot_scripts.py
```

Откат — вернуть предыдущий `main`/тег и перезапустить workflow; state в HF
перезаписывается только при `save`, поэтому старый снапшот можно восстановить
вручную через `state_sync.py restore`.

## Ограничения

- один getUpdates-процесс на бота: не запускай AstrBot одновременно с
  `ad_bot.py` / `telegram-growth-bot.py` на том же токене;
- GitHub Actions job ограничен 6 часами;
- не коммить `data/` и `.env` — там сессии и секреты.

## RAG и Telegram Stars

См. [astrbot-rag-stars.md](astrbot-rag-stars.md): база знаний `content-factory`, эмбеддинги Cloudflare, донаты через `@Cf_crosspromo_bot` (`/donate`).
