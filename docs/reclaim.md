# Reclaim.ai — стек тайм-блокинга для работы над фабрикой

Reclaim.ai сам находит время в календаре под задачи (задачи, привычки, фокус-блоки)
и перепланирует их, если день сдвинулся. Для проекта это значит: проверки фабрики,
разбор аналитики и ревью контент-плана попадают в календарь автоматически,
а не «когда вспомнилось».

## 1. Быстрый старт (рекомендую)

Ключ: <https://app.reclaim.ai/settings/developer> → **Create API key**.

```bash
cd content-factory
RECLAIM_API_KEY=... .venv/bin/python tools/reclaim_mcp.py   # MCP-сервер (stdio)
RECLAIM_API_KEY=... .venv/bin/python scripts/reclaim_sync.py --apply  # задачи [CF] в Reclaim
```

`scripts/reclaim_sync.py` без `--apply` показывает план, с `--apply` создаёт
недостающие задачи (повторный запуск не плодит дубли — идемпотентность по названию):

- `[CF] Утренняя проверка системы` — 15 мин, P2;
- `[CF] Разбор аналитики каналов` — 45 мин, P3;
- `[CF] Ревью контент-плана на неделю` — 60 мин, P3.

## 2. Подключение к DSH

### Вариант A — наш stdlib MCP (работает здесь и сейчас)

Без внешних зависимостей (в этом окружении pydantic-колёса сторонних пакетов
не проходят проверку подписи macOS, поэтому community-серверы на pydantic/Node
могут не запуститься).

```json
{
  "mcpServers": {
    "reclaim": {
      "command": "/Users/vd/Documents/deepseek-harness/default-workspace/content-factory/.venv/bin/python",
      "args": ["/Users/vd/Documents/deepseek-harness/default-workspace/content-factory/tools/reclaim_mcp.py"],
      "env": {"RECLAIM_API_KEY": "ваш_ключ"}
    }
  }
}
```

Инструменты: `reclaim_whoami`, `reclaim_list_tasks`, `reclaim_create_task`,
`reclaim_complete_task`, `reclaim_list_events`.

Проверка без DSH:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | RECLAIM_API_KEY=... .venv/bin/python tools/reclaim_mcp.py
```

### Вариант B — нативный hosted MCP Reclaim (OAuth)

Reclaim отдаёт собственный MCP-сервер:

- URL: `https://api.app.reclaim.ai/api/mcp`
- OAuth discovery: `https://api.app.reclaim.ai/.well-known/oauth-protected-resource/api/mcp`
- scopes: `read write mcp`, bearer в заголовке.

Добавить как remote MCP в настройках DSH и пройти OAuth-вход в браузере —
локальные пакеты и ключ не нужны.

### Вариант C — community-серверы (на обычной машине)

| Пакет | Запуск | Примечание |
|---|---|---|
| [aaron-nunley/reclaim-mcp](https://github.com/aaron-nunley/reclaim-mcp) | `npx reclaim-mcp` | Node, `RECLAIM_API_KEY` |
| [universalamateur/reclaim-mcp-server](https://github.com/universalamateur/reclaim-mcp-server) | `uvx reclaim-mcp-server` | Python, 40 инструментов, профили |

В этом окружении оба варианта упираются в подпись compiled-зависимостей
(pydantic_core / npm), поэтому основной путь — вариант A или B.

## 3. API, который использует наш сервер

База: `https://api.app.reclaim.ai/api`, заголовок `Authorization: Bearer <key>`.

- `GET /users/current` — проверка ключа;
- `GET /tasks` — список задач; `POST /tasks` — создание;
- `POST /planner/done/task/{id}` — завершить;
- `GET /events?start=&end=` — календарь;
- время в 15-минутных чанках: `timeChunksRequired=4` = 1 час.

## 4. Безопасность

- API-ключ Reclaim = доступ к задачам и календарю (read/write), храните только
  в env/секретах, не коммитьте;
- для экспериментов лучше отдельный аккаунт или ключ с минимальными правами;
- `reclaim_sync.py` создаёт только задачи с маркером `[CF]` и не удаляет чужие;
- завершение задач (`reclaim_complete_task`) меняет состояние аккаунта — не
  давайте этот инструмент автономным агентам без подтверждения.
