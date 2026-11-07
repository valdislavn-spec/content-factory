# Postman: подключение и коллекция API-проверок

Postman подключён к проекту по **официальному REST API** (`https://api.getpostman.com`
с заголовком `X-Api-Key`). Ключ хранится в `.env` (`POSTMAN_API_KEY`, файл в `.gitignore`) и
никогда не попадает в документацию, коллекцию или git.

> Почему не MCP: MCP-сервер Postman в этой сессии недоступен (нет политики авторизации
> каталога), поэтому интеграция сделана через официальный API и CLI проекта.

## Что уже подключено

| Объект | Где | uid |
|---|---|---|
| Аккаунт | `valdislav-n` (valdislav.n@gmail.com) | — |
| Рабочее пространство | `V. N.'s Workspace` (team) | см. `postman list` |
| Коллекция | `content-factory: API checks` | см. `postman list` |
| Окружение | `content-factory (secrets)` | см. `postman list` |

После `postman install` откройте [postman.com](https://postman.com) → ваше рабочее
пространство: коллекция и окружение уже там.

## Команды

```bash
# проверить ключ и показать аккаунт/workspace/коллекции
./.venv/bin/python -m content_factory postman status

# workspace, коллекции и окружения с uid
./.venv/bin/python -m content_factory postman list

# загрузить коллекцию и окружение из postman/ в рабочее пространство
./.venv/bin/python -m content_factory postman install
./.venv/bin/python -m content_factory postman install --workspace <id>

# скачать существующую коллекцию (uid из `postman list`)
./.venv/bin/python -m content_factory postman export --collection <uid> --out data/postman.json
```

## Что внутри коллекции

`postman/content-factory.postman_collection.json` — 5 папок:

| Папка | Запросы | Зачем |
|---|---|---|
| Telegram Bot API | `getMe`, `getChatMemberCount`, `getChat`, `sendMessage` (отключён) | Проверить токен, узнать точное число подписчиков, резолв `@username` в `chat_id` |
| VK API | `wall.post` (отключён) | Тест публикации через `publishers/vk.py` |
| Dify | `chat-messages` (отключён) | Проверка Dify-приложения (`llm.provider: dify`) |
| Источники и данные роста | RSS Habr, HF SillyFeed, HF top-10k, `t.me/s` | Доступность источников и датасетов роста (см. [tg-growth.md](tg-growth.md)) |
| Postman API | `me` | Проверка самого `POSTMAN_API_KEY` |

У ключевых запросов есть тесты-ассерты (`pm.test`): статус, `ok: true`, число подписчиков,
наличие датасета и т.д. — их видно на вкладке **Tests** и в результатах запуска.

**Секретов в коллекции нет.** Все токены — переменные окружения `content-factory (secrets)`:
`telegram_bot_token`, `telegram_chat_id`, `vk_access_token`, `vk_owner_id`, `dify_api_key`,
`postman_api_key`, `tg_channel_username`. Базы API (`telegram_api_base` и др.) заданы
значениями по умолчанию.

## Как пользоваться

1. Postman → **Environments** → `content-factory (secrets)` → заполните значения секретов
   (не коммитьте их в git и не пересылайте в чаты).
2. Выберите окружение в правом верхнем углу.
3. Откройте коллекцию `content-factory: API checks` → нужную папку → **Send**.
4. Для отключённых запросов (`sendMessage`, `wall.post`, `chat-messages`) снимите галочку
   «Disabled» вручную — они делают реальные публикации.

## Безопасность

- `POSTMAN_API_KEY` лежит только в `.env` (gitignored, права `600`). В `postman/*.json` его нет —
  это проверяет тест `tests/test_postman_integration.py`.
- Ключ был передан в чате, поэтому после настройки **рекомендуется его перевыпустить**:
  Postman → Settings → API keys → удалить старый, создать новый и обновить `.env`.
- Запускать Postman **Monitor** с токеном бота в облаке Postman можно, только осознанно:
  токен окажется в облачном сервисе. Без необходимости не храните секреты в Postman Cloud.

## Ограничения

- `postman install` при повторном вызове создаёт дубликаты коллекции/окружения — старые
  удалите вручную в Postman (или через API).
- `t.me/s` может быть недоступен из некоторых сетей (в локальной сети на 07.11.2026 запросы
  к превью падали по таймауту) — в GitHub Actions/VPS обычно работает.
- Postman API имеет лимиты запросов; CLI делает 4–5 запросов на команду.
- Файлы ассетов: [postman/content-factory.postman_collection.json](../postman/content-factory.postman_collection.json),
  [postman/content-factory.postman_environment.json](../postman/content-factory.postman_environment.json).
