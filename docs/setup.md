# Установка и настройка

Инструкция рассчитана на человека без опыта программирования. Все команды
выполняются **из папки проекта** (там, где лежат `config/`, `content_factory/`,
`requirements.txt`). Если вы открыли терминал в другой папке — сначала
перейдите в проект:

```bash
cd путь/к/content-factory
```

Проект не требует Docker, платных API и GPU. Нужен только Python и интернет
для сбора новостей.

## 1. Установка Python

Нужен **Python 3.9 или новее** (рекомендуется 3.11–3.12).

### Windows

1. Скачайте Python с <https://www.python.org/downloads/windows/>.
2. При установке обязательно поставьте галочку **«Add python.exe to PATH»**.
3. Проверьте в новом окне командной строки:

```bat
python --version
```

Если открывается Microsoft Store вместо Python — переустановите с официального
сайта.

### Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip
python3 --version
```

### macOS

```bash
# Вариант 1: с сайта python.org (рекомендуется)
# Вариант 2: Homebrew
brew install python
python3 --version
```

Везде далее команда `python` означает ваш Python 3. На Linux/macOS, возможно,
придётся писать `python3`.

## 2. Скачивание проекта и виртуальное окружение

Виртуальное окружение (venv) — отдельная «песочница» для зависимостей, чтобы
не засорять систему.

### Linux / macOS

```bash
cd content-factory
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Windows (cmd)

```bat
cd content-factory
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Windows (PowerShell)

```powershell
cd content-factory
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Если PowerShell запрещает запуск скриптов:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

> После активации в начале строки появится `(.venv)`. Это значит, что
> команды `python`/`pip` относятся к проекту. Если вы открыли новый терминал —
> активируйте venv снова.

В дальнейшем в документации используется запись `./.venv/bin/python` — это
путь к Python внутри venv для Linux/macOS. На Windows ему соответствует
`.venv\Scripts\python.exe`. Если venv активирован, достаточно `python`.

### 2.1. Локальная LLM (Ollama) — бесплатно и без ключей

Завод умеет генерировать посты без облачных API и без регистраций — на
локальной модели. Это бесплатно, работает офлайн, данные никуда не уходят.
В проекте уже лежит готовый бинарник Ollama (`data/ollama/`, ключи не нужны):

```bash
bash scripts/start-ollama.sh start          # запустить сервер
bash scripts/start-ollama.sh pull qwen3.5:9b  # скачать модель, ~7.6 ГБ (один раз)
bash scripts/start-ollama.sh status         # проверить
```

В `config/settings.yaml` провайдер уже включён:

```yaml
llm:
  provider: ollama
  ollama:
    model: qwen3.5:9b
    num_ctx: 8192
    think: false      # без «размышлений» модель отвечает в разы быстрее
```

Проверка: `./.venv/bin/python -m content_factory llm-test` — должен прийти
ответ модели. Если модель не скачана или сервер не запущен, завод не падает,
а публикует в extractive-режиме (см. [llm.md](llm.md)).

Под другое железо: `qwen3.5:4b` (~4 ГБ) для 8 ГБ RAM, `qwen3.8:27b` для
GPU 24 ГБ; модели с Hugging Face — через
`bash scripts/start-ollama.sh pull hf.co/<repo>:<quant>`.

## 3. Первый запуск без токенов: demo

Демо работает **офлайн, без сети, без токенов и без публикации**. Оно
показывает, как выглядят посты и отчёт.

```bash
python -m content_factory init     # создаст .env и каталоги data/
python -m content_factory demo
```

Что произойдёт:

- посты сохранятся в `samples/demo/outbox/`;
- отчёт (HTML и Markdown) — в `samples/demo/reports/`, HTML откроется в
  браузере;
- рабочая база и логи демо — в `data/demo/`, рабочие данные не затрагиваются.

`demo --keep` не удаляет прошлые демо-результаты (по умолчанию они
очищаются перед прогоном).

Если демо отработало — установка успешна. Можно переходить к токенам.

## 4. Настройка публикации в Telegram

### 4.1. Создать бота

1. Откройте Telegram, найдите **@BotFather** (официальный, с галочкой).
2. Отправьте `/newbot`.
3. Задайте имя бота и username (должен заканчиваться на `bot`).
4. BotFather пришлёт **токен** вида `123456789:AAH...`. Это секрет: не
   публикуйте его, не пересылайте в чаты.

### 4.2. Заполнить `.env`

Откройте `.env` в любом текстовом редакторе (файл создан командой `init`).
Минимум, что нужно:

```bash
TELEGRAM_BOT_TOKEN=123456789:AAH...ваш_токен...

# id каналов: @username или числовой -100... (по одному на канал)
TELEGRAM_CHAT_ID_TECH_AI=@my_tech_channel
TELEGRAM_CHAT_ID_BUSINESS_FINANCE=@my_business_channel
TELEGRAM_CHAT_ID_SCIENCE_HEALTH=@my_science_channel
TELEGRAM_CHAT_ID_AUTO=@my_auto_channel
TELEGRAM_CHAT_ID_TRAVEL=@my_travel_channel
TELEGRAM_CHAT_ID_CULTURE=@my_culture_channel

# пока true — ничего не публикуем, посты идут в data/outbox
CONTENT_FACTORY_DRY_RUN=true
```

Если канал пока не нужен — оставьте переменную пустой. При включённом
`dry_run` пост просто попадёт в `data/outbox`; при выключенном dry-run
публикация в этот канал завершится ошибкой «не задан chat_id», которая будет
видна в `publishes.error`.

### 4.3. Добавить бота администратором в канал

1. Откройте канал → «Управление» → «Администраторы» → «Добавить
   администратора».
2. Найдите бота по username и добавьте.
3. Обязательно включите право **«Публикация сообщений»** (Post messages).
4. Сохраните.

Без этого шага Telegram вернёт ошибку вида `chat not found`,
`not enough rights to send text messages` или `403 Forbidden`.

### 4.4. Как узнать chat_id канала

Два надёжных способа:

1. **Публичный канал:** используйте `@username` (например,
   `@my_tech_channel`). Подходит, если username не менялся.
2. **Числовой id:** откройте канал в `web.telegram.org`, посмотрите на адрес
   строки: `.../#-1001234567890` — число `-1001234567890` и есть chat_id.
   Также можно переслать любой пост канала боту @username_to_id_bot и взять
   `id` канала.

В `.env` пишите id без кавычек:

```bash
TELEGRAM_CHAT_ID_TECH_AI=-1001234567890
```

### 4.5. Проверить конфигурацию

```bash
python -m content_factory channels
```

Команда покажет 6 каналов, их расписание и режим публикации (dry-run/Telegram/
нет chat_id). Затем проверьте источники:

```bash
python -m content_factory sources check
```

- `OK` — источник доступен;
- `FAIL` — источник недоступен (сеть, блокировка, изменился адрес); это не
  смертельно, но такой источник не даст новостей.

## 5. Первый dry-run и первая публикация

### 5.1. Безопасный прогон

```bash
python -m content_factory run --channel all --dry-run
```

- ничего не публикуется;
- посты сохраняются в `data/outbox/`;
- статистика — в `data/factory.sqlite3` (таблицы `runs`, `posts`).

Проверьте посты глазами:

```bash
python -m content_factory preview --channel tech-ai
```

`preview` показывает, что было бы опубликовано, **не сохраняя посты и не
публикуя**. Параметр `--limit 3` задаёт, сколько сюжетов показать на канал.

### 5.2. Реальная публикация

Убедитесь, что бот добавлен админом во все каналы, затем в `.env`:

```bash
CONTENT_FACTORY_DRY_RUN=false
```

И запустите:

```bash
# один канал
python -m content_factory run --channel tech-ai

# все каналы
python -m content_factory run --channel all
```

Разовую публикацию можно включить и без правки `.env`:

```bash
python -m content_factory run --channel tech-ai --publish
```

(`--publish` переопределяет dry-run; будьте осторожны.)

После публикации проверьте канал и базу:

```bash
python -m content_factory report --days 1
```

В отчёте видно, сколько постов сгенерировано и опубликовано, какие были
ошибки.

### 5.3. Вернуться в безопасный режим

```bash
CONTENT_FACTORY_DRY_RUN=true
```

или запускайте с флагом `--dry-run`. Переменная окружения имеет приоритет над
`config/settings.yaml`.

## 6. Автозапуск

- **Linux:** systemd-сервис — см. `scripts/systemd/content-factory.service` и
  [operations.md](operations.md).
- **Windows:** Планировщик заданий — см. `scripts/windows/install-task.ps1`.
- **Готовые скрипты:** `scripts/install.sh` (установка),
  `scripts/run-daemon.sh` (запуск демона с логом), `scripts/check.sh`
  (проверка источников и тестов).

Демон:

```bash
python -m content_factory daemon
```

Остановка — `Ctrl+C`. Проверить расписание один раз (удобно для cron):

```bash
python -m content_factory daemon --once
```

## 7. Типичные ошибки

### `No module named content_factory`

Вы запускаете команду не из папки проекта. Перейдите в неё (`cd
content-factory`) или используйте флаг `--root`:

```bash
python -m content_factory --root /путь/к/content-factory channels
```

### `Не установлен PyYAML`

Не активирован venv или не установлены зависимости:

```bash
source .venv/bin/activate      # Linux/macOS
.venv\Scripts\activate         # Windows
python -m pip install -r requirements.txt
```

### `No module named yaml` / `ModuleNotFoundError`

То же самое: активируйте venv и установите `requirements.txt`.

### `Ошибка конфигурации: ... config/channels.yaml`

Синтаксическая ошибка в YAML (чаще всего — табуляция вместо пробелов,
потерянное двоеточие, неверный отступ). Текст ошибки содержит путь и место.
Проверьте отступы: в YAML только пробелы, выравнивание одинаковое.

### `chat not found` / `not enough rights` / `403`

- Бот не добавлен в канал администратором.
- У бота нет права «Публикация сообщений».
- Неверный `chat_id` (канал удалён или id другого канала).
- Бот заблокирован пользователем (для личных чатов).

### `Unauthorized` / `401`

Неверный `TELEGRAM_BOT_TOKEN` (пробел, перенос строки, старый токен).
Перевыпустите токен в @BotFather (`/revoke`).

### `Протух/неверный GIGACHAT_CREDENTIALS`

Проверьте base64-строку и срок действия ключа; временно верните
`llm.provider: extractive`.

### Источники `FAIL`, но интернет есть

- Сайт блокирует запросы (403) или сменил адрес RSS.
- Источник недоступен из вашей сети/VPN.
- Временно отключите источник (`enabled: false`) и проверьте остальные.

### Демо не находит данные

`demo` требует файл `samples/demo_articles.json` — он поставляется вместе с
проектом. Если файла нет, проверьте, что вы скачали проект целиком.

### Публикация прошла, а в канале пусто

Проверьте `CONTENT_FACTORY_DRY_RUN`: при `true` посты только в
`data/outbox/`. Посмотрите `data/logs/factory.log` и таблицу `publishes` в
базе.

## 8. Что дальше

- Настройте каналы и темы — [channels.md](channels.md).
- Подключите локальную LLM (если нужно) — [llm.md](llm.md).
- Настройте автозапуск и бэкапы — [operations.md](operations.md).
- Прочитайте правовые ограничения — [legal.md](legal.md).
