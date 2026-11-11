#!/usr/bin/env bash
# Деплой Cloudflare Worker «price-alerts» (BingX → Telegram, каждую минуту).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ -f .env ]] && { set -a; source .env; set +a; }
: "${CLOUDFLARE_API_TOKEN:?}" "${CLOUDFLARE_ACCOUNT_ID:?}" "${TELEGRAM_BOT_TOKEN:?}"
NAME=price-alerts
API="https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}"
ADMIN="${LINK_TRACKER_ADMIN_TOKEN:-$CLOUDFLARE_API_TOKEN}"

KV_ID=$(curl -s -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" "$API/storage/kv/namespaces" \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print(next((n['id'] for n in d.get('result',[]) if n.get('title')=='price-alerts-state'),''))")
if [[ -z "$KV_ID" ]]; then
  KV_ID=$(curl -s -X POST -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H 'content-type: application/json' \
    -d '{"title":"price-alerts-state"}' "$API/storage/kv/namespaces" \
    | python3 -c "import json,sys;print(json.load(sys.stdin)['result']['id'])")
  echo "KV created: $KV_ID"
fi
echo "KV: $KV_ID"

META=$(python3 - "$KV_ID" <<'PY'
import json,sys
kv=sys.argv[1]
meta={
 "main_module":"worker.js",
 "compatibility_date":"2026-11-01",
 "bindings":[
   {"type":"kv_namespace","name":"STATE","namespace_id":kv},
   {"type":"secret_text","name":"TELEGRAM_BOT_TOKEN","text":__import__('os').environ['TELEGRAM_BOT_TOKEN']},
   {"type":"secret_text","name":"ADMIN_TOKEN","text":__import__('os').environ.get('ADMIN_TOKEN','')},
 ]
}
print(json.dumps(meta))
PY
)
ADMIN_TOKEN_VALUE="$ADMIN" META="$META" python3 - <<'PY'
import json, os
meta=json.loads(os.environ["META"])
for b in meta["bindings"]:
    if b.get("name")=="ADMIN_TOKEN": b["text"]=os.environ["ADMIN_TOKEN_VALUE"]
open('/tmp/price-alerts-meta.json','w').write(json.dumps(meta))
PY

curl -s -X PUT "$API/workers/scripts/$NAME" -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  -F 'metadata=@/tmp/price-alerts-meta.json;type=application/json' \
  -F "worker.js=@infra/cloudflare/price-alerts/worker.js;type=application/javascript+module" \
  -o /tmp/price-alerts-upload.json -w 'upload HTTP %{http_code}\n'

curl -s -X PUT "$API/workers/scripts/$NAME/schedules" -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H 'content-type: application/json' \
  -d '[{"cron":"* * * * *"}]' -o /dev/null -w 'schedule HTTP %{http_code}\n'
curl -s -X POST "$API/workers/scripts/$NAME/subdomain" -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H 'content-type: application/json' \
  -d '{"enabled":true}' -o /dev/null -w 'subdomain HTTP %{http_code}\n'

SUBDOMAIN=$(curl -s -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" "$API/workers/subdomain" \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['result']['subdomain'])")
echo "URL: https://${NAME}.${SUBDOMAIN}.workers.dev"
