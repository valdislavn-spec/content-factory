# Генерация изображений: бесплатно без ключа + Leonardo на будущее

## 1. Провайдеры

| Провайдер | Ключ | Цена | Из РФ | Особенности |
|---|---|---|---|---|
| **Pollinations** | не нужен | бесплатно | ✅ работает | 1 изображение / 45 с на IP; небольшой watermark; ретрай уже встроен |
| **Leonardo.ai** | `LEONARDO_API_KEY` | платно (API Credits, $) | через API | лучшее качество, модели Lucid Origin/Realism, Ideogram; ключа пока нет |
| **HuggingFace** | `HUGGINGFACE_API_KEY` (есть) | free tier/лимиты | ❌ DNS блокируется локально, в Actions работает | FLUX.1-schnell |

Опционально для Pollinations: `POLLINATIONS_TOKEN` (pollen-ключ) снимает лимит
1/45 с и watermark — если появится.

## 2. CLI

```bash
# бесплатно, без ключа
python scripts/image_gen.py "editorial illustration, AI chips, blue neon light"

# размер/провайдер/воспроизводимость
python scripts/image_gen.py "..." --width 768 --height 768 --seed 42
python scripts/image_gen.py "..." --provider huggingface   # если HF доступен

# только посмотреть доступные провайдеры
python scripts/image_gen.py x --dry-run
```

Файлы сохраняются в `assets/generated/` (в .gitignore).

## 3. MCP-сервер

`tools/image_mcp.py` — stdlib, без зависимостей:

| Инструмент | Что делает |
|---|---|
| `image_generate` | генерирует и сохраняет файл (`provider`, `width/height`, `model`, `seed`, `out_dir`) |
| `image_providers` | показывает доступные провайдеры (по наличию ключей) |

```json
{"mcpServers": {"images": {
  "command": ".../content-factory/.venv/bin/python",
  "args": [".../content-factory/tools/image_mcp.py"],
  "env": {"POLLINATIONS_TOKEN": ""}
}}}
```

Проверка:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | .venv/bin/python tools/image_mcp.py
```

## 4. Пример (сгенерирован без ключа)

`assets/generated/pollinations-*.jpg` — тестовая картинка «AI data center, blue neon»:
512×512, ~40 КБ, сгенерирована Pollinations за один запрос.

## 5. Подключение к постам

1. сгенерировать картинку под тему поста (1 промпт на пост);
2. положить в `assets/generated/` или `assets/covers/`;
3. отправить как фото к посту (`sendPhoto`) — карточка Pillow остаётся
   fallback'ом, когда картинка не нужна/не сгенерировалась.

Если нужно — добавлю шаг «иллюстрация к посту» в `pipeline.py`:
- генерация только для `story/analysis` в дневных слотах;
- лимит N генераций/сутки и стоимость;
- автоматический fallback на карточку при ошибке/лимите.
