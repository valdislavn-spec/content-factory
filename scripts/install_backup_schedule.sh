#!/usr/bin/env bash
# Устанавливает ежедневный бэкап контент-завода в launchd (без root).
# Запуск: bash scripts/install_backup_schedule.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${ROOT}/../tools/markitdown-venv/bin/python"
if [ ! -x "${PY}" ]; then
  PY="$(command -v python3)"
fi
PLIST="${HOME}/Library/LaunchAgents/com.contentfactory.backup.plist"
LOG_DIR="${ROOT}/data/logs"
mkdir -p "${HOME}/Library/LaunchAgents" "${LOG_DIR}"

cat > "${PLIST}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.contentfactory.backup</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PY}</string>
    <string>${ROOT}/scripts/backup_onedrive.py</string>
    <string>--verbose</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT}</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>3</integer>
    <key>Minute</key>
    <integer>30</integer>
  </dict>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/backup.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/backup.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)" "${PLIST}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "${PLIST}"
launchctl enable "gui/$(id -u)/com.contentfactory.backup"
echo "Готово: ${PLIST} (ежедневно в 03:30, лог: ${LOG_DIR}/backup.log)"
