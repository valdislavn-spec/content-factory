# Английский режим (English posts)

Завод может публиковать посты на английском. Это не глобальная настройка
«перевести всё»: язык задаётся **у канала** (`language: en`), поэтому один
запуск может обслуживать и русские, и английские каналы.

## 1. Быстрый старт

1. Готовый набор английских каналов — `config/channels.en.yaml`: 3 реальных
   Telegram-канала (US Sports, AI, Crypto). В `telegram_chat_id` прописаны
   **числовые ID каналов** (не `@username`): бот работает по ID, и они не
   меняются при переименовании канала. Отдельные `TELEGRAM_CHAT_ID_*` для них
   не нужны. Испанские каналы лежат в `config/channels.es.yaml`.
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
   ./.venv/bin/python -m content_factory run --channel ai-news --dry-run
   ```

   Убедитесь, что в outbox-файле английский текст, а публикация остаётся
   выключенной. Для en-канала служебные подписи dry-run предпросмотра
   (`.txt` и `.html` в `data/outbox/`) тоже английские.

Переопределить файл каналов можно без правки YAML:

```bash
CONTENT_FACTORY_CHANNELS=config/channels.en.yaml ./.venv/bin/python -m content_factory run
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

## 3. Автопостинг по расписанию

В `config/channels.en.yaml` **3 английских канала**:

| Канал | Слотов в сутки |
|---|---:|
| `sport-news` | 12 |
| `ai-news` | 8 |
| `crypto-news` | 12 |

Итого **32 запланированных поста в сутки** в английском наборе. Точные слоты
заданы в `schedule` каждого канала и считаются в его `timezone_offset`
(у EN-каналов сейчас UTC−5). Испанский набор (`config/channels.es.yaml`) —
ещё 32 слота, всего по сети 64.

**Продакшн-планировщик — GitHub Actions** (`.github/workflows/content-factory.yml`),
он запускается по внешнему cron и делает один тик EN + один тик ES.

**Локальный автозапуск на macOS** — только резервный режим для одной машины:

```bash
bash scripts/install-launchd-macos.sh          # установить и запустить
bash scripts/install-launchd-macos.sh status   # проверить
bash scripts/install-launchd-macos.sh uninstall# остановить
```

⚠️ Не запускайте локальный `daemon` одновременно с облачным workflow: два
планировщика видят разные `schedule_state.json`, отрабатывают одни и те же
слоты и дают дубли постов. Для облачного продакшна локальный агент должен быть
остановлен и disabled (`launchctl bootout` + `launchctl disable`).

Логи локального режима: `data/logs/daemon.out.log`,
`data/logs/daemon.err.log` и общий `data/logs/factory.log`.

**Бесплатные лимиты** (зависят от текущего набора источников и LLM-цепочки):

| Ресурс | Лимит | Наш расход / защита |
|---|---|---|
| RSS | без ключей | основной источник, работает всегда |
| World News API | 50 points/сутки | `daily_limit` в конфиге источника |
| newsdata.io | ~200 кредитов/сутки | `daily_limit: 100` |
| Currents API | ~600 запросов/сутки | `daily_limit: 100` |
| LLM (Groq/free) | лимиты провайдеров | `daily_request_limit: 300`, дальше extractive |
| Dify-приложение | 200 кредитов Sandbox | по умолчанию выключено |
| Telegram Bot API | бесплатно | 64 слота/сутки + рыночные алерты |

Источники с исчерпанной квотой пропускаются (счётчики в
`data/source_<type>_usage.json`), канал продолжает работать на RSS.

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
