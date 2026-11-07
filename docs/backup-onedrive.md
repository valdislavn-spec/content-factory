# Бэкап контент-завода в OneDrive

Цель: ежедневный архив `data/` (SQLite, отчёты, outbox, аналитика, логи),
`config/`, `docs/promo/` и `scripts/` — в облако, с ротацией и SHA256.
Секреты (`.env`) в архив **не попадают**.

## Как это работает

Скрипт `scripts/backup_onedrive.py`:

1. Находит папку синхронизации OneDrive:
   - `~/OneDrive/` (классический клиент),
   - `~/Library/CloudStorage/OneDrive*/` (новый клиент),
   - иначе пишет локально в `data/backups/` с предупреждением.
2. Делает согласованный снимок `factory.sqlite3` через SQLite backup API
   (без блокировки базы).
3. Пакует в `content-factory-backup-YYYYmmdd-HHMMSS.tar.gz` + `.sha256`.
4. Удаляет старые архивы, оставляя последние 14.

## Установка (один раз)

1. Установите **OneDrive для Mac**: <https://www.microsoft.com/microsoft-365/onedrive/download>
   (или Mac App Store) — права администратора не нужны.
2. Войдите в Microsoft-аккаунт, который открывается по вашей ссылке
   `onedrive.live.com`, и включите синхронизацию (появится `~/OneDrive`).
3. Проверьте бэкап вручную:

   ```bash
   cd content-factory
   python ../tools/markitdown-venv/bin/python scripts/backup_onedrive.py
   ```

   В `~/OneDrive/ContentFactoryBackups/` появится архив.

## Ежедневный запуск (launchd, без root)

```bash
cd content-factory
bash scripts/install_backup_schedule.sh
```

Скрипт создаёт `~/Library/LaunchAgents/com.contentfactory.backup.plist`
и запускает его в 03:30 каждый день. Логи: `data/logs/backup.log`.
Удалить расписание: `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.contentfactory.backup.plist`.

## Восстановление

```bash
cd content-factory
tar -xzf ~/OneDrive/ContentFactoryBackups/content-factory-backup-<дата>.tar.gz
# .env нужно вернуть отдельно (он не бэкапится — это секреты)
```

## Если OneDrive ставить не хочется

Можно ходить в OneDrive через Microsoft Graph API (OAuth): нужен
`client_id`/`refresh_token` приложения Microsoft Entra. Тогда бэкап можно
делать и с GitHub Actions (раннер ходит в Graph без блокировок). Скажи —
подготовлю OAuth-инструкцию и workflow.
