#!/usr/bin/env bash
# =====================================================================
#  Установка контент-завода: venv, зависимости, .env, demo.
#
#  Запуск из любой папки:
#      bash scripts/install.sh
#
#  Скрипт идемпотентный: повторный запуск не ломает уже готовую установку.
#  Требуется Python 3.9+ (python3 или python в PATH).
# =====================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

echo "===================================================================="
echo " Установка контент-завода"
echo " Каталог проекта: $ROOT"
echo "===================================================================="

# --- 1. Python ---------------------------------------------------------
PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo
    echo "ОШИБКА: не найден Python 3.9+."
    echo "Установите Python с https://www.python.org/downloads/ и повторите."
    echo "Linux (Ubuntu/Debian): sudo apt install python3 python3-venv python3-pip"
    exit 1
fi
echo "[1/5] Python: $("$PYTHON" --version 2>&1) ($(command -v "$PYTHON"))"

# --- 2. Виртуальное окружение -----------------------------------------
VENV_PY="$ROOT/.venv/bin/python"
if [ -x "$VENV_PY" ]; then
    echo "[2/5] Виртуальное окружение уже существует: .venv"
else
    echo "[2/5] Создаю виртуальное окружение .venv ..."
    "$PYTHON" -m venv "$ROOT/.venv"
    if [ ! -x "$VENV_PY" ]; then
        echo "ОШИБКА: не удалось создать .venv."
        echo "Linux: возможно, нужен пакет python3-venv."
        exit 1
    fi
fi

# --- 3. Зависимости ----------------------------------------------------
echo "[3/5] Устанавливаю зависимости (PyYAML) ..."
"$VENV_PY" -m pip install --upgrade pip >/dev/null 2>&1 || true
"$VENV_PY" -m pip install -r "$ROOT/requirements.txt"

# --- 4. .env и каталоги ------------------------------------------------
echo "[4/5] Готовлю .env и каталоги ..."
if [ ! -f "$ROOT/.env" ] && [ -f "$ROOT/.env.example" ]; then
    cp "$ROOT/.env.example" "$ROOT/.env"
    echo "      Создан .env из .env.example — заполните TELEGRAM_BOT_TOKEN и id каналов."
elif [ -f "$ROOT/.env" ]; then
    echo "      .env уже существует — не трогаю."
else
    echo "      ВНИМАНИЕ: не найден .env.example — создайте .env вручную."
fi
"$VENV_PY" -m content_factory init >/dev/null || true
mkdir -p "$ROOT/data/logs" "$ROOT/data/outbox" "$ROOT/data/reports"

# --- 5. Демо -----------------------------------------------------------
echo "[5/5] Запускаю офлайн-демо (без сети, без токенов) ..."
if "$VENV_PY" -m content_factory demo; then
    echo
    echo "Демо выполнено успешно."
else
    echo
    echo "ВНИМАНИЕ: демо не запустилось. Это не мешает установке:"
    echo "  - проверьте, что на месте samples/demo_articles.json;"
    echo "  - подробности в data/logs/factory.log."
fi

# --- Итог --------------------------------------------------------------
echo
echo "===================================================================="
echo " Установка завершена."
echo
echo " Дальнейшие шаги:"
echo "   1) Заполните .env: TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID_*"
echo "   2) Добавьте бота администратором в каждый канал"
echo "      (право «Публикация сообщений»)."
echo "   3) Проверьте источники:"
echo "        ./.venv/bin/python -m content_factory sources check"
echo "   4) Безопасный прогон:"
echo "        ./.venv/bin/python -m content_factory run --channel all --dry-run"
echo "   5) Публикация (после проверки текстов):"
echo "        CONTENT_FACTORY_DRY_RUN=false ./.venv/bin/python -m content_factory run --channel all"
echo "   6) Автономная работа:"
echo "        bash scripts/run-daemon.sh"
echo
echo " Подробная инструкция: docs/setup.md"
echo "===================================================================="
