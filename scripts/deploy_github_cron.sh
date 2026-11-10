#!/usr/bin/env bash
# Деплой Cloudflare-планировщика GitHub Actions (cron -> workflow_dispatch).
# Требует CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, GITHUB_TOKEN,
# LINK_TRACKER_ADMIN_TOKEN в .env (или окружении).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ -f .env ]] && { set -a; source .env; set +a; }
: "${CLOUDFLARE_API_TOKEN:?}" "${CLOUDFLARE_ACCOUNT_ID:?}" "${GITHUB_TOKEN:?}"
ADMIN="${LINK_TRACKER_ADMIN_TOKEN:-$GITHUB_TOKEN}"
API="https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}"
NAME=github-cron
REPO=valdislavn-spec/content-factory

curl -s -X PUT "$API/workers/scripts/$NAME" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  -F 'metadata={"main_module":"worker.js"};type=application/json' \
  -F "worker.js=@infra/cloudflare/github-cron/worker.js;type=application/javascript+module" \
  -o /dev/null -w 'upload HTTP %{http_code}\n'

for pair in "GITHUB_TOKEN=$GITHUB_TOKEN" "REPO=$REPO" "ADMIN_TOKEN=$ADMIN" "REF=main"; do
  key="${pair%%=*}"; value="${pair#*=}"
  curl -s -X PUT "$API/workers/scripts/$NAME/secrets" \
    -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H 'content-type: application/json' \
    -d "$(python3 -c 'import json,sys;print(json.dumps({"name":sys.argv[1],"text":sys.argv[2],"type":"secret_text"}))' "$key" "$value")" \
    -o /dev/null
  echo "secret $key set"
done

curl -s -X PUT "$API/workers/scripts/$NAME/schedules" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H 'content-type: application/json' \
  -d '[{"cron":"17 10,14,16,18,22 * * *"},{"cron":"10 3 * * *"},{"cron":"0 */5 * * *"}]' \
  -o /dev/null -w 'schedules HTTP %{http_code}\n'

curl -s -X POST "$API/workers/scripts/$NAME/subdomain" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H 'content-type: application/json' \
  -d '{"enabled":true}' -o /dev/null -w 'subdomain HTTP %{http_code}\n'

SUBDOMAIN=$(curl -s -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" "$API/workers/subdomain" \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['result']['subdomain'])")
echo "URL: https://${NAME}.${SUBDOMAIN}.workers.dev"
