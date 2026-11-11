# World News API MCP Server

Скачан и собран локально:

- репозиторий: https://github.com/ddsky/world-news-api-mcp
- путь: `tools/world-news-api-mcp`
- commit: `001fd3b`
- версия: `1.0.0`
- лицензия: ISC
- Node: >=18 (используется Node 24 из Zed)

## Что это

MCP-сервер для [World News API](https://worldnewsapi.com/): даёт AI-агенту
доступ к поиску новостей, топ-новостям, статьям, первоисточникам и гео-данным.

Инструменты:

| Инструмент | Что делает |
|---|---|
| `search_news` | поиск по тексту, стране, языку, датам, категориям, sentiment |
| `get_top_news` | топ-новости страны на языке |
| `retrieve_newspaper_front_page` | первые полосы газет (платно) |
| `retrieve_news_articles` | статьи по ID |
| `extract_news` | извлечь статью по URL |
| `extract_news_links` | ссылки на новости с сайта |
| `search_news_sources` | проверить источник |
| `get_geo_coordinates` | координаты для `location-filter` |

## Установка (уже сделана)

```bash
cd tools/world-news-api-mcp
export PATH="/Users/vd/Library/Application Support/Zed/node/node-v24.22.1-darwin-arm64/bin:$PATH"
npm install --cache ./.npm-cache
npm run build
```

Проверка без ключа:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | ./run.sh
```

Должен вернуться JSON со списком 8 инструментов.

## API-ключ

1. Зарегистрируйся: https://worldnewsapi.com/register
2. Возьми ключ в консоли: https://worldnewsapi.com/console/
3. Добавь в окружение:

```bash
export WORLD_NEWS_API_KEY="..."
```

Или в `.env` проекта:

```bash
WORLD_NEWS_API_KEY=...
```

В `content-factory` уже есть адаптер `worldnews` и скрипт:

```bash
python3 scripts/set_worldnews_key.py
```

Ключ общий: и MCP-сервер, и `content-factory` используют
`WORLD_NEWS_API_KEY`. Не запускай оба одновременно на одном лимите.

## Лимиты

Официальный free-план на 07.11.2026:

- **50 points/day**;
- 1 request/s, 1 concurrent;
- история 1 месяц;
- front pages недоступны;
- **требуется обратная ссылка** на worldnewsapi.com.

В README репозитория указано 150 запросов/день — это устаревшая информация.
Ориентируйся на официальный pricing.

## Подключение к Zed

Добавь в `~/.config/zed/settings.json` в `context_servers`:

```json
"world-news-api": {
  "command": "/Users/vd/Documents/deepseek-harness/default-workspace/tools/world-news-api-mcp/run.sh",
  "env": {
    "WORLD_NEWS_API_KEY": "вставь_ключ"
  }
}
```

Или без wrapper:

```json
"world-news-api": {
  "command": "/Users/vd/Library/Application Support/Zed/node/node-v24.22.1-darwin-arm64/bin/node",
  "args": [
    "/Users/vd/Documents/deepseek-harness/default-workspace/tools/world-news-api-mcp/dist/index.js"
  ],
  "env": {
    "WORLD_NEWS_API_KEY": "вставь_ключ"
  }
}
```

Не коммить ключ в git.

## Claude Desktop

Конфиг уже создан:

```
~/Library/Application Support/Claude/claude_desktop_config.json
```

Содержимое:

```json
{
  "mcpServers": {
    "world-news-api": {
      "command": "/Users/vd/Documents/deepseek-harness/default-workspace/tools/world-news-api-mcp/run.sh"
    }
  }
}
```

Ключ в конфиг не записан: `run.sh` сам читает `WORLD_NEWS_API_KEY` из
`content-factory/.env`. Поэтому после добавления ключа достаточно перезапустить
Claude Desktop.

Если Claude Desktop ещё не установлен — конфиг уже на месте и подхватится
после установки/запуска. Если там уже были другие MCP-серверы, добавь
`world-news-api` внутрь существующего `mcpServers`, не заменяй весь файл.

Проверка:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | tools/world-news-api-mcp/run.sh
```

Должно вернуться 8 инструментов.

## Пример вызова

```json
{
  "name": "search_news",
  "arguments": {
    "text": "artificial intelligence",
    "language": "en",
    "categories": "technology",
    "number": 5
  }
}
```

Или топ-новости США:

```json
{
  "name": "get_top_news",
  "arguments": {
    "source-country": "us",
    "language": "en"
  }
}
```

## Важно

- Репозиторий маленький (10 ★, последний коммит август 2025), ISC.
- Перед продом проверь код и обработку ошибок.
- Free-план требует backlink; если сайта нет — проверь условия.
- MCP-сервер не заменяет `content_factory/sources/worldnews.py`: это
  дополнительный интерфейс для агента, а не runtime контент-завода.
- При ошибках `401` — ключ, `402` — квота, `429` — rate limit.
