#!/usr/bin/env bash
# =====================================================================
#  Запуск демона контент-завода из venv с дублированием вывода в лог.
#
#  Использование:
#      bash scripts/run-daemon.sh              # демон по расписанию
#      bash scripts/run-daemon.sh --once       # одна проверка и выход
#      bash scripts/run-daemon.sh --interval 300
#
#  Остановка: Ctrl+C. Лог: data/logs/daemon.out
#  Для сервера лучше systemd (см. scripts/systemd/).
# =====================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

VENV_PY="$ROOT/.venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
    echo "ОШИБКА: не найдено виртуальное окружение .venv."
    echo "Сначала выполните: bash scripts/install.sh"
    exit 1
fi

LOG_DIR="$ROOT/data/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/daemon.out"

echo "Демон контент-завода запускается..."
echo "Проект:  $ROOT"
echo "Python:  $VENV_PY"
echo "Лог:     $LOG_FILE"
echo "Режим:   $(grep -E '^CONTENT_FACTORY_DRY_RUN=' .env 2>/dev/null || echo 'dry_run из config/settings.yaml')"
echo "Остановка: Ctrl+C"
echo "--------------------------------------------------------------------"

# tee — чтобы видеть вывод и одновременно писать в лог.
# pipefail уже включён: код выхода будет кодом python, а не tee.
exec "$VENV_PY" -m content_factory daemon "$@" 2>&1 | tee -a "$LOG_FILE"
