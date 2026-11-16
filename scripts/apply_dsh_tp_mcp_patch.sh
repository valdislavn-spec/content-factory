set -euo pipefail

CF_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE="${DSH_PROFILE_PATCH:-$HOME/.dsh/profiles/desktop/cordis.patch.yml}"
PATCH="$CF_ROOT/config/dsh-travelpayouts-mcp.patch.yml"

if [[ ! -f "$PROFILE" ]]; then
  echo "DSH profile patch not found: $PROFILE" >&2
  exit 1
fi
if grep -q 'id: travelpayouts-mcp' "$PROFILE"; then
  echo "travelpayouts-mcp is already present in $PROFILE"
  exit 0
fi
printf '\n' >> "$PROFILE"
cat "$PATCH" >> "$PROFILE"
echo "Added travelpayouts-mcp to $PROFILE"
echo "Restart DSH to load the 13 Travelpayouts tools."
