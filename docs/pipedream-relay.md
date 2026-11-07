# Релей Telegram через Pipedream (если api.telegram.org блокируется)

Некоторые сети (и песочница агента) не пропускают `api.telegram.org`:
TCP-соединение к `149.154.166.110:443` уходит в таймаут. Pipedream при этом
доступен, а его workflow может сходить в Telegram из облака. Схема:

```
контент-завод → https://<workflow>.m.pipedream.net/bot<TOKEN>/sendMessage
             → Pipedream (Node.js) → https://api.telegram.org/bot<TOKEN>/<method>
             → ответ Bot API JSON возвращается заводу
```

В коде завода это уже поддержано: переменная `TELEGRAM_API_BASE` заменяет
`https://api.telegram.org` (публикатор и `scripts/telegram_check.py`).

## Готовый релей этого проекта (Cloudflare Worker)

В аккаунте Cloudflare уже развёрнут Worker `telegram-proxy` — он проксирует
запросы на `api.telegram.org`, сохраняя путь и метод:

```
https://telegram-proxy.valdislav-n.workers.dev
```

В `.env`:

```bash
TELEGRAM_API_BASE=https://telegram-proxy.valdislav-n.workers.dev
```

Проверка: `./.venv/bin/python scripts/telegram_check.py` → «Бот: @Novyi0007Bot»
и статусы каналов. Важно: Cloudflare режет User-Agent `Python-urllib`
(ошибка 1010), поэтому скрипт отправляет браузерный UA — не убирайте его.
Проверить релей вручную:

```bash
curl -A "Mozilla/5.0" "https://telegram-proxy.valdislav-n.workers.dev/bot<TOKEN>/getMe"
```

Ниже — вариант с Pipedream, если Cloudflare-релея нет.

## 1. Workflow в Pipedream

1. <https://pipedream.com> → **New Workflow** → имя, например `telegram-relay`.
2. Триггер: **HTTP / Webhook** → создайте его и скопируйте URL вида
   `https://eoxxxxx.m.pipedream.net`.
3. В настройках HTTP-триггера включите **«Return a custom response from your
   workflow»** (если есть такой переключатель) — без этого ответ не дойдёт до
   завода.
4. Добавьте шаг **Run Node.js code** и вставьте код ниже, затем **Deploy**.

```js
export default defineComponent({
  async run({ steps, $ }) {
    const event = steps.trigger.event;
    const path = event.path || (event.url ? new URL(event.url).pathname : "");
    const match = String(path).match(/\/bot([^/]+)\/([^/?#]+)/);
    if (!match) {
      await $.respond({ status: 400, body: { ok: false, description: "bad relay path" } });
      return;
    }
    const [, token, method] = match;

    // Pipedream может отдать тело как строку (x-www-form-urlencoded) или объект.
    const rawBody = event.body ?? "";
    let formBody;
    if (typeof rawBody === "string") {
      formBody = rawBody;
    } else if (rawBody && typeof rawBody === "object") {
      formBody = new URLSearchParams(
        Object.entries(rawBody).map(([k, v]) => [k, typeof v === "string" ? v : JSON.stringify(v)])
      ).toString();
    } else {
      formBody = "";
    }

    const response = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: formBody,
    });
    const data = await response.json();
    await $.respond({
      status: response.status,
      headers: { "Content-Type": "application/json" },
      body: data,
    });
    return data;
  },
});
```

Проверка: откройте URL триггера в браузере — должен прийти JSON
`{"ok":false,"description":"Not Found"}` или похожий (это нормально: без
`/bot.../method` релей отвечает 400).

## 2. Подключить к заводу

В `.env`:

```bash
TELEGRAM_API_BASE=https://eoxxxxx.m.pipedream.net
```

Проверка бота и прав в каналах (запускать можно и с этой машины — Pipedream
доступен):

```bash
./.venv/bin/python scripts/telegram_check.py
```

Ожидаемый вывод: `Бот: @Novyi0007Bot`, реальные названия каналов, статус
`administrator` и `can_post=True`.

## 3. Публикация

Когда dry-run проверен и `telegram_check.py` зелёный:

```bash
# в .env: CONTENT_FACTORY_DRY_RUN=false (или app.dry_run: false в settings.yaml)
./.venv/bin/python -m content_factory run --channel tech-news --publish --max-posts 1
```

Дальше — демон/launchd или GitHub Actions, как описано в
[cloud-actions.md](cloud-actions.md).

## Ограничения и безопасность

- URL триггера — фактически ключ к вашему боту: держите его в секрете.
- Токен бота передаётся внутри пути `/bot<TOKEN>/method`; Pipedream видит его,
  но это ваш собственный аккаунт. Если не хотите передавать токен в пути —
  задайте в Pipedream переменную окружения `TELEGRAM_BOT_TOKEN` и в коде
  используйте её вместо `match[1]`.
- Бесплатный тариф Pipedream ограничивает число запусков в сутки; при
  публикации 96 постов/сутки проверьте лимиты. Если не хватает — оставьте
  релей только для проверки, а публикацию перенесите в GitHub Actions.
