#!/usr/bin/env bash
# Деплой воркера-трекера ссылок на Cloudflare (API, без wrangler).
#   bash scripts/deploy_link_tracker.sh            # создать KV (если нет), залить код, секреты, включить subdomain
#   bash scripts/deploy_link_tracker.sh --update   # только обновить код/секреты
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -f .env ]]; then set -a; source .env; set +a; fi
: "${CLOUDFLARE_API_TOKEN:?CLOUDFLARE_API_TOKEN не задан}"
: "${CLOUDFLARE_ACCOUNT_ID:?CLOUDFLARE_ACCOUNT_ID не задан}"

API="https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}"
WORKER_NAME="links-tracker"
WORKER_DIR="$ROOT/infra/cloudflare/links-tracker"
SCRIPT="$WORKER_DIR/worker.js"
TITLE="content-factory-links"
UPDATE_ONLY="${1:-}"

D1_NAME="links-tracker"
D1_ID=$(curl -s -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  "$API/d1/database" \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print(next((x['uuid'] for x in (d.get('result') or []) if x.get('name')=='$D1_NAME'),''))")
if [[ -z "$D1_ID" ]]; then
  D1_ID=$(curl -s -X POST -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H 'content-type: application/json' \
    -d "{\"name\":\"$D1_NAME\"}" "$API/d1/database" \
    | python3 -c "import json,sys;print((json.load(sys.stdin).get('result') or {}).get('uuid',''))")
  echo "D1 создана: $D1_ID"
else
  echo "D1: $D1_ID"
fi
: "${D1_ID:?D1 database не найдена}"

# Схема (идемпотентно)
for SQL in \
  "CREATE TABLE IF NOT EXISTS links (code TEXT PRIMARY KEY, target TEXT NOT NULL, channel TEXT, network TEXT, label TEXT, active INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT);" \
  "CREATE TABLE IF NOT EXISTS clicks (code TEXT NOT NULL, day TEXT NOT NULL, count INTEGER DEFAULT 0, last_click TEXT, PRIMARY KEY (code, day));" \
  "CREATE TABLE IF NOT EXISTS subscribers (email TEXT PRIMARY KEY, source TEXT, lang TEXT, created_at TEXT);" \
  "CREATE TABLE IF NOT EXISTS growth_queue (id TEXT PRIMARY KEY, platform TEXT NOT NULL, due TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', payload TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, published_at TEXT, published_url TEXT, message_id INTEGER, updated_at TEXT NOT NULL);" \
  "CREATE INDEX IF NOT EXISTS idx_growth_queue_due ON growth_queue(platform, status, due);" ; do
  curl -s -X POST -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H 'content-type: application/json' \
    -d "$(python3 -c "import json,sys;print(json.dumps({'sql':sys.argv[1]}))" "$SQL")" \
    "$API/d1/database/$D1_ID/query" -o /dev/null -w 'd1 schema HTTP %{http_code}\n'
done

META=$(python3 -c "import json;print(json.dumps({'main_module':'worker.js','compatibility_date':'2026-11-08','bindings':[{'type':'d1','name':'DB','id':'$D1_ID'}]}))")
curl -s -X PUT "$API/workers/scripts/$WORKER_NAME" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  -F "metadata=$META;type=application/json" \
  -F "worker.js=@$SCRIPT;filename=worker.js;type=application/javascript+module" \
  -o /tmp/links-deploy.json -w 'deploy HTTP %{http_code}\n'
python3 -c "import json;d=json.load(open('/tmp/links-deploy.json'));print('ok:',d.get('success'),'errors:',d.get('errors'))"

if [[ -n "${LINK_TRACKER_ADMIN_TOKEN:-}" ]]; then
  curl -s -X PUT "$API/workers/scripts/$WORKER_NAME/secrets" \
    -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H 'content-type: application/json' \
    -d "{\"name\":\"ADMIN_TOKEN\",\"text\":\"$LINK_TRACKER_ADMIN_TOKEN\",\"type\":\"secret_text\"}" \
    -o /dev/null -w 'admin secret HTTP %{http_code}\n'
fi
if [[ -n "${LINK_TRACKER_STATS_TOKEN:-}" ]]; then
  curl -s -X PUT "$API/workers/scripts/$WORKER_NAME/secrets" \
    -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H 'content-type: application/json' \
    -d "{\"name\":\"STATS_TOKEN\",\"text\":\"$LINK_TRACKER_STATS_TOKEN\",\"type\":\"secret_text\"}" \
    -o /dev/null -w 'stats secret HTTP %{http_code}\n'
fi

if [[ -n "${KIT_WEBHOOK_SECRET:-}" ]]; then
  curl -s -X PUT "$API/workers/scripts/$WORKER_NAME/secrets" \
    -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H 'content-type: application/json' \
    -d "{\"name\":\"KIT_WEBHOOK_SECRET\",\"text\":\"$KIT_WEBHOOK_SECRET\",\"type\":\"secret_text\"}" \
    -o /dev/null -w 'kit webhook secret HTTP %{http_code}\n'
fi

if [[ -n "${PINTEREST_CAPI_TOKEN:-}" ]]; then
  curl -s -X PUT "$API/workers/scripts/$WORKER_NAME/secrets" \
    -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H 'content-type: application/json' \
    -d "{\"name\":\"PINTEREST_CAPI_TOKEN\",\"text\":\"$PINTEREST_CAPI_TOKEN\",\"type\":\"secret_text\"}" \
    -o /dev/null -w 'pinterest capi token HTTP %{http_code}\n'
fi
if [[ -n "${PINTEREST_AD_ACCOUNT_ID:-}" ]]; then
  curl -s -X PUT "$API/workers/scripts/$WORKER_NAME/secrets" \
    -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H 'content-type: application/json' \
    -d "{\"name\":\"PINTEREST_AD_ACCOUNT_ID\",\"text\":\"$PINTEREST_AD_ACCOUNT_ID\",\"type\":\"secret_text\"}" \
    -o /dev/null -w 'pinterest ad account HTTP %{http_code}\n'
fi

curl -s -X POST "$API/workers/scripts/$WORKER_NAME/subdomain" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H 'content-type: application/json' \
  -d '{"enabled":true}' -o /dev/null -w 'subdomain HTTP %{http_code}\n'

SUBDOMAIN=$(curl -s -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" "$API/workers/subdomain" \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['result']['subdomain'])")
echo "URL: https://${WORKER_NAME}.${SUBDOMAIN}.workers.dev"
