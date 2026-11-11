# AstrBot: RAG по данным проекта и Telegram Stars

## RAG (база знаний)

- Провайдер эмбеддингов: **Cloudflare Workers AI** `@cf/baai/bge-m3` (1024 dims),
  OpenAI-совместимый endpoint
  `https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/v1`.
- В `.astrbot/cmd_config.template.json` добавлены:
  - `provider` c id `cf-embed` (`type: openai_embedding`, `provider_type: embedding`);
  - `kb_names: ["content-factory"]`, `kb_fusion_top_k: 30`, `kb_final_top_k: 8`.
- `render_config_image.py` подставляет `CLOUDFLARE_ACCOUNT_ID` / `CLOUDFLARE_API_TOKEN`
  и убирает `cf-embed`, если они не заданы.
- База знаний создана через Dashboard API:
  `POST /api/v1/knowledge-bases` с `embedding_provider_id: "cf-embed"`.
  Документы загружены в неё (Markdown из `docs/`, плюс
  `.astrbot/knowledge/content-factory-overview.md` и `channels-reference.md`).
- Для RAG важна чистая формулировка запроса: `provider_settings.prompt_prefix`
  должен быть `{{prompt}}`, а языковые инструкции — в **persona** (системный промпт),
  иначе инструкция попадает в embedding-запрос и портит выдачу.
- State (`data/`) синкается в приватный HF dataset `ERPSAS/cf-astrbot-state` каждые
  5 минут, поэтому база знаний переживает рестарты.

Проверка:

```bash
curl -s -X POST "$ASTRBOT_URL/api/v1/knowledge-bases/<kb_id>/retrieve" \
  -H "Authorization: Bearer $JWT" -H 'Content-Type: application/json' \
  -d '{"query":"Перечисли все 6 каналов","kb_names":["content-factory"],"top_k":8}'
```

## Telegram Stars (донаты)

- Worker: `infra/stars-pay/index.js` (Cloudflare Worker, service-worker syntax).
- Бот: `@Cf_crosspromo_bot`; `/donate` → 50 / 100 / 250 ⭐.
- Worker сохраняет прежний webhook Railway: все не-payment updates форвардятся туда.
- Для оплаты пользователь должен сначала открыть бота и нажать **Start** — бот не
  может сам начать диалог.
- Секреты worker: `BOT_TOKEN`, `WEBHOOK_SECRET`; Telegram webhook ставится с
  `secret_token`.
