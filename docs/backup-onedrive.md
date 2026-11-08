# Бэкап контент-завода в OneDrive (Microsoft Graph API)

Ежедневный архив `data/` (SQLite, отчёты, outbox, аналитика, логи), `config/`,
`docs/promo/`, `scripts/` — в OneDrive через **Microsoft Graph API**.
Секреты (`.env`, `rclone.conf`) в архив **не попадают**.

## Статус (07.11.2026)

- ✅ OneDrive подключён (Graph API, rclone v1.76): **5 ГБ**, свободно ~5 ГБ.
- ✅ Тестовая выгрузка: архив 2.8 МБ + `.sha256` лежит в `onedrive:ContentFactoryBackups`.
- ✅ launchd-агент `com.contentfactory.backup`: ежедневно в **03:30**.
- Локальные копии: `data/backups/`, ротация — 14 архивов.

## Как устроено

`scripts/backup_onedrive.py`:

1. Согласованный снимок `factory.sqlite3` через SQLite backup API.
2. `content-factory-backup-YYYYmmdd-HHMMSS.tar.gz` + `.sha256`.
3. Локальный ретеншен (14) и выгрузка в `onedrive:ContentFactoryBackups/`
   (rclone → Microsoft Graph API, токен обновляется сам).
4. Если OneDrive не настроен — пишет локально с предупреждением.

Секреты и мусор исключены: `.env`, `rclone.conf`, модели Ollama (7+ ГБ), кэши.

## OAuth-токен (как получен и где лежит)

- Приложение — **rclone** (собственный зарегистрированный клиент, права
  `Files.ReadWrite offline_access`); вход выполнен один раз в браузере.
- Токен (access + **refresh**) — `data/rclone.conf`, `chmod 600`.
  `data/` в `.gitignore`; из бэкапа файл исключён.
- rclone сам обновляет access token по refresh token.
- Если refresh token отозван (смена пароля/«выйти на всех устройствах»),
  повторить:

  ```bash
  cd content-factory
  ../tools/rclone/rclone authorize onedrive --auth-no-open-browser
  # открыть ссылку из вывода, войти, скопировать JSON-токен
  # затем вписать в data/rclone.conf (поле token), drive_id оставить:
  ../tools/rclone/rclone --config data/rclone.conf lsd onedrive:
  ```

## Ручной запуск

```bash
cd content-factory
../tools/markitdown-venv/bin/python scripts/backup_onedrive.py
# архив появится в data/backups и уедет в OneDrive:ContentFactoryBackups
```

Полезные флаги: `--dry-run`, `--keep N`, `--target DIR`,
`--remote onedrive:ContentFactoryBackups`, `--verbose`.

## Ежедневное расписание (launchd)

```bash
cd content-factory
bash scripts/install_backup_schedule.sh
```

Лог: `data/logs/backup.log`. Удалить: `launchctl bootout gui/$(id -u)
~/Library/LaunchAgents/com.contentfactory.backup.plist`.

## Восстановление

```bash
cd content-factory
../tools/rclone/rclone --config data/rclone.conf copy \
  onedrive:ContentFactoryBackups/content-factory-backup-<дата>.tar.gz ./
tar -xzf content-factory-backup-<дата>.tar.gz
# .env вернуть отдельно (в бэкап не входит — секреты)
```

## GitHub Actions (работает даже при выключенном Mac)

Workflow [`.github/workflows/onedrive-backup.yml`](../.github/workflows/onedrive-backup.yml)
запускается **ежедневно в 04:15 UTC** (и вручную через workflow_dispatch):

1. Кладёт `repo.tar.gz` (снимок HEAD) и `growth-reports.tar.gz` (ветка отчётов).
2. Скачивает zip-артефакты последних 3 успешных запусков `content-factory.yml`
   и `growth-report.yml` (outbox, reports, логи, Markdown+raw JSON).
3. Пакует в `server-backup-YYYYmmdd-HHMMSS.tar.gz` + `.sha256`.
4. Выгружает в `onedrive:ServerBackups/` через rclone (Graph API).
5. Держит в облаке последние 30 дней (`--min-age 30d`).

Секреты репозитория:
- `RCLONE_CONF_B64` — base64 от `data/rclone.conf` (уже добавлен).
- Стандартный `GITHUB_TOKEN` workflow (права `actions: read`) для скачивания
  артефактов.

Проверить: Actions → **onedrive-backup** → Run workflow; результат —
`onedrive:ServerBackups/server-backup-*.tar.gz`.
