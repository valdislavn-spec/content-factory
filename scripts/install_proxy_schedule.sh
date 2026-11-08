#!/usr/bin/env bash
# Устанавливает/удаляет launchd-агент автозапуска бесплатного SOCKS-прокси.
#
#   bash scripts/install_proxy_schedule.sh            # установить (без root)
#   bash scripts/install_proxy_schedule.sh --uninstall
#
# Агент работает от текущего пользователя, слушает только 127.0.0.1:1080,
# системный прокси НЕ включаёт. Логи: data/logs/free_proxy.log
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${ROOT}/../tools/markitdown-venv/bin/python"
if [ ! -x "${PY}" ]; then
  PY="$(command -v python3)"
fi
PLIST="${HOME}/Library/LaunchAgents/com.contentfactory.free-proxy.plist"
LOG_DIR="${ROOT}/data/logs"

if [ "${1:-}" = "--uninstall" ]; then
  launchctl bootout "gui/$(id -u)" "${PLIST}" 2>/dev/null || true
  rm -f "${PLIST}"
  echo "Агент удалён: ${PLIST}"
  exit 0
fi

mkdir -p "${HOME}/Library/LaunchAgents" "${LOG_DIR}"

cat > "${PLIST}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.contentfactory.free-proxy</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PY}</string>
    <string>${ROOT}/scripts/free_proxy_daemon.py</string>
    <string>--socks-port</string>
    <string>1080</string>
    <string>--check-interval</string>
    <string>120</string>
    <string>--max-failures</string>
    <string>3</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>30</integer>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/free_proxy.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/free_proxy.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)" "${PLIST}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "${PLIST}"
launchctl enable "gui/$(id -u)/com.contentfactory.free-proxy"
echo "Готово: ${PLIST}"
echo "SOCKS: 127.0.0.1:1080 (только локально, системный прокси не меняется)"
echo "Лог: ${LOG_DIR}/free_proxy.log"
echo "Проверка: ../tools/markitdown-venv/bin/python scripts/free_proxy.py test"
