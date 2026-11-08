# Leonardo.ai — генерация изображений для постов

Leonardo.ai умеет генерировать иллюстрации по текстовому промпту. Для фабрики
это картинки к постам, обложки для кросс-промо и материалы для превью.

## 1. Ключ и доступ

1. Войдите в <https://app.leonardo.ai/api-access>;
2. Купите **API Credits** (API-план отдельный от веб-подписки; оплата в $);
3. **Create New Key** → скопируйте ключ, положите в env `LEONARDO_API_KEY`.

Ключ не коммитить: `.env` в `.gitignore`, в Actions — GitHub Secret.

## 2. Два способа подключения

### Вариант A — нативный MCP Leonardo (OAuth не нужен, header API-Key)

В настройках MCP DSH добавить remote-сервер:

```json
{
  "mcpServers": {
    "leonardo-ai": {
      "url": "https://mcp.leonardo.ai/v1/mcp",
      "headers": {"API-Key": "ваш_ключ"}
    }
  }
}
```

Инструмент: `generate-image` (Lucid Origin, Lucid Realism, Ideogram 3.0).

### Вариант B — наш stdlib MCP-сервер (полный API, скачивание файлов)

```json
{
  "mcpServers": {
    "leonardo": {
      "command": "/Users/vd/Documents/deepseek-harness/default-workspace/content-factory/.venv/bin/python",
      "args": ["/Users/vd/Documents/deepseek-harness/default-workspace/content-factory/tools/leonardo_mcp.py"],
      "env": {"LEONARDO_API_KEY": "ваш_ключ"}
    }
  }
}
```

Инструменты:

| Инструмент | Что делает |
|---|---|
| `leonardo_generate` | создаёт генерацию (async), возвращает `generation_id` |
| `leonardo_generation` | статус + ссылки на изображения |
| `leonardo_download` | ждёт завершения и сохраняет файлы в `assets/generated/` |
| `leonardo_list_models` | список платформенных моделей |

Проверка:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | LEONARDO_API_KEY=... .venv/bin/python tools/leonardo_mcp.py
```

## 3. CLI без MCP

```bash
# посмотреть payload (ничего не тратит)
python scripts/leonardo_image.py "cinematic AI chip close-up" --dry-run

# реальная генерация + скачивание в assets/generated/
LEONARDO_API_KEY=... python scripts/leonardo_image.py \
  "editorial illustration, AI data center, blue light" \
  --width 1024 --height 1024 --num 2
```

Параметры: `--model`, `--width/--height` (512–1536, кратно 8), `--num` (1–4),
`--style-uuid`, `--alchemy`, `--contrast`, `--out-dir`, `--timeout`.

## 4. API, который используется

База: `https://cloud.leonardo.ai/api/rest/v1`, заголовок `Authorization: Bearer <key>`.

- `POST /generations` → `{sdGenerationJob: {generationId}}`;
- `GET /generations/{id}` → `{generations_by_pk: {status, generated_images:[{url}]}}`;
- `GET /platform-models` — модели;
- стили/модели по умолчанию: Lucid Origin `7b592283-...`, Dynamic `111dc692-...`.

Статусы: `PENDING` → `COMPLETE` / `FAILED`. Обычно 10–60 секунд.

## 5. Стоимость и безопасность

- API платный: каждая генерация списывает кредиты/деньги — следите за балансом
  на странице API Access; для тестов используйте 1 изображение 512–768 px;
- ключ даёт доступ к аккаунту Leonardo (генерации, история) — храните в env;
- промпты и результаты сохраняются в аккаунте; не отправляйте секреты;
- наш MCP не удаляет и не меняет историю генераций — только создаёт и читает.

## 6. Интеграция с постами

`assets/generated/*.png` можно прикреплять к постам через существующий пайплайн
(карточки уже рендерятся Pillow; для «живой» иллюстрации положите файл в
`assets/covers/` или передайте в `sendPhoto`). Если нужно — добавлю шаг
«иллюстрация к посту» в `pipeline.py` с dry-run и лимитом стоимости.

## 7. Ключа нет?

Пока нет `LEONARDO_API_KEY`/API-кредитов — используйте бесплатный
Pollinations без ключа: [docs/image-generation.md](image-generation.md)
(`python scripts/image_gen.py "..."`). Leonardo-сервер уже готов и заработает
сразу после добавления ключа.
