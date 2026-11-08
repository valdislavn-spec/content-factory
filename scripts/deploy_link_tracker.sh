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

if [[ "$UPDATE_ONLY" != "--update" ]]; then
  KV_ID=$(curl -s -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
    "$API/storage/kv/namespaces?per_page=100" \
    | python3 -c "import json,sys;d=json.load(sys.stdin);print(next((x['id'] for x in d.get('result',[]) if x.get('title')=='$TITLE'),''))")
  if [[ -z "$KV_ID" ]]; then
    KV_ID=$(curl -s -X POST -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H 'content-type: application/json' \
      -d "{\"title\":\"$TITLE\"}" "$API/storage/kv/namespaces" \
      | python3 -c "import json,sys;print(json.load(sys.stdin)['result']['id'])")
    echo "KV создан: $KV_ID"
  else
    echo "KV: $KV_ID"
  fi
else
  KV_ID=$(curl -s -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
    "$API/storage/kv/namespaces?per_page=100" \
    | python3 -c "import json,sys;d=json.load(sys.stdin);print(next((x['id'] for x in d.get('result',[]) if x.get('title')=='$TITLE'),''))")
fi
: "${KV_ID:?KV namespace не найден}"

META=$(python3 -c "import json;print(json.dumps({'main_module':'worker.js','compatibility_date':'2026-11-08','bindings':[{'type':'kv_namespace','name':'LINKS','namespace_id':'$KV_ID'}]}))")
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

curl -s -X POST "$API/workers/scripts/$WORKER_NAME/subdomain" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H 'content-type: application/json' \
  -d '{"enabled":true}' -o /dev/null -w 'subdomain HTTP %{http_code}\n'

SUBDOMAIN=$(curl -s -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" "$API/workers/subdomain" \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['result']['subdomain'])")
echo "URL: https://${WORKER_NAME}.${SUBDOMAIN}.workers.dev"
