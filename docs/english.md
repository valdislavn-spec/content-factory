# Английский режим (English posts)

Завод может публиковать посты на английском. Это не глобальная настройка
«перевести всё»: язык задаётся **у канала** (`language: en`), поэтому один
запуск может обслуживать и русские, и английские каналы.

## 1. Быстрый старт

1. Готовый набор английских каналов — `config/channels.en.yaml`: 6 реальных
   Telegram-каналов (спорт, спорт-аналитика/ставки, мир, ИИ, технологии,
   крипто). В `telegram_chat_id` прописаны **числовые ID каналов** (не
   `@username`): бот работает по ID, и они не меняются при переименовании
   канала. Отдельные `TELEGRAM_CHAT_ID_*` для них не нужны.
2. В `config/settings.yaml`:

   ```yaml
   app:
     language: en
     channels_file: config/channels.en.yaml
   ```

3. Проверьте LLM (например, Dify):

   ```bash
   ./.venv/bin/python -m content_factory llm-test
   ```

4. Запуск в безопасном режиме (посты в `data/outbox/`, без публикации):

   ```bash
   ./.venv/bin/python -m content_factory run --channel tech-ai --dry-run
   ```

   Убедитесь, что в outbox-файле английский текст, а публикация остаётся
   выключенной. Для en-канала служебные подписи dry-run предпросмотра
   (`.txt` и `.html` в `data/outbox/`) тоже английские.

Переопределить файл каналов можно без правки YAML:

```bash
CONTENT_FACTORY_CHANNELS=config/channels.yaml ./.venv/bin/python -m content_factory run
```

## 2. Что именно переводится

- **Промпты анализа и генерации** — английские, когда у канала `language: en`.
- **Шаблонный fallback** (когда LLM недоступна или вернула мусор) — английские
  подписи, вступление, вывод, дайджест и цифры: пост остаётся английским.
- **Валидация ответов LLM** — для `en` принимается латиница и отклоняется
  кириллица, markdown и выдуманные цифры (как и раньше для русского).
- **Стили каналов** (`tone: expert|science|friendly`) — английские подписи.
- **Ключевые термины/хештеги** — английские стоп-слова и простая частотность
  без русской морфологии.

Не переводятся: внутренние логи, названия полей в SQLite, отчёты аналитики и
документация — они служебные и остаются на русском.

## 3. Автопостинг: раз в 90 минут в каждый канал

В `config/channels.en.yaml` **6 каналов** (спорт, спорт-аналитика/ставки, мир, ИИ, технологии, крипто)
и у каждого **16 слотов в сутки** — пост раз в 90 минут:
`00:00, 01:30, 03:00, 04:30, 06:00, 07:30, 09:00, 10:30, 12:00, 13:30, 15:00,
16:30, 18:00, 19:30, 21:00, 22:30` (UTC). Итого **96 постов/сутки**.

**Автозапуск на macOS** (переживает перезагрузку, перезапускается при падении):

```bash
bash scripts/install-launchd-macos.sh          # установить и запустить
bash scripts/install-launchd-macos.sh status   # проверить
bash scripts/install-launchd-macos.sh uninstall# остановить
```

Логи: `data/logs/daemon.out.log`, `data/logs/daemon.err.log` и общий
`data/logs/factory.log`.

**Бесплатные лимиты** (80 запусков/сутки):

| Ресурс | Лимит | Наш расход / защита |
|---|---|---|
| RSS | без ключей | основной источник, работает всегда |
| World News API | 50 points/сутки | `daily_limit: 30` → примерно треть слотов |
| newsdata.io | ~200 кредитов/сутки | `daily_limit: 100` (хватает на все 80) |
| Currents API | ~600 запросов/сутки | `daily_limit: 100` |
| LLM (Groq/free) | лимиты провайдеров | `daily_request_limit: 300`, дальше extractive |
| Dify-приложение | 200 кредитов Sandbox | по умолчанию выключено |
| Telegram Bot API | бесплатно | 80 сообщений/сутки |

Источники с исчерпанной квотой пропускаются (счётчики в
`data/source_<type>_usage.json`), канал продолжает работать на RSS.
LLM-цепочка: `Groq → OpenRouter → SambaNova → HuggingFace → OpenAI → Dify →
extractive` (счётчик `data/llm_usage.json`).

Пока `TELEGRAM_BOT_TOKEN` пуст или `dry_run: true`, демон пишет посты в
`data/outbox/` и ничего не публикует — это безопасный режим для проверки.

## 4. Dify Cloud и язык

Если генерация идёт через приложение Dify, язык ответа задаёт **инструкция
приложения** (поле `INSTRUCTIONS` в Dify). Для английских постов она должна
требовать английский, например:

```
You are a news editor for a Telegram channel. Always respond in English only.
Follow the user's request precisely, use only the facts provided and never
invent numbers, names, quotes or links.
```

Фабрика передаёт свои промпты в запросе, но приложение Dify остаётся главным
источником инструкций. Подробнее о провайдере — в [llm.md](llm.md#16-dify--приложение-dify-как-llm).
