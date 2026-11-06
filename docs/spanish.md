# Испанский режим (canales en español)

Завод умеет публиковать посты **на испанском** (нейтральный es-419 — ЛатАм и
Испания). Язык, как и для английского, задаётся **у канала**
(`language: es` в YAML), поэтому один запуск может обслуживать ru/en/es
каналы, а испанские каналы живут в отдельном файле `config/channels.es.yaml`.

## 1. Что уже настроено

`config/channels.es.yaml` — 3 канала, 6 постов в сутки каждый, время местное
UTC−5 (Богота/Лима/Кито; в Мексике посты выйдут на час раньше, в Аргентине —
на два позже):

| id | Название | Тема | Источники |
|---|---|---|---|
| `tech-ai-es` | Tecnología e IA | технологии, ИИ, продукты, компании | Hipertextual, FayerWayer, ABC Tecnología, La Nación/Tecnología, El Financiero |
| `crypto-es` | Cripto y Blockchain | Bitcoin, Ethereum, регулирование, рынки | CriptoNoticias, BeInCrypto Español, CriptoTendencia, Observatorio Blockchain |
| `futbol-es` | Fútbol en Español | LaLiga, Liga MX, Аргентина, MLS, Champions | ESPN JSON API (lang=es, 5 лиг), Relevo, 90min, La Nación/Deportes, El Universal/Deportes, Récord |

Источники проверены 06.11.2026. Отдельно отмечу:

- **ESPN для футбола** — не RSS (он закрыт антиботом, HTTP 202), а JSON API
  `site.api.espn.com/.../soccer/{league}/news?lang=es`; адаптер `type: espn`
  с `options.lang: es` отдаёт испанские заголовки и описания.
- **La Nación / El Universal** — не тематические ленты, а разделы «Deportes»
  общего RSS; они идут **без** `trust: true`, поэтому контент дополнительно
  фильтруется по темам канала.
- **Récord** (Мексика) отдаёт только короткое описание, поэтому у него
  включён `full_text: true` — текст догружается со страницы статьи.

## 2. Запуск

Проверить конфиг и источники:

```bash
CONTENT_FACTORY_CHANNELS=config/channels.es.yaml ./.venv/bin/python -m content_factory channels
CONTENT_FACTORY_CHANNELS=config/channels.es.yaml ./.venv/bin/python -m content_factory sources check --channel tech-ai-es
```

Безопасный прогон (посты в `data/outbox/`, без публикации):

```bash
CONTENT_FACTORY_CHANNELS=config/channels.es.yaml ./.venv/bin/python -m content_factory run --channel tech-ai-es,crypto-es,futbol-es --dry-run
```

Публикация — после того как в `.env` появятся `TELEGRAM_BOT_TOKEN` и chat_id
каналов (`TELEGRAM_CHAT_ID_TECH_AI_ES`, `TELEGRAM_CHAT_ID_CRYPTO_ES`,
`TELEGRAM_CHAT_ID_FUTBOL_ES`), а `dry_run` выключен.

Демон испанских каналов удобно запускать отдельным процессом/сервисом с
переменной `CONTENT_FACTORY_CHANNELS=config/channels.es.yaml` — тогда русские
и английские каналы продолжают работать своим демоном, а испанские своим
(состояние слотов и SQLite общие, id каналов не пересекаются).

## 3. Что переведено в генерации

- промпты анализа и генерации (LLM) — испанские;
- шаблонный fallback (без LLM) — испанские подписи: «Claves», «Por qué
  importa», «Contexto», «Qué dicen las fuentes», «Cifras», «Conclusión»,
  «Fuentes»;
- проверка языка: в es-постах отбрасываются кириллические фрагменты и
  заголовки без латиницы;
- даты — «6 nov 2026», хэштеги с диакритикой (á, é, í, ó, ú, ñ) не теряются;
- ключевые слова и тональность — испанские стоп-слова и лексикон.

Не переводится: логи, отчёты, документация (служебные, остаются русскими).

## 4. Ограничения

- Нейтральный испанский один на все страны: без местной лексики
  (`celular` vs `móvil`, `computadora` vs `ordenador`). Для отдельного
  ES-ES канала (Испания) лучше завести копию канала с правкой лексики.
- Морфология испанского не поддерживается (как и английского) — только
  стоп-слова; для качества лучше держать LLM (Ollama/Groq/Gemini), иначе
  extractive-режим даёт более сухие посты.
- Права: только пересказ своими словами + ссылка на первоисточник; полный
  перевод статьи — производное произведение, нужен договор. Фото издателей
  не берём — только свои или стоковые.
