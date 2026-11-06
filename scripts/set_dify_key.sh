#!/usr/bin/env bash
# =====================================================================
#  Безопасно записать API-ключ приложения Dify в content-factory/.env
#
#  Запуск:  bash scripts/set_dify_key.sh
#  Ключ вводится скрыто (read -s), не печатается на экран, не попадает
#  в историю shell и не передаётся в чат. Скрипт сам находит/создаёт .env
#  и заменяет строку DIFY_API_KEY= (или добавляет её, если строки нет).
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=".env"

printf 'Вставь API-ключ приложения Dify (начинается с app-), затем Enter: '
if [ -t 0 ]; then
    IFS= read -rs KEY      # ввод скрыт
else
    IFS= read -r KEY       # если ввод пришёл через pipe
fi
printf '\n'

# Убираем пробелы, переводы строк и кавычки, которые могли прилипнуть при копировании.
KEY="${KEY//[[:space:]]/}"
KEY="${KEY%\"}"; KEY="${KEY#\"}"
KEY="${KEY%\'}"; KEY="${KEY#\'}"

if [ -z "$KEY" ]; then
    echo "Пустой ввод — ключ не записан." >&2
    exit 1
fi
case "$KEY" in
    app-*) ;;
    *) echo "Внимание: ключи Dify обычно начинаются с 'app-'. Продолжаю как есть." >&2 ;;
esac

if [ ! -f "$ENV_FILE" ]; then
    cp .env.example "$ENV_FILE"
fi
chmod 600 "$ENV_FILE" 2>/dev/null || true

python3 - "$KEY" <<'PY'
import re
import sys

key = sys.argv[1]
path = ".env"
with open(path, "r", encoding="utf-8") as handle:
    text = handle.read()

new_line = "DIFY_API_KEY=" + key
if re.search(r"(?m)^DIFY_API_KEY=.*$", text):
    text = re.sub(r"(?m)^DIFY_API_KEY=.*$", lambda _match: new_line, text, count=1)
else:
    text = text.rstrip("\n") + "\n\n" + new_line + "\n"

with open(path, "w", encoding="utf-8") as handle:
    handle.write(text)
print("Готово: DIFY_API_KEY записан в .env (значение не выводится).")
PY

echo "Проверка: $(grep -c '^DIFY_API_KEY=app-' "$ENV_FILE" || true) строка с ключом в $ENV_FILE."
echo "Дальше: скажи агенту «ключ вписал» — он переключит provider и запустит llm-test."
