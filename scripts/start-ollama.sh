#!/usr/bin/env bash
# =====================================================================
#  Локальная бесплатная LLM для контент-завода (Ollama).
#
#  Бинарник и модели лежат внутри проекта, в data/ollama/ (каталог data/
#  исключён из git) — ключи, аккаунты и платежи не нужны.
#
#  Использование:
#      bash scripts/start-ollama.sh start            # запустить сервер в фоне
#      bash scripts/start-ollama.sh status           # проверить сервер и модели
#      bash scripts/start-ollama.sh pull [модель]    # скачать модель (по умолчанию qwen3.5:9b)
#      bash scripts/start-ollama.sh stop             # остановить сервер
#      bash scripts/start-ollama.sh restart
#      bash scripts/start-ollama.sh logs             # хвост лога
#
#  После запуска в config/settings.yaml должно быть:
#      llm:
#        provider: ollama
#        ollama:
#          base_url: http://127.0.0.1:11434
#          model: qwen3.5:9b
#
#  Остановка контент-завода и Ollama — независимы: если сервера нет,
#  завод автоматически уходит в extractive (см. docs/llm.md §5).
# =====================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OLLAMA_DIR="$ROOT/data/ollama"
DEFAULT_MODEL="${OLLAMA_MODEL:-qwen3.5:9b}"
OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
export OLLAMA_HOST
export HOME="$OLLAMA_DIR/home"          # ключ/настройки Ollama — внутри проекта
export OLLAMA_MODELS="$OLLAMA_DIR/models"
LOG_DIR="$ROOT/data/logs"
LOG_FILE="$LOG_DIR/ollama.log"
PID_FILE="$OLLAMA_DIR/ollama.pid"

mkdir -p "$OLLAMA_DIR/bin" "$OLLAMA_DIR/home" "$OLLAMA_DIR/models" "$LOG_DIR"

# Бинарник: приоритет — локальный, потом системный ollama из PATH.
if [ -x "$OLLAMA_DIR/bin/ollama" ]; then
    BIN="$OLLAMA_DIR/bin/ollama"
elif command -v ollama >/dev/null 2>&1; then
    BIN="$(command -v ollama)"
else
    echo "ОШИБКА: не найден ollama." >&2
    echo "Скачайте CLI: https://github.com/ollama/ollama/releases (файл ollama-darwin.tgz)" >&2
    echo "и распакуйте в $OLLAMA_DIR/bin (или установите Ollama обычным способом)." >&2
    exit 1
fi

is_running() {
    curl -s --max-time 2 "http://$OLLAMA_HOST/api/version" >/dev/null 2>&1
}

start() {
    if is_running; then
        echo "Ollama уже запущена: $(curl -s "http://$OLLAMA_HOST/api/version")"
        return 0
    fi
    nohup "$BIN" serve >>"$LOG_FILE" 2>&1 &
    echo $! >"$PID_FILE"
    for _ in $(seq 1 30); do
        if is_running; then
            echo "Ollama запущена (pid $(cat "$PID_FILE")). API: http://$OLLAMA_HOST"
            echo "Модели: $OLLAMA_MODELS"
            return 0
        fi
        sleep 1
    done
    echo "ОШИБКА: Ollama не поднялась за 30 с. Смотрите лог: $LOG_FILE" >&2
    tail -n 20 "$LOG_FILE" >&2 || true
    return 1
}

stop() {
    if is_running; then
        # Сервер мог быть запущен раньше, не через этот скрипт (pidfile может отсутствовать).
        pkill -f "$OLLAMA_DIR/bin/ollama serve" 2>/dev/null || pkill -f "ollama serve" 2>/dev/null || true
        for _ in $(seq 1 15); do
            is_running || { echo "Ollama остановлена."; rm -f "$PID_FILE"; return 0; }
            sleep 1
        done
        echo "ОШИБКА: не удалось остановить Ollama." >&2
        return 1
    fi
    echo "Ollama не запущена."
    rm -f "$PID_FILE"
}

status() {
    if is_running; then
        echo "Сервер: запущен (http://$OLLAMA_HOST)"
        "$BIN" list
    else
        echo "Сервер: не запущен. Запуск: bash scripts/start-ollama.sh start"
    fi
}

pull() {
    local model="${1:-$DEFAULT_MODEL}"
    start
    echo "Скачиваю модель: $model (один раз; дальше всё работает офлайн)"
    "$BIN" pull "$model"
    "$BIN" list
    echo
    echo "Готово. Убедитесь, что в config/settings.yaml указано model: $model"
}

logs() {
    tail -n "${1:-40}" "$LOG_FILE"
}

case "${1:-start}" in
    start)   start ;;
    stop)    stop ;;
    restart) stop || true; start ;;
    status)  status ;;
    pull)    shift || true; pull "${1:-}" ;;
    logs)    shift || true; logs "${1:-40}" ;;
    *)
        echo "Использование: bash scripts/start-ollama.sh {start|stop|restart|status|pull [модель]|logs [строк]}" >&2
        exit 2
        ;;
esac
