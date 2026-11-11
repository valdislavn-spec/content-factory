# Oracle Cloud Always Free: запуск контент-завода на своём сервере

Короткая инструкция именно для этого репозитория. Общий разбор бесплатных
вариантов и ограничений Oracle — в [free-cloud.md](free-cloud.md) §6.1;
автозапуск/мониторинг — в [operations.md](operations.md); бэкапы — в
[backup-onedrive.md](backup-onedrive.md).

## 0. Что понадобится

- Аккаунт Oracle Cloud (карта для верификации, списаний в Always Free быть не должно).
- Инстанс **VM.Standard.A1.Flex** (ARM, Always Free: до 4 OCPU / 24 ГБ RAM) +
  образ **Ubuntu 22.04** или **24.04** (aarch64).
- Публичный IP и SSH-ключ, привязанный к инстансу.
- `ssh -i <ключ> ubuntu@<IP>` — вход по умолчанию для Ubuntu-образов Oracle.

Входящие порты заводу не нужны: он только ходит наружу (Telegram API, RSS, LLM).
SSH-доступ по умолчанию уже открыт в security list.

## 1. Быстрый запуск (один скрипт)

На сервере, из каталога проекта:

```bash
sudo bash scripts/oracle_bootstrap.sh --dry-run   # посмотреть шаги
sudo bash scripts/oracle_bootstrap.sh             # выполнить
```

Скрипт идемпотентно: ставит пакеты, создаёт пользователя `content`,
раскладывает проект в `/opt/content-factory`, запускает `scripts/install.sh`,
ставит systemd-сервис `content-factory` и включает автозапуск.
Параметры: `APP_DIR=...`, `SERVICE_USER=...`, `--no-install`, `--no-systemd`.

Если проект ещё не на сервере — сначала скопируйте его:

```bash
# с локальной машины
rsync -az --exclude .venv --exclude data --exclude '.git' \
    content-factory/ ubuntu@<IP>:/opt/content-factory/
```

## 2. Вручную (если без скрипта)

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git rsync
sudo useradd --system --create-home --shell /bin/bash content
sudo mkdir -p /opt/content-factory && sudo chown -R content:content /opt/content-factory
# проект уже в /opt/content-factory
sudo -u content bash /opt/content-factory/scripts/install.sh
cd /opt/content-factory
sudo cp .env.example .env        # затем заполнить токены
sudo chown content:content .env && sudo chmod 600 .env
sudo cp scripts/systemd/content-factory.service /etc/systemd/system/
sudo sed -i -e 's|^User=.*|User=content|' -e 's|^Group=.*|Group=content|' \
    -e 's|^WorkingDirectory=.*|WorkingDirectory=/opt/content-factory|' \
    -e 's|^EnvironmentFile=.*|EnvironmentFile=/opt/content-factory/.env|' \
    -e 's|^ExecStart=.*|ExecStart=/opt/content-factory/.venv/bin/python -m content_factory daemon|' \
    /etc/systemd/system/content-factory.service
sudo systemctl daemon-reload
sudo systemctl enable --now content-factory
```

## 3. Настройка .env

Минимум для работы:

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID_TECH_AI=...
# ... остальные каналы (см. .env.example)
CONTENT_FACTORY_DRY_RUN=true      # сначала dry-run, потом false
```

Затем: бот — админ в каждом канале (право «Публикация сообщений»),
`python -m content_factory sources check`, `run --channel all --dry-run`,
и только после проверки текстов — `CONTENT_FACTORY_DRY_RUN=false`.

## 4. LLM на сервере

- Лёгкий вариант без GPU: **Ollama Cloud** (ключ `OLLAMA_API_KEY`; как основной
  провайдер уже настроен в `config/settings.yaml`) — ничего ставить не нужно.
- Полностью локально: `ollama pull qwen2.5:7b` и `llm.provider: ollama`
  (см. [llm.md](llm.md)); ARM-сервер тянет 7B на CPU, но медленно — под 144
  поста/сутки лучше 3B–7B + fallback на облако.

## 5. Проверка и обслуживание

```bash
systemctl status content-factory --no-pager
journalctl -u content-factory -f          # логи
sudo -u content /opt/content-factory/.venv/bin/python -m content_factory report
```

- Обновление: `rsync` проекта в `/opt/content-factory` (кроме `.env`, `data`) →
  `systemctl restart content-factory`.
- Бэкап: см. [backup-onedrive.md](backup-onedrive.md) (rclone, `data/`).
- Простаивающие Always Free-ресурсы Oracle может отозвать; cron-нагрузка завода
  считается активностью, но мониторинг (канал/алерт) стоит держать.

## 6. Ограничения из РФ

- `cloud.oracle.com` из этой сети отдаёт 403 — консоль открывается через VPN или
  с другого устройства; сам сервер после создания работает без VPN (Telegram
  Bot API через релей, см. [pipedream-relay.md](pipedream-relay.md)).
- Если Oracle не даёт аккаунт — есть готовый запуск без сервера:
  [cloud-actions.md](cloud-actions.md).
