# Docker / systemd deployment

## Docker (recommended for a VPS)

```bash
cp .env.example .env   # заполнить TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID_* и т.д.
docker compose up -d --build
docker compose logs -f daemon
```

- `data/` смонтирован в контейнер: SQLite и outbox сохраняются между рестартами.
- `restart: unless-stopped` — автоперезапуск после падения/ребута.
- Один контейнер = один daemon. Второй экземпляр остановится на файловой
  блокировке `data/locks/daemon.lock`, а не будет портить SQLite.
- Разовая проверка без запуска демона:

```bash
docker compose run --rm daemon run --channel all --dry-run
```

### Ollama для ML-верификатора кластеризации

Обычный `docker compose up` не тянет тяжёлую модель. Чтобы включить локальный
LLM-верификатор неоднозначных пар, используйте overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.ml.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.ml.yml logs -f ollama-pull
```

- `ollama` — локальный сервер в контейнере, модели в named volume
  `ollama-models` (переживают перезапуск);
- `ollama-pull` — one-shot: скачивает `CLUSTER_VERIFIER_MODEL` при первом
  запуске (~7.6 ГБ для `qwen3.5:9b`);
- `daemon` получает `OLLAMA_HOST=http://ollama:11434`,
  `CLUSTER_VERIFIER=ollama` и таймаут 60 с. Он не блокируется, если загрузка
  модели ещё идёт: первые прогоны используют эвристику, следующие — LLM.

На CPU 9B-модель медленная; для VPS возьмите модель меньше:

```bash
CLUSTER_VERIFIER_MODEL=qwen3:1.7b \
  docker compose -f docker-compose.yml -f docker-compose.ml.yml up -d --build
```

Если Ollama недоступна/модель не скачалась, кластеризация не падает: через
таймаут верификатор отключается и работает быстрая эвристика.

Для ботов (long-polling) используйте **отдельный** контейнер/процесс с тем же
образом, но другим `command`, и отдельный токен — один getUpdates на токен:

```bash
docker run --rm --env-file .env -v "$PWD/data:/app/data" content-factory:local \
  python scripts/telegram-growth-bot.py
```

Не запускайте одновременно `ad_bot.py` и `telegram-growth-bot.py` на одном
токене: второй процесс получит понятную ошибку блокировки.

## systemd (без Docker)

```bash
sudo useradd --system --home /opt/content-factory content-factory
sudo mkdir -p /opt/content-factory
# скопировать проект, создать .env и venv:
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
sudo cp scripts/systemd/content-factory.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now content-factory
sudo journalctl -u content-factory -f
```

`Restart=always` + `RestartSec=10` закрывают требование автоматического
рестарта; `KillSignal=SIGINT` даёт демону корректно завершиться.

## Healthcheck

```bash
docker inspect --format '{{.State.Health.Status}}' $(docker compose ps -q daemon)
```

`healthy` означает, что Python/CLI внутри контейнера живы; состояние
планировщика смотрите в `data/logs/factory.log`.
