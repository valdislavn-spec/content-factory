#!/usr/bin/env bash
# Автозапуск контент-завода на macOS через launchd.
#
#   bash scripts/install-launchd-macos.sh          # установить и запустить демон
#   bash scripts/install-launchd-macos.sh status   # статус
#   bash scripts/install-launchd-macos.sh uninstall# остановить и удалить
#
# Ставит два агента:
#   1) com.contentfactory.daemon — сам завод (расписание, публикация);
#   2) com.contentfactory.ollama  — локальная LLM (если установлена в data/ollama/),
#      чтобы после перезагрузки завод сразу работал с ней, а не падал в extractive.
#
# Демон работает в фоне, переживает перезагрузку и перезапускается при падении.
# Публикация зависит от .env: пока TELEGRAM_BOT_TOKEN пуст или dry_run=true,
# посты пишутся в data/outbox и никуда не отправляются.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.contentfactory.daemon"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
OLLAMA_LABEL="com.contentfactory.ollama"
OLLAMA_PLIST="$HOME/Library/LaunchAgents/$OLLAMA_LABEL.plist"
PYTHON="$ROOT/.venv/bin/python"
LOG_DIR="$ROOT/data/logs"
OLLAMA_DIR="$ROOT/data/ollama"
OLLAMA_BIN="$OLLAMA_DIR/bin/ollama"

status() {
    if launchctl list | grep -q "$LABEL"; then
        echo "Демон запущен: $LABEL"
        launchctl list | grep "$LABEL" || true
    else
        echo "Демон не запущен."
    fi
    if [ -x "$OLLAMA_BIN" ]; then
        if launchctl list | grep -q "$OLLAMA_LABEL"; then
            echo "Локальная LLM запущена: $OLLAMA_LABEL"
        else
            echo "Локальная LLM не запущена."
        fi
    fi
}

uninstall() {
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    launchctl bootout "gui/$(id -u)/$OLLAMA_LABEL" 2>/dev/null || true
    rm -f "$OLLAMA_PLIST"
    echo "Автозапуск удалён."
}

if [ "${1:-install}" = "status" ]; then status; exit 0; fi
if [ "${1:-install}" = "uninstall" ]; then uninstall; exit 0; fi

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"
if [ ! -x "$PYTHON" ]; then
    echo "Не найден $PYTHON — сначала установите зависимости (.venv)." >&2
    exit 1
fi

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>-m</string>
    <string>content_factory</string>
    <string>daemon</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>60</integer>
  <key>StandardOutPath</key><string>$LOG_DIR/daemon.out.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/daemon.err.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
  </dict>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl load -w "$PLIST"

# Локальная LLM: ставим отдельный агент, если бинарник уже лежит в проекте.
if [ -x "$OLLAMA_BIN" ]; then
    mkdir -p "$OLLAMA_DIR/home" "$OLLAMA_DIR/models"
    cat > "$OLLAMA_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$OLLAMA_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$OLLAMA_BIN</string>
    <string>serve</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>$LOG_DIR/ollama.out.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/ollama.err.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key><string>$OLLAMA_DIR/home</string>
    <key>OLLAMA_MODELS</key><string>$OLLAMA_DIR/models</string>
    <key>OLLAMA_HOST</key><string>127.0.0.1:11434</string>
  </dict>
</dict>
</plist>
PLIST
    launchctl bootout "gui/$(id -u)/$OLLAMA_LABEL" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$OLLAMA_PLIST" 2>/dev/null || launchctl load -w "$OLLAMA_PLIST"
else
    echo "Локальная LLM не найдена в $OLLAMA_BIN — агент Ollama пропущен."
    echo "Поставьте её: bash scripts/start-ollama.sh start (потребуется бинарник)"
fi

sleep 1
status
echo
echo "Логи: $LOG_DIR/daemon.out.log, $LOG_DIR/ollama.out.log"
echo "Остановить: bash scripts/install-launchd-macos.sh uninstall"
