# Эксплуатация: автозапуск, логи, бэкапы, мониторинг

Документ для случая «уже настроено и публикуется»: как сделать работу
автономной, где смотреть ошибки, что бэкапить и как обновляться.

## 1. Режимы работы

| Команда | Что делает |
|---|---|
| `python -m content_factory run --channel all` | один прогон всех каналов и выход |
| `python -m content_factory run --channel tech-ai --dry-run` | прогон без публикации (в outbox) |
| `python -m content_factory daemon` | демон: проверяет расписание каждые `daemon_interval_sec` (60 с) |
| `python -m content_factory daemon --once` | одна проверка расписания и выход (для cron) |
| `python -m content_factory daemon --interval 300` | демон с интервалом 5 минут |
| `python -m content_factory report --days 7` | отчёт за 7 дней |

Важно: **не запускайте два демона одновременно** на одной базе
`data/factory.sqlite3` — SQLite рассчитан на одного писателя. Второй процесс
может получить ошибку `database is locked`.

При самом первом запуске демон может «догнать» слоты за последние 24 часа
(окно первого запуска). Если это нежелательно, запустите его сразу после
настройки или в безопасном режиме `CONTENT_FACTORY_DRY_RUN=true`, проверьте
outbox и только потом включайте реальную публикацию.

## 2. Автозапуск на Linux (systemd)

Готовый unit — `scripts/systemd/content-factory.service`. Скопируйте его,
поправьте пути/пользователя и установите:

```bash
# 1) отредактируйте пути в файле (WorkingDirectory, ExecStart, User,
#    EnvironmentFile) — там есть комментарии
sudo nano scripts/systemd/content-factory.service

# 2) установите
sudo cp scripts/systemd/content-factory.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now content-factory

# 3) проверьте
systemctl status content-factory
journalctl -u content-factory -f
```

После правки unit-файла:

```bash
sudo systemctl daemon-reload
sudo systemctl restart content-factory
```

Полезные команды:

```bash
sudo systemctl stop content-factory      # остановить
sudo systemctl disable content-factory   # убрать из автозапуска
sudo systemctl restart content-factory   # перезапустить
```

`Restart=always` в unit означает, что при падении процесса systemd поднимет
его снова через несколько секунд.

### Вариант без systemd: cron

Если systemd нет (некоторые VPS/контейнеры), запускайте «одну проверку
расписания» по cron каждые 5–10 минут:

```cron
*/10 * * * * cd /opt/content-factory && ./.venv/bin/python -m content_factory daemon --once >> data/logs/cron.log 2>&1
```

Откройте `crontab -e` и добавьте строку. Убедитесь, что путь и пользователь
верные; cron не загружает `.env` сам — но программа читает `.env` из корня
проекта (`cd` в строке это обеспечивает).

## 3. Автозапуск на Windows (Планировщик заданий)

1. Откройте PowerShell в папке проекта (для `-AtStartup` — от имени
   администратора).
2. Разрешите запуск скриптов (если ещё не):

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

3. Зарегистрируйте задачу:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\install-task.ps1

# вариант «запускать при старте Windows» (нужен PowerShell от админа):
powershell -ExecutionPolicy Bypass -File scripts\windows\install-task.ps1 -AtStartup
```

Скрипт создаст задачу `ContentFactory`, которая запускается при входе в
систему (или при старте Windows с `-AtStartup`) и затем каждые N минут
выполняет одну проверку расписания (`run.bat --once`, то есть
`daemon --once`). Параметры (имя задачи, интервал, папка проекта) можно
изменить в начале скрипта. `-AtStartup` регистрирует задачу от SYSTEM —
удобно для сервера, который работает без входа пользователя.

Проверка и управление:

```powershell
Get-ScheduledTask -TaskName ContentFactory
Start-ScheduledTask -TaskName ContentFactory
Stop-ScheduledTask -TaskName ContentFactory
Unregister-ScheduledTask -TaskName ContentFactory -Confirm:$false
```

Альтернатива: создайте задачу вручную в «Планировщике заданий» с действием
`scripts\windows\run.bat` и триггером «При входе в систему».

## 4. Логи

- Основной лог: `data/logs/factory.log`.
- Ротация встроена: файл до 2 МБ, хранится 3 архива
  (`factory.log.1`, `.2`, `.3`). Старые записи удаляются автоматически.
- Уровень подробности задаётся в `config/settings.yaml`:
  `app.log_level: INFO` (можно `DEBUG` для диагностики, `WARNING` для
  тишины).
- Логи демона при systemd дополнительно доступны через
  `journalctl -u content-factory`.
- Cron-режим пишет в `data/logs/cron.log` (см. пример выше).

Что искать в логе:

```bash
# ошибки источников и публикации
grep -E "ERROR|WARNING|Ошибка" data/logs/factory.log | tail -n 50

# итоги запусков
grep "Итог" data/logs/factory.log | tail -n 20
```

## 5. Бэкапы

Бэкапить нужно:

1. `data/factory.sqlite3` — статьи, посты, публикации, метрики, история.
2. `.env` — токены и id каналов (хранить как пароль!).
3. `config/settings.yaml`, `config/channels.yaml` — настройки каналов.
4. (по желанию) `data/reports/`, `data/outbox/`.

### SQLite: правильная копия

Не копируйте файл базы «на горячую» обычным `cp`, если демон работает — можно
получить повреждённую копию. Используйте встроенный бэкап SQLite:

```bash
mkdir -p backups
sqlite3 data/factory.sqlite3 ".backup 'backups/factory-$(date +%Y%m%d-%H%M).sqlite3'"
```

Если `sqlite3` не установлен, остановите демон и скопируйте файл:

```bash
sudo systemctl stop content-factory
cp data/factory.sqlite3 "backups/factory-$(date +%Y%m%d).sqlite3"
sudo systemctl start content-factory
```

### Пример ежедневного бэкапа (cron)

```cron
15 4 * * * cd /opt/content-factory && mkdir -p backups && sqlite3 data/factory.sqlite3 ".backup 'backups/factory-$(date +\%Y\%m\%d).sqlite3'" && cp .env "backups/env-$(date +\%Y\%m\%d).bak" && find backups -name 'factory-*.sqlite3' -mtime +30 -delete
```

(В crontab символ `%` нужно экранировать как `\%`.)

### Восстановление

1. Остановите демон.
2. Замените `data/factory.sqlite3` копией из `backups/`.
3. Запустите демон и проверьте `python -m content_factory report --days 7`.

## 6. Мониторинг

### Быстрая проверка

```bash
python -m content_factory channels          # каналы и режим публикации
python -m content_factory sources check     # доступность источников
python -m content_factory metrics           # подписчики и объёмы
python -m content_factory telegram-metrics  # просмотры/реакции/ER (Telethon)
python -m content_factory report --days 7   # HTML+MD отчёт
```

### Что смотреть в отчёте

- количество статей, сюжетов, постов за период;
- сколько постов опубликовано / отклонено / упало;
- доля dry-run публикаций (если 100% — реальная публикация выключена);
- топ источников (видно, кто даёт контент, а кто молчит);
- ошибки запусков (`runs.errors`);
- Telegram-метрики: подписчики, рост, средние просмотры, ER, лучший пост
  (если запускались `telegram-metrics`/`metrics` с Telethon);
- подписчики (если Bot API доступен);
- средняя длина постов и распределение форматов.

### Прямые запросы к базе (для продвинутых)

```bash
sqlite3 data/factory.sqlite3
```

```sql
-- последние запуски
SELECT channel_id, started_at, posts_generated, posts_published,
       substr(errors,1,120) AS errors
FROM runs ORDER BY started_at DESC LIMIT 20;

-- неудачные публикации
SELECT channel_id, publisher, error, published_at
FROM publishes WHERE ok = 0 ORDER BY published_at DESC LIMIT 20;

-- сколько постов за неделю
SELECT channel_id, COUNT(*) FROM posts
WHERE created_at >= datetime('now','-7 days') GROUP BY channel_id;
```

### Признаки проблем

| Симптом | Вероятная причина | Что делать |
|---|---|---|
| нет постов несколько дней | источники недоступны / темы слишком узкие | `sources check`, расширить `topics`, проверить `runs.errors` |
| посты есть, но не публикуются | `dry_run=true`, нет chat_id, бот не админ | проверить `.env`, `channels`, лог |
| много отклонённых постов | `min_post_chars`, `banned_words`, качество резюме | ослабить/усилить фильтры, сменить LLM |
| `database is locked` | запущено два демона | оставить один процесс |
| лог растёт слишком быстро | `DEBUG`, ошибки источников в цикле | поднять уровень до INFO/WARNING |
| Telegram `429 Too Many Requests` | слишком частая публикация | увеличить интервалы слотов |

## 7. Ограничения Telegram и VK

- **Длина сообщения Telegram** — 4096 символов. Программа режет длинный HTML
  на части, не разрывая теги; канал настроен на 3500–3800 символов, так что
  обычно хватает одного сообщения.
- **Частота.** Ориентиры Bot API: около 30 сообщений в секунду в целом и
  порядка 20 сообщений в минуту в один канал. Конвейер публикует по слотам,
  не «пачкой», поэтому лимиты почти не достигаются.
- **429 Too Many Requests** — Telegram просит подождать (`retry_after`).
  Публикация помечается ошибкой и попадает в отчёт; **автоматического повтора
  нет** — следующий слот возьмёт новые сюжеты, а отклонённый пост можно
  посмотреть в `preview`/`data/outbox/` и опубликовать вручную.

Если публикация не удалась, действуйте так:

1. Посмотрите `data/logs/factory.log` и `publishes` (`error`).
2. Проверьте, что бот — администратор канала с правом публикации, токен
   действителен, `chat_id` верный.
3. Проверьте текст: `python -m content_factory preview --channel ...` не
   публикует, но показывает будущий пост; при необходимости отправьте вручную.
4. После исправления дождитесь следующего слота — он возьмёт свежие сюжеты.
- **VK:** лимит длины поста — 16 000 символов; публикация в стену группы
  требует токена с правами `wall`, `manage` и прав администратора у токена.
- **Просмотры постов** Bot API не отдаёт. Подписчики — отдаёт. Для просмотров
  нужен Telethon или ручной экспорт.

## 8. Обновление

1. Сделайте бэкап (см. выше).
2. Остановите демон.
3. Замените код проекта (git pull / распакуйте новую версию), **не
   перезаписывая** `config/`, `.env`, `data/`.
4. Обновите зависимости:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

5. Прогоните тесты и проверки:

```bash
bash scripts/check.sh
```

6. Запустите демо и dry-run, затем поднимите демон:

```bash
python -m content_factory demo
python -m content_factory run --channel all --dry-run
sudo systemctl start content-factory
```

## 9. Ротация токенов и безопасность

- Токен бота перевыпускается в @BotFather: `/revoke` → новый токен → заменить
  `TELEGRAM_BOT_TOKEN` в `.env` → перезапустить демон.
- Токен VK/ключи GigaChat/YandexGPT продлеваются в личных кабинетах; после
  замены — перезапуск.
- `.env` и Telethon-сессия (`TG_SESSION`) — как пароли: не в git, не в
  переписке, права `600` на сервере:

```bash
chmod 600 .env
```

- Не публикуйте логи с токенами; программа токены не логирует, но проверяйте
  сторонние скрипты.

## 10. Перенос на VPS

1. Создайте пользователя (например, `content`) и каталог `/opt/content-factory`.
2. Установите Python 3.9+, скопируйте проект.
3. Перенесите `config/`, `.env`, `data/factory.sqlite3` (можно без базы —
   начнёт с чистого листа).
4. Создайте venv и установите зависимости.
5. Проверьте `python -m content_factory channels` и `sources check`.
6. Настройте systemd-сервис (пункт 2) и бэкапы (пункт 5).
7. Убедитесь, что часовой пояс расписания — МСК (`timezone_offset: 3`), а не
   пояс сервера; расписание не зависит от системного времени, но для
   понимания логов удобно выставить TZ.
8. Первый запуск — с `--dry-run`, затем реальный.

Требования к VPS минимальны: 1–2 ГБ RAM достаточно для `extractive`; для
локальной LLM нужно 8–16 ГБ RAM (или облачный GigaChat/YandexGPT без
локальной модели).

## 11. Остановка и «пауза»

- Временно остановить: `sudo systemctl stop content-factory` (или закрыть
  окно демона).
- Полностью отключить автозапуск: `sudo systemctl disable content-factory`.
- Поставить на паузу один канал: `enabled: false` в `config/channels.yaml` и
  перезапуск.
- Выключить реальную публикацию, оставив сбор: `CONTENT_FACTORY_DRY_RUN=true`
  и перезапуск.
