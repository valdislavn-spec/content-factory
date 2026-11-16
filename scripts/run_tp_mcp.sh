set -euo pipefail

CF_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="$(cd "$CF_ROOT/.." && pwd)"
ROOT="$WORKSPACE/tools/theYahia-travelpayouts-mcp"
ENV_FILE="$CF_ROOT/.env"
NODE="${NODE:-/Users/vd/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/node/bin/node}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  . "$ENV_FILE"
  set +a
fi

export TRAVELPAYOUTS_TOKEN="${TRAVELPAYOUTS_API_TOKEN:?TRAVELPAYOUTS_API_TOKEN is missing}"
export TRAVELPAYOUTS_MARKER="${TRAVELPAYOUTS_MARKER:-674170}"
export TRAVELPAYOUTS_TRS="${TRAVELPAYOUTS_TRS:-597672}"
export TRAVELPAYOUTS_CURRENCY="${TRAVELPAYOUTS_CURRENCY:-usd}"
export TRAVELPAYOUTS_MARKET="${TRAVELPAYOUTS_MARKET:-us}"
export TRAVELPAYOUTS_LOCALE="${TRAVELPAYOUTS_LOCALE:-en}"

exec "$NODE" "$ROOT/node_modules/tsx/dist/cli.mjs" "$ROOT/src/index.ts"
