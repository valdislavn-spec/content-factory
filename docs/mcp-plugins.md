# Полезные MCP-плагины для контент-фабрики

## Что уже есть у агента

| Сервер | Что даёт |
|---|---|
| GitHub MCP | репозиторий, Actions, Issues/PR, поиск по коду |
| Firecrawl | search / scrape / crawl / map / research |
| Playwright | браузер: t.me, админки, проверки |
| mem0 | долговременная память |
| Docker gateway | GSC MCP, GA4-инструменты, code-mode, fetch, sequential-thinking |

## Каталог gateway: что ещё есть

В каталоге MCP-gateway доступны (имена для `mcp-add`):

- `SQLite` / `database-server` — запросы к SQLite/Postgres/MySQL;
- `tavily` — поиск и extract (нужен `tavily.api_token`);
- `mcp-hackernews` — Hacker News;
- `cloudflare-radar` — интернет-тренды Cloudflare;
- `gsc` / `ga4` — Google Search Console / Analytics (нужен `google_seo.sa_json`);
- `github`, `firecrawl`, `exa`, `duckduckgo`, `brave` — поиск/репозитории;
- `apify-mcp-server` — скрапинг через Apify.

**Важно:** подключение из сессии заблокировано политикой gateway
(`mcp-add SQLite/tavily/mcp-hackernews` возвращает `server is not enabled and no
enforcing policy is available…`). Эквиваленты уже есть в `factory-mcp`:
`factory_query`/`factory_schema` ≈ SQLite, `web_search` ≈ tavily,
`hackernews_top` ≈ mcp-hackernews.
(`server is not enabled and no enforcing policy is available to authorize
catalog access`). Серверы включает владелец окружения — через профиль/политику
gateway, после чего агент может вызвать:

```
mcp-add(name="tavily", activate=true)
mcp-config-set(server="tavily", config={...})
```

## Готовый вариант без политики: `factory-mcp`

В репозитории лежит собственный read-only MCP-сервер — не требует доступа к
каталогу и ничего не пишет в БД.

Файлы:

- `tools/factory_mcp.py` — сервер (stdio JSON-RPC 2.0);
- `scripts/db_query.py` — тот же read-only SQL из CLI.

### Инструменты

| Инструмент | Аргументы | Что делает |
|---|---|---|
| `factory_status` | — | каналы, последние посты и запуски |
| `factory_query` | `sql` | только SELECT/WITH/PRAGMA/EXPLAIN, максимум 200 строк |
| `trends_now` | `channel_id`, `language` | Google Trends RSS, CoinGecko, GitHub, HN |
| `factory_schema` | — | таблицы и колонки БД |
| `hackernews_top` | `limit` | топ Hacker News (без ключа) |
| `web_search` | `query`, `max_results` | Tavily, а при 403 (РФ) — Bing News RSS |

### Подключение к DSH

Добавить в MCP-конфиг окружения (файл профиля DSH) запись:

```json
{
  "mcpServers": {
    "factory": {
      "command": "/Users/vd/Documents/deepseek-harness/default-workspace/content-factory/.venv/bin/python",
      "args": ["/Users/vd/Documents/deepseek-harness/default-workspace/content-factory/tools/factory_mcp.py"],
      "env": {
        "FACTORY_DB": "/Users/vd/Documents/deepseek-harness/default-workspace/content-factory/data/factory.sqlite3"
      }
    }
  }
}
```

После перезапуска MCP в сессии появятся инструменты `factory_status`,
`factory_query`, `trends_now`, `web_search`.

### Проверка без DSH

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"factory_status","arguments":{}}}' \
  | .venv/bin/python tools/factory_mcp.py
```

CLI-вариант:

```bash
.venv/bin/python scripts/db_query.py \
  "SELECT channel_id, status, COUNT(*) FROM posts GROUP BY 1,2"
```

### Безопасность

- БД открывается в режиме `mode=ro` (read-only), запись отклоняется валидацией;
- сервер не публикует посты и не меняет состояние фабрики;
- `TAVILY_API_KEY` берётся из `.env`; из РФ Tavily отдаёт 403 — тогда
  используется Bing News RSS без ключа;
- не давайте этому серверу токен бота и не добавляйте write-инструменты —
  для публикаций уже есть пайплайн с dry-run.

## Заметки по локальной сети из РФ

- `api.telegram.org` напрямую недоступен → в локальном `.env` стоит
  `CONTENT_FACTORY_SKIP_SUBSCRIBERS=1`, а публикации идут через relay
  `TELEGRAM_API_BASE`;
- Tavily `api.tavily.com` отдаёт 403, Google News RSS — таймаут; Bing News RSS
  работает и используется как fallback;
- в GitHub Actions (US) Tavily/Google доступны без ограничений.

## Leonardo.ai (генерация изображений)

| Способ | Что это |
|---|---|
| **Нативный hosted MCP** | `https://mcp.leonardo.ai/v1/mcp`, header `API-Key` |
| **Наш `leonardo-mcp`** | `tools/leonardo_mcp.py` — stdlib MCP: generate/poll/download/models |

Подробности и конфиг DSH: [docs/leonardo.md](leonardo.md).

## Генерация изображений (image-mcp)

| Провайдер | Ключ | Статус |
|---|---|---|
| Pollinations | не нужен | ✅ работает из РФ, 1 изображение/45 с |
| Leonardo.ai | `LEONARDO_API_KEY` | ключа нет (API платный) |
| HuggingFace | `HUGGINGFACE_API_KEY` | локально DNS блок, в Actions ок |

Наш stdlib MCP: `tools/image_mcp.py` (`image_generate`, `image_providers`).
Подробности: [docs/image-generation.md](image-generation.md).
