#!/usr/bin/env bash
# Управление VPN-прокси на macOS: Xray (SOCKS 1080 + HTTP 1081) + системный прокси Wi-Fi.
#
#   bash scripts/mac_vpn.sh on        # запустить Xray и включить системный прокси
#   bash scripts/mac_vpn.sh off       # выключить системный прокси (Xray оставить)
#   bash scripts/mac_vpn.sh status    # состояние + проверка доступности
#   bash scripts/mac_vpn.sh test      # проверка сайтов через HTTP-прокси
#   bash scripts/mac_vpn.sh restart   # перезапустить Xray
#
# Без root: Xray от пользователя, networksetup меняет прокси текущего пользователя.
# Чувствительные сайты в обход прокси: банки, госуслуги, CDN GitHub (см. bypass).
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE="$(cd "$ROOT/.." && pwd)"
XRAY="$WORKSPACE/tools/xray/xray"
CONFIG="$WORKSPACE/tools/xray/config.json"
LOG="$ROOT/data/logs/xray.log"
SERVICE="${MAC_VPN_SERVICE:-Wi-Fi}"
HTTP_PORT="${MAC_VPN_HTTP_PORT:-1081}"
SOCKS_PORT="${MAC_VPN_SOCKS_PORT:-1080}"
BYPASS=(
  "*.local" "169.254/16" "127.0.0.1" "localhost"
  "192.168.0.0/16" "10.0.0.0/8" "172.16.0.0/12"
  "*.sberbank.ru" "*.sber.ru" "*.tbank.ru" "*.tinkoff.ru" "*.vtb.ru" "*.alfabank.ru"
  "*.gazprombank.ru" "*.raiffeisen.ru" "*.gosuslugi.ru" "*.nalog.ru" "*.mos.ru"
  "*.wildberries.ru" "*.ozon.ru" "*.yandex.ru" "*.mail.ru" "*.avito.ru"
  "*.vk.com" "*.ok.ru" "*.dzen.ru" "*.rutube.ru" "*.kinopoisk.ru"
  "*.github.com" "*.githubusercontent.com" "*.workers.dev"
)

xray_pid() { pgrep -f "tools/xray/xray run" | head -1; }

start_xray() {
  if [ -n "$(xray_pid)" ] && curl -s -o /dev/null --max-time 3 -x "http://127.0.0.1:$HTTP_PORT" https://t.me; then
    echo "Xray уже работает (pid $(xray_pid))"
    return 0
  fi
  pkill -f "tools/xray/xray run" 2>/dev/null || true
  sleep 1
  mkdir -p "$(dirname "$LOG")"
  nohup "$XRAY" run -c "$CONFIG" >> "$LOG" 2>&1 &
  sleep 2
  if [ -z "$(xray_pid)" ]; then echo "Xray не запустился — смотрите $LOG"; return 1; fi
  echo "Xray запущен (pid $(xray_pid)): SOCKS 127.0.0.1:$SOCKS_PORT, HTTP 127.0.0.1:$HTTP_PORT"
}

proxy_on() {
  start_xray || return 1
  networksetup -setwebproxy "$SERVICE" 127.0.0.1 "$HTTP_PORT" >/dev/null
  networksetup -setsecurewebproxy "$SERVICE" 127.0.0.1 "$HTTP_PORT" >/dev/null
  networksetup -setproxybypassdomains "$SERVICE" "${BYPASS[@]}" >/dev/null
  echo "Системный прокси включён: $SERVICE → http://127.0.0.1:$HTTP_PORT"
}

proxy_off() {
  networksetup -setwebproxystate "$SERVICE" off >/dev/null
  networksetup -setsecurewebproxystate "$SERVICE" off >/dev/null
  echo "Системный прокси выключен: $SERVICE (Xray продолжает работать, если запущен)"
}

status() {
  echo "=== Xray ==="
  local pid; pid="$(xray_pid)"
  [ -n "$pid" ] && echo "работает: pid $pid" || echo "не запущен"
  ss -tln 2>/dev/null | grep -E ":$HTTP_PORT|:$SOCKS_PORT" >/dev/null && true
  echo ""
  echo "=== Системный прокси ($SERVICE) ==="
  networksetup -getwebproxy "$SERVICE" | sed -n '1,3p'
  echo ""
  echo "=== Доступ через HTTP-прокси ==="
  test_sites
}

test_sites() {
  local ok=0 total=0
  for url in https://t.me https://api.telegram.org https://oauth.telegram.org https://bsky.app https://admin.adminhub.tools https://x.com; do
    total=$((total+1))
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 12 -x "http://127.0.0.1:$HTTP_PORT" "$url" 2>/dev/null)
    echo "  $code  $url"
    [ "$code" != "000" ] && ok=$((ok+1))
  done
  echo "  доступно: $ok/$total"
}

restart() {
  pkill -f "tools/xray/xray run" 2>/dev/null || true
  sleep 1
  start_xray
}

case "${1:-status}" in
  on) proxy_on ;;
  off) proxy_off ;;
  status) status ;;
  test) test_sites ;;
  restart) restart ;;
  *) echo "Использование: $0 on|off|status|test|restart"; exit 2 ;;
esac
