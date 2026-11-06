# Hugging Face: готовые проекты, модели и данные для контент-фабрики

**Дата live-проверки: 6 ноября 2026.** Всё, что ниже, проверено запросами к HF API,
каталогу `router.huggingface.co`, документации и живым вызовам — с пометками, где
проверки не было. Исходные исследования (три отчёта, ~1000 строк с ссылками и командами):

- [.research/hf/01-spaces-inference.md](../../.research/hf/01-spaces-inference.md) — HF Inference Providers, бесплатные Spaces, ZeroGPU, РФ-доступность;
- [.research/hf/02-models-local.md](../../.research/hf/02-models-local.md) — локальные RU-модели (Ollama/llama.cpp), суммаризаторы, эмбеддинги;
- [.research/hf/03-datasets-projects.md](../../.research/hf/03-datasets-projects.md) — готовые проекты, Spaces, датасеты, библиотеки.

Документ отвечает на вопрос «что с Hugging Face реально взять и как это встроить в
`content-factory`», с учётом требований проекта: **бесплатно, работает из России, без Docker**.

---

## TL;DR — главное

1. **Бесплатного «серверного» LLM-API у Hugging Face больше нет.** У free-аккаунта
   **0 включённых кредитов** Inference Providers (только покупка), PRO — $9/мес и всего
   $2 кредитов. Router без токена отвечает 401. **HF — платный fallback, а не замена
   Groq/OpenRouter.** Это надо зафиксировать в конфиге и документации проекта
   (сейчас в `scripts/set_extra_keys.py` он подписан как «free-кредиты» — это устарело).
2. **Главная польза HF для проекта — локальные модели: бесплатно, офлайн, работает из РФ
   после скачивания.** Топ: `Qwen/Qwen3.5-9B` (Apache-2.0, 16 ГБ RAM),
   `t-tech/T-lite-it-2.1` (русский стиль, 8 ГБ), `ai-sage/GigaChat3.1-10B-A1.8B`
   (MIT, MoE — быстрый на CPU); для 8 ГБ — `Qwen/Qwen3.5-4B`, для 24 ГБ GPU —
   `Qwen/Qwen3.8-27B`. Все — актуальное поколение 2026, без gating.
3. **Готовых живых HF Spaces «новости → Telegram-пост» нет.** Проверено >10 спейсов:
   `RUNTIME_ERROR`/`PAUSED`/`BUILD_ERROR`. Рабочее лежит в **GitHub-репозиториях (MIT)** и
   библиотеках: ближайший аналог пайплайна — `alxyrgin/news-digest`, продовый дедуп —
   `frankzch/ai-news-brief`, локальный семантический дедуп — `semhash`/`model2vec`.
4. **Единственный бесплатный программный путь на HF — публичные демо-Spaces** (Gradio API):
   официальное демо `gemma-3-12b-it` реально ответило по-русски, но квота ZeroGPU —
   **2–5 минут GPU/сутки → 1–2 запроса в день**. Это только аварийный fallback перед
   `extractive`, не инфраструктура для 144 постов/сутки.
5. **Датасеты HF дают бесплатный способ проверять качество и учить стиль:** главный
   benchmark — `RussianNLP/Mixed-Summarization-Dataset` (apache-2.0, 197 819 строк +
   golden-test), 97 151 пост из 30 RU Telegram-каналов — для few-shot/стиля, свежие
   снимки 5 177 / 10 000 каналов 2026 г. (cc-by-4.0) — для аналитики и выбора ниш.

---

## 1. Что изменилось на HF в 2026 (и почему это важно для нас)

Проверки 2026-11-06:

| Проверка | Результат |
|---|---|
| `GET https://router.huggingface.co/v1/models` без токена | 200, **125 моделей**, у каждой `providers[]` с ценами |
| Бесплатные модели/провайдеры в каталоге | **нет ни одной** (`is_free: false` у всех) |
| `POST /v1/chat/completions` без токена | **401** (HTML-страница входа, не JSON) |
| Документация [pricing](https://huggingface.co/docs/inference-providers/pricing) | Free Users — **Monthly Credits: None**; PRO — **$2.00/мес**; Team/Enterprise — $2.00/seat; сверх — pay-as-you-go |
| [first-api-call](https://huggingface.co/docs/inference-providers/guides/first-api-call) | нужен HF-аккаунт + User Access Token (`HF_TOKEN`) и «remaining credits» |

**Вывод:** бесплатный тариф Inference Providers закончился (в 2025–начале 2026 ещё был
небольшой месячный лимит). Теперь HF — обычный платный провайдер; оплата кредитов — картой,
что для РФ само по себе ограничение.

**Что это значит для content-factory:** провайдер `huggingface` в
[config/settings.yaml](../config/settings.yaml#L91) уже реализован (OpenAI-совместимый,
`router.huggingface.co/v1`, по умолчанию `meta-llama/Llama-3.3-70B-Instruct`). Его нужно:

- оставить в `llm.fallback`, но **после** бесплатных (groq → openrouter → sambanova → gigachat);
- обновить модель на более русскую;
- исправить комментарии/подписи, где он назван «бесплатным»;
- считать его платным резервом, а не основой.

### 1.1. Модели router, пригодные для русского (цены — $ за 1M токенов input/output)

| Model ID | Провайдер(ы) | Цена in/out | Контекст | Комментарий |
|---|---|---|---|---|
| **`Qwen/Qwen2.5-72B-Instruct`** | deepinfra, featherless-ai | **0.36 / 0.40** | 32K | Лучший баланс «качество RU / цена» среди проверенных |
| `Qwen/Qwen3-32B` | deepinfra, featherless-ai | **0.08 / 0.28** | 40K | Самый дешёвый Qwen для постов |
| `Qwen/Qwen3-30B-A3B` | deepinfra | 0.12 / 0.50 | 40K | MoE, быстрый |
| `openai/gpt-oss-120b` | novita, groq, baseten, ovhcloud, cerebras | **0.05 / 0.25** (novita) | 131K | Дешёвый «черновик» для summary |
| `openai/gpt-oss-20b` | groq, ovhcloud, deepinfra | **0.03 / 0.14** (deepinfra) | 131K | Самая дешёвая модель каталога |
| `deepseek-ai/DeepSeek-V3.2` | deepinfra | 0.26 / 0.38 | 163K | Хороший русский |
| `meta-llama/Llama-3.3-70B-Instruct` | novita, featherless-ai, ovhcloud | 0.135 / 0.40 | 12K–131K | **Сейчас в settings.yaml**; для русского слабее и дороже Qwen |
| `zai-org/GLM-4.5-Air` | novita, zai-org | 0.13 / 0.85 | 131K | Хороший, дорогой output |

Модели поколения 2026 в каталоге тоже есть (`Qwen/Qwen3.8-27B`, `Qwen/Qwen3.5-9B`,
`google/gemma-4-31B-it`, `deepseek-ai/DeepSeek-V4.1-Flash`, `zai-org/GLM-5.3-Flash`), но их
русское качество **вызовом не проверено** (нет кредитов) — не ставить единственной моделью без теста.

Деньги: 300 запросов/сутки × ~1.5–2k токенов ≈ 0.3–0.6M токенов/сутки. На `gpt-oss-20b`
это ~$0.01–0.03/сутки, на `Qwen/Qwen3-32B` — ~$0.02–0.08/сутки, т.е. **$2 PRO-кредитов
хватает на месяц**, но это подписка $9/мес. Реалистичный бесплатный вариант для РФ —
локальная модель (раздел 3), а HF — только если есть карта/PRO.

---

## 2. Готовые HF-проекты: что реально существует и что брать

### 2.1. End-to-end пайплайны «новости → дайджест/пост»

Живых HF Spaces такого класса **нет** (проверены >10: `RUNTIME_ERROR`/`PAUSED`/`BUILD_ERROR`;
списки — в [03-datasets-projects.md](../../.research/hf/03-datasets-projects.md)). Рабочие
проекты — в GitHub, лицензий MIT достаточно для заимствования:

| Проект | Лицензия | Что внутри | Как использовать в content-factory |
|---|---|---|---|
| [**alxyrgin/news-digest**](https://github.com/alxyrgin/news-digest) | **MIT** | Telethon + RSS каждые 30 мин → AI-фильтр шума → категоризация → суммаризация → ежедневный/недельный дайджест → Telegraph | **Ближайший аналог всего пайплайна.** Взять структуру, промпты фильтра/категоризации/дайджеста; GPT-4o заменить локальной моделью |
| [**frankzch/ai-news-brief**](https://github.com/frankzch/ai-news-brief) | **MIT** | 370+ источников, `trafilatura` + fallback-скрапинг, LLM-скоринг, **дедуп 2 стадии: SimHash + pgvector**, PostgreSQL | Взять двухступенчатый дедуп, скоринг важности, список источников; PostgreSQL → SQLite (у нас уже SQLite) |
| [qianqiuqiu/news-aggregator](https://github.com/qianqiuqiu/news-aggregator) | MIT | Node + `node:sqlite`; LLM: дедуп → саммари → **ранжирование «по числу изданий»** | Идея: вес кластера в digest = число подтвердивших источников (у нас счётчик уже есть) |
| [ma111e/downlink](https://github.com/ma111e/downlink) | MIT | RSS → полный текст → LLM-скоринг по рубрикам → рейтинговый дайджест → публикация | Схема «рубрики → оценка → рейтинг»; идея архива дайджестов |
| [Rongronggg9/RSS-to-Telegram-Bot](https://github.com/Rongronggg9/RSS-to-Telegram-Bot) | **AGPL-3.0** | Зрелый RSS→TG бот: HTML→Telegram entities, дедуп, расписание | **Только идеи**, код не копировать (AGPL) |

### 2.2. Живые HF Spaces, которые можно использовать или позаимствовать

| Space | Лицензия | Статус 2026-11-06 | Что даёт / как применить |
|---|---|---|---|
| [minishlab/semantic-deduplication](https://huggingface.co/spaces/minishlab/semantic-deduplication) | **MIT** | **RUNNING**, gradio API 200 | Семантический дедуп на SemHash+Model2Vec. Как сервис принимает только датасеты HF Hub — **ставить `semhash` локально** (тот же алгоритм, CPU, MIT) |
| [Agents-MCP-Hackathon/web-scraper](https://huggingface.co/spaces/Agents-MCP-Hackathon/web-scraper) | нет license | RUNNING, `/scrape_content` | URL → markdown. Без лицензии — только вызов как эксперимент; в прод лучше `trafilatura` (Apache-2.0) |
| [davanstrien/topic-feed-lab](https://huggingface.co/spaces/davanstrien/topic-feed-lab) | нет license | RUNNING | Паттерн «дешёвый CPU-классификатор тем вместо LLM» + фоновый воркер + JSON API. Код не копировать (нет лицензии) |
| [JournalistsonHF/ai-toolkit](https://huggingface.co/spaces/JournalistsonHF/ai-toolkit) | нет license | RUNNING | Курируемый список инструментов для контент-редакций — полезен для ревью стека |

Мёртвые/непригодные (не тратить время): `openfree/*`, `autotrust/news`, `valurank/*`,
`spark-nlp/Russian-NER` (SLEEPING), `Qwen/Qwen3-Demo` (внутри DashScope, не API),
спейсы-прокси `Nymbo/*`, `akhaliq/*`, `openfree/*` (401/404 — чужие ключи).

### 2.3. Библиотеки, которые стоит взять напрямую (проверены на PyPI 2026-11-06)

| Пакет | Версия | Лицензия | Для чего в content-factory |
|---|---|---|---|
| [trafilatura](https://pypi.org/project/trafilatura/) | 2.3.1 | Apache-2.0 | Полный текст статьи из URL (RSS часто отдаёт только анонс) |
| [feedparser](https://pypi.org/project/feedparser/) | 6.0.14 | BSD-2 | Надёжный RSS/Atom-парсер (если своего не хватает) |
| [newspaper3k](https://pypi.org/project/newspaper3k/) | 0.2.8 | MIT | Альтернативный article-extractor (запасной) |
| [pymorphy3](https://pypi.org/project/pymorphy3/) | 2.0.6 | MIT | RU-лемматизация для дедупа/TF-IDF/ключевых слов без LLM |
| [razdel](https://pypi.org/project/razdel/) | 0.5.0 | MIT | RU-токенизация/предложения (extractive-саммари, нарезка постов) |
| [sumy](https://pypi.org/project/sumy/) | 0.13.0 | Apache-2.0 | Extractive-суммаризация (LSA/LexRank/TextRank) — усиление режима `extractive` |
| [BERTopic](https://pypi.org/project/bertopic/) | 0.17.4 | MIT | Тематическая кластеризация (тренды дня, группировка сюжетов) |
| [semhash](https://pypi.org/project/semhash/) | 0.5.0 | MIT | Семантический дедуп на CPU (minhash + эмбеддинги) |
| [model2vec](https://pypi.org/project/model2vec/) | 0.10.0 | MIT | Быстрые статические эмбеддинги для дедупа (RU-модель проверить в карточке MinishLab) |
| [sentence-transformers](https://pypi.org/project/sentence-transformers/) | 6.2.0 | Apache-2.0 | Локальные эмбеддинги для кластеризации/дедупа |
| [gradio-client](https://pypi.org/project/gradio-client/) | 2.7.2 | Apache-2.0 | Если звать бесплатные Spaces (только fallback) |

---

## 3. Локальные модели с HF — главная бесплатная ценность

Требования проекта: офлайн после скачивания, без Docker, 8–16 ГБ RAM (опционально GPU 24 ГБ).
Поколения 2024–2025 (Qwen2.5, Qwen3, Gemma 3, Llama 3.x) живы, но в 2026 актуальнее Qwen 3.5/3.6/3.8,
Gemma 4, GigaChat 3.1 — при том же размере заметно лучше. Все топ-варианты — **Apache-2.0/MIT
и без gating** (в отличие от Gemma 3 и Llama, которые требуют HF-аккаунт и принятие условий).

### 3.1. Топ-3 (проверено через HF API)

| # | Модель | GGUF/размер | Лицензия | Почему |
|---|---|---|---|---|
| 1 | [**Qwen/Qwen3.5-9B**](https://huggingface.co/Qwen/Qwen3.5-9B) | [unsloth/Qwen3.5-9B-GGUF](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF), Q4_K_M **5,7 ГБ**; Ollama `qwen3.5:9b` ≈ 7,6 ГБ | apache-2.0 | Универсал: посты, пересказ, анализ; 201 язык, ctx 262K; дефолт на 16 ГБ RAM |
| 2 | [**t-tech/T-lite-it-2.1**](https://huggingface.co/t-tech/T-lite-it-2.1) | [GGUF](https://huggingface.co/t-tech/T-lite-it-2.1-GGUF), Q4_K_M **5,03 ГБ** | apache-2.0 | Русскоязычная 8B (база Qwen3-8B), бенчмарки Ru Arena Hard/ruIFeval в карточке; стиль «как автор». В библиотеке Ollama нет → `ollama pull hf.co/t-tech/T-lite-it-2.1-GGUF:Q4_K_M` |
| 3 | [**ai-sage/GigaChat3.1-10B-A1.8B**](https://huggingface.co/ai-sage/GigaChat3.1-10B-A1.8B) | [GGUF](https://huggingface.co/ai-sage/GigaChat3.1-10B-A1.8B-GGUF), q4_K_M **6,48 ГБ** | **MIT** | Открытые веса Сбера (2026), MoE 10B/1,8B active → скорость как у 2B на CPU; ctx 262K; `ollama pull hf.co/ai-sage/GigaChat3.1-10B-A1.8B-GGUF:q4_K_M` |

Сверху: для 24 ГБ GPU — [Qwen/Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B)
([UD-Q4_K_M 16,5 ГБ](https://huggingface.co/unsloth/Qwen3.8-27B-GGUF), Apache-2.0) или
[google/gemma-4-12B-it](https://huggingface.co/google/gemma-4-12B-it) Q8 (12,7 ГБ, Apache-2.0).

### 3.2. Что подобрать под железо

| Железо | Модель по умолчанию | Альтернативы | Ожидание |
|---|---|---|---|
| **8 ГБ RAM, CPU** | `qwen3.5:4b` (~4,0 ГБ) | `qwen3.5:2b` (3,1), `qwen3:4b` (2,5) | посты 1–2 мин; 7B+ не советую |
| **16 ГБ RAM, CPU** | `qwen3.5:9b` (~7,6 ГБ) | `T-lite-it-2.1` (5,0), `GigaChat3.1` (6,5), `gemma4:12b` (7,7) | 30–120 с/пост; GigaChat3.1 — самый быстрый из-за MoE |
| **24 ГБ GPU** | `qwen3.8:27b` (~18 ГБ) | `Qwen3.6-27B` UD-Q4 (16,8), `Gemma-4-12B` Q8 (12,7) | секунды–десятки секунд; 27B Q4 + ctx 8–16K может не влезть → UD-IQ4_XS (14,3 ГБ) |
| Слабое железо / без зависимостей | **`extractive`** (текущий дефолт) | — | 0 ₽, всегда работает |

Под задачу: **digest/пересказ** — Qwen3.5-9B или GigaChat3.1; **story/аналитика (авторский
стиль)** — T-lite-it-2.1 или Vikhr-Nemo-12B; **en-каналы** (`config/channels.en.yaml`) —
Qwen3.5-9B / Gemma-4-12B.

### 3.3. Настройки `config/settings.yaml`

Статус на 06.11.2026: локальная модель уже подключена — в `settings.yaml` стоит
`llm.provider: ollama`, `model: qwen3.5:9b`, `num_ctx: 8192`, `timeout: 300`;
бинарник и модели Ollama лежат в `data/ollama/`, управление —
`bash scripts/start-ollama.sh {start|status|pull}`. Ниже — те же настройки и
объяснение, чтобы можно было повторить на другой машине:

```yaml
llm:
  provider: ollama
  timeout: 300          # CPU/GPU-генерация 9B: 30–180 с/пост
  max_tokens: 500       # 700 на CPU = слишком долго
  temperature: 0.3
  ollama:
    base_url: http://127.0.0.1:11434
    model: qwen3.5:9b   # альтернативы: hf.co/t-tech/T-lite-it-2.1-GGUF:Q4_K_M,
                        #              hf.co/ai-sage/GigaChat3.1-10B-A1.8B-GGUF:q4_K_M
    num_ctx: 8192       # иначе Ollama может резать контекст до 4K
    think: false        # reasoning-модели «думают» — для постов это лишние минуты
```

⚠️ **Три подводных камня, важных именно для нашего кода** (`content_factory/nlp/llm.py`):

1. `OllamaLLM` раньше не передавал `num_ctx` → Ollama применяла дефолтный контекст
   (может быть 4K), а в промпт попадает до 15k символов статьи. **Исправлено 06.11.2026:**
   `num_ctx` читается из конфига и уходит в `options.num_ctx`; параллельно можно
   задать `OLLAMA_CONTEXT_LENGTH=8192` (переменная Ollama) или Modelfile
   с `PARAMETER num_ctx 8192`.
2. `llm.timeout: 120` для CPU-модели 9B мал — **поднято до 300–420 с**, `max_tokens` снижен
   до 350–500 (на CPU 700 токенов = слишком долго).
3. **Reasoning-модели (qwen3.5) по умолчанию «думают».** Первый `llm-test` с `max_tokens: 500`
   упёрся в 5-минутный таймаут, потому что модель генерировала цепочку рассуждений
   (1276 токенов). **Исправлено:** `OllamaLLM` передаёт `think: false` из конфига — ответ
   за 5,7 с вместо 5 минут, и качество постов не страдает.

Проверка провайдера после настройки: `./.venv/bin/python -m content_factory llm-test`
(команда `llm-test` уже есть в `content_factory/cli.py`).

### 3.4. Суммаризаторы, эмбеддинги, тональность

| Модель | Размер | Лицензия | Применение |
|---|---|---|---|
| [RussianNLP/FRED-T5-Summarizer](https://huggingface.co/RussianNLP/FRED-T5-Summarizer) | 1,74B (~7 ГБ fp32) | MIT | RU-суммаризатор Сбера (не путать с нерабочим `SberDevices/...`); лучший «абстрактивный» пересказ, лучше на GPU |
| [cointegrated/rut5-base-absum](https://huggingface.co/cointegrated/rut5-base-absum) | 244M (~0,9 ГБ) | MIT | лёгкий CPU-суммаризатор |
| [IlyaGusev/rut5_base_sum_gazeta](https://huggingface.co/IlyaGusev/rut5_base_sum_gazeta) | 222M (~0,9 ГБ) | Apache-2.0 | новостная суммаризация (Gazeta) |
| [cointegrated/rubert-tiny2](https://huggingface.co/cointegrated/rubert-tiny2) | 29M (~120 МБ) | MIT | быстрые RU-эмбеддинги для дедупа/кластеров на CPU |
| [ai-forever/ru-en-RoSBERTa](https://huggingface.co/ai-forever/ru-en-RoSBERTa) | 404M (~0,8 ГБ) | MIT | RU+EN эмбеддинги (у нас есть и en-каналы) |
| [intfloat/multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small) | 118M (~0,5 ГБ) | MIT | эмбеддинги с **ONNX** — без torch |
| [ai-forever/FRIDA](https://huggingface.co/ai-forever/FRIDA) | 1,7B (3,3 ГБ) | MIT | лучший RU semantic-search класс; только если RAM ≥ 16 ГБ |
| [seara/rubert-tiny2-russian-sentiment](https://huggingface.co/seara/rubert-tiny2-russian-sentiment) | 29M | MIT | тональность RU (5 классов) для фильтра негатива |

Для seq2seq-суммаризации нужны `torch`+`transformers` (~2–3 ГБ) и отдельный код; на практике
фабрике проще просить пересказ у того же локального LLM через промпт, а seq2seq держать
опциональным «лёгким» путём.

### 3.5. Какие ID из старых примеров больше не работают

| Было в примерах | Статус | Актуальный ID |
|---|---|---|
| `SberDevices/FRED-T5-Summarizer` | 401→404 | `RussianNLP/FRED-T5-Summarizer` |
| `t-tech/T-lite-instruct` | 401→404 | `t-tech/T-lite-it-2.1` |
| `VikhrModels/Vikhr-Nemo-12B-Instruct` | 401→404 | `Vikhrmodels/Vikhr-Nemo-12B-Instruct-R-21-09-24` |
| `google/gemma-3-*` | gated (manual), лицензия gemma | `google/gemma-4-*` (Apache-2.0, без gating) |
| `meta-llama/Llama-3.1/3.3` | gated, русского нет в списке языков | не рекомендуется для RU-постов |

**Не брать:** `d0rj/rut5-base-summ` и `ai-forever/ruT5-*` (лицензия не указана),
`ai-forever/ruGPT-3.5-13B` (не инструкт), `DeepSeek-R1-Distill-*` как основную
(reasoning-модель — длинные «рассуждения», медленно, водянистый пост), `IlyaGusev/saiga_mistral_7b`
(это LoRA-адаптер, не полная модель).

---

## 4. Датасеты HF: чем реально помогают

### 4.1. Русскоязычные новости — для eval суммаризации/фильтра

| Датасет | Лицензия | Объём | Как использовать |
|---|---|---|---|
| [**RussianNLP/Mixed-Summarization-Dataset**](https://huggingface.co/datasets/RussianNLP/Mixed-Summarization-Dataset) | **apache-2.0** | **197 819** строк (train 197 561 + golden-test 258) | **Главный benchmark** качества суммаризации: сравнение extractive / локальной LLM / смены промпта |
| [IlyaGusev/gazeta](https://huggingface.co/datasets/IlyaGusev/gazeta) | unknown | 74 126 | Классика RU-суммаризации (новости Gazeta.ru). Только внутренний eval, не распространять |
| [data-silence/lenta.ru_2-extended](https://huggingface.co/datasets/data-silence/lenta.ru_2-extended) | не указана | 577 134 | Самый свежий RU-корпус: новости 2019-12…2024-06 — тесты фильтра по свежести/трендов |
| [data-silence/rus_news_classifier](https://huggingface.co/datasets/data-silence/rus_news_classifier) | не указана | 10K–100K | Оценка фильтра по темам; обучение лёгкого CPU-классификатора тем |
| [ai-forever/ria-news-retrieval](https://huggingface.co/datasets/ai-forever/ria-news-retrieval) | не указана | 724 344 | Оценка retrieval/кластеризации «одна история из разных источников» |
| [reciTAL/mlsum](https://huggingface.co/datasets/reciTAL/mlsum) | other (research) | 1,5M+ (есть ru) | Оценка суммаризации на RU-новостях; условия читать на карточке |
| [data-silence/xlsum-russian-bbc](https://huggingface.co/datasets/data-silence/xlsum-russian-bbc), [sumnews](https://huggingface.co/datasets/data-silence/sumnews) | **cc-by-nc-sa-4.0** | 77 784 / 100K–1M | Только некоммерческий research/eval |

### 4.2. Telegram-посты и каналы — для стиля, few-shot и аналитики

| Датасет | Лицензия | Объём | Применение |
|---|---|---|---|
| [ScoutieAutoML/russian-news-telegram-dataset](https://huggingface.co/datasets/ScoutieAutoML/russian-news-telegram-dataset) | не указана | **97 151** пост, 30 RU каналов | Few-shot стиля постов, оценка фильтра каналов; внутренние тесты |
| [starnikovoleg/telegram-public-channels-2026-W36](https://huggingface.co/datasets/starnikovoleg/telegram-public-channels-2026-W36) | **cc-by-4.0** | 5 177 каналов на 31.08.2026 + граф рекомендаций | Карта конкурентов/ниш, обоснование выбора каналов |
| [JohnRicoco/top-telegram-channels](https://huggingface.co/datasets/JohnRicoco/top-telegram-channels) | **cc-by-4.0** | 10 000 каналов, октябрь 2026 | Бенчмарк метрик (подписчики/просмотры/ER по темам) для аналитики |

Не подходит: `KvaytG/russian-telegram-chat-logs` (логи чатов, не посты),
`aisbergpublicorganization/telegram-news-ua-dataset` (украинские каналы),
`yenisei23/russian-military-telegram-2year` (военная тематика — юридические/модерационные риски).

⚠️ Правило: **нет лицензии ≠ можно использовать**. Датасеты без лицензии и NC-датасеты —
только внутренний eval, без перепубликации данных и без коммерческого контента.

---

## 5. Бесплатный LLM через HF: только демо-Spaces (и это честно последний резерв)

Единственный живой бесплатный спейс с публичным Gradio API и проверенным ответом по-русски:

- [**huggingface-projects/gemma-3-12b-it**](https://huggingface.co/spaces/huggingface-projects/gemma-3-12b-it) —
  RUNNING, `zero-a10g`, endpoint `/run` (параметры `message`, `system_prompt`,
  `max_new_tokens`); живой вызов 2026-11-06 дал русский ответ за 5,9 с.
- Рядом RUNNING официальные демо Gemma 4 — `gemma-4-12b-it`, `gemma-4-26b-a4b-it`,
  `gemma-4-31b-it`, `gemma-4-e4b-it` (`/chat`), но генерация **[не проверена]** — квота кончилась.
- T-lite / Vikhr / GigaChat бесплатных спейсов **нет** (все проверенные — PAUSED/RUNTIME_ERROR/
  BUILD_ERROR/SLEEPING); спейсы-прокси с чужими ключами (`akhaliq/*`, `openfree/*`) — 401/404.

**Лимиты ZeroGPU** (docs, подтверждено ошибкой `You have exceeded your ZeroGPU quota`):
2 мин/сутки анонимно, 5 мин/сутки с бесплатным HF-токеном, 40 мин — PRO. Спейс запрашивает
~180 с GPU за вызов → анонимно хватает на **1–2 ответа в сутки**. Для 144 постов/сутки не подходит.

Если всё же нужен резерв перед `extractive` — эскиз провайдера `hf_space` (ленивый
`gradio_client` в `requirements-optional.txt`, `enabled: false`, `daily_limit: 10`) есть в
[01-spaces-inference.md](../../.research/hf/01-spaces-inference.md) §5.2. Это ~50 строк в
`content_factory/nlp/llm.py` + конфиг + тест с моком. Но по совокупности рисков (квоты, очередь,
ToS, чужие демо) это **экспериментальный** путь, а не продакшн-опция.

---

## 6. План внедрения в content-factory

> **Статус на 06.11.2026:** P0 выполнен и P1-багфикс `OllamaLLM` тоже — в проекте уже
> работает локальная модель `qwen3.5:9b` (провайдер `ollama`, `num_ctx: 8192`,
> `timeout: 300`), Ollama лежит в `data/ollama/`, управление — `scripts/start-ollama.sh`.
> HF-провайдер помечен как платный и переведён на `Qwen/Qwen2.5-72B-Instruct`, в
> `docs/free-cloud.md` и `docs/llm.md` статус HF исправлен.
> Дополнительно внедрена **экономия токенов** (кэш ответов, объединённый анализ, компактный
> заголовок, учёт токенов): −42% токенов на пост без потери качества — см.
> [llm.md §7](llm.md#7-экономия-токенов-с-2026-11) и `scripts/token_economy_check.py`.
> Остались P1-скрипт eval на HF-датасете и P2.

### P0 — дёшево и сразу (без новых зависимостей)

1. **Исправить статус HF в проекте** (он больше не «бесплатные кредиты»):
   - `scripts/set_extra_keys.py` — подпись `HUGGINGFACE_API_KEY` → «HuggingFace Inference
     (LLM, платно: у free 0 кредитов, PRO $2/мес)» — **сделано**;
   - `config/settings.yaml` — комментарий к провайдеру `huggingface` и модель:
     `model: Qwen/Qwen2.5-72B-Instruct` (лучший русский среди дешёвых; альтернативы
     `Qwen/Qwen3-32B`, `openai/gpt-oss-20b` — см. §1.1) — **сделано**;
   - поставить `huggingface` в `fallback` **после** бесплатных — **сделано**.
2. **Локальная модель по умолчанию**: `qwen3.5:9b` (16 ГБ) или `qwen3.5:4b` (8 ГБ),
   `llm.timeout: 300`, `max_tokens: 500`; `num_ctx: 8192`; инструкции —
   `docs/setup.md` §2.1 и `docs/llm.md` §1.2 — **сделано**.
3. **Документация**: `docs/llm.md`, `docs/free-cloud.md` обновлены, HF больше нигде не
   назван бесплатным — **сделано**.

### P1 — полдня–день (код и тесты)

4. **Багфикс `OllamaLLM`**: передавать `num_ctx` (из конфига/`OLLAMA_CONTEXT_LENGTH`) и
   поднять дефолтный таймаут; тест на payload. Это чинит потерю контекста на длинных статьях.
5. **Опциональный провайдер `hf_space`** (§5): `enabled: false` по умолчанию, `daily_limit: 10`,
   ленивый импорт `gradio_client`, обёртка таймаута, тест с моком; строка в `requirements-optional.txt`.
6. **Скрипт eval суммаризации** `scripts/eval_summary.py`: 30–50 примеров из
   `RussianNLP/Mixed-Summarization-Dataset` golden-test → прогон `extractive` vs локальная LLM,
   метрики (ROUGE-1/2/L через `rouge`/`rouge-score`, длина, время, доля fallback). Даёт
   объективный ответ «стоит ли менять extractive на LLM» на реальных новостях.

### P2 — 1–2 дня (усиление качества)

7. **Семантический дедуп**: опциональный модуль `semhash` (MIT) как вторая ступень после
   текущего URL/заголовочного дедупа — идея из `frankzch/ai-news-brief` (SimHash → семантика).
8. **Эмбеддинги для кластеров/трендов**: `multilingual-e5-small` ONNX (118 МБ, без torch) или
   `rubert-tiny2`; сравнить с текущим TF-IDF-подходом на датасете `ria-news-retrieval`.
9. **Аналитика каналов**: разовый скрипт-снимок `top-telegram-channels` (cc-by-4.0) для
   сравнения ER/ниш и обоснования 6 каналов; `rus_news_classifier` — для обучения лёгкого
   CPU-классификатора тем (вместо/рядом с keyword-фильтром).
10. **RU-тональность** `seara/rubert-tiny2-russian-sentiment` (MIT) — фильтр негатива и
    «разные ракурсы» в анализе (опционально, если появится потребность).

**Что не делать:** не строить продакшн на чужих Spaces; не тянуть gated Gemma 3/Llama;
не использовать NC/безлицензионные датасеты для контента; не считать HF бесплатным.

---

## 7. Риски и ограничения

1. **Биллинг HF:** free-аккаунт = 0 кредитов (401 на chat без токена); PRO = $9/мес и $2
   кредитов; оплата из РФ картой — отдельная проблема. HF-роутер — только платный резерв.
2. **ZeroGPU-квоты крошечные:** 2/5/40 минут в сутки; спейс «съедает» ~180 с за вызов;
   после исчерпания — ошибка до следующих суток. Не для 144 постов/сутки.
3. **Чужие демо-спейсы — не инфраструктура:** PAUSED/SLEEPING, смена кода/модели, логин,
   «uncensored»-модели, нет SLA; массовая автоматизация может быть заблокирована.
4. **Лицензии:** Apache-2.0/MIT — безопасно; Gemma — Gemma Terms; `license: unknown`/NC
   датасеты — только внутренние тесты; gated-репозитории требуют аккаунт и принятие условий
   (401 у `/api/models/{id}` ≠ «модели нет»).
5. **Русский язык и галлюцинации:** 4–9B модели могут путать факты; для digest —
   `temperature` 0.2–0.3, проверка цифр/имён по статье, `banned_words` и `extractive`-fallback
   уже есть в проекте.
6. **Скорость/таймауты:** CPU-инференс 9B ~4–8 ток/с ⇒ 700 токенов = 90–175 с при текущем
   `llm.timeout: 120` — часть постов уйдёт в fallback; поднять таймаут.
7. **Контекст Ollama:** без `num_ctx` часть статьи (до 15k символов) теряется — см. §3.3.
8. **Доступность из РФ:** на 2026-11-06 `huggingface.co`, `router.huggingface.co/v1/models`
   и `*.hf.space` отвечали 200 с московских нод check-host (домашние ISP не проверялись);
   для скачивания моделей при проблемах — `HF_ENDPOINT`-зеркало (`hf-mirror.com`), VPN или
   заранее скачанные GGUF. После скачивания всё работает офлайн.
9. **Актуальность:** HF меняется быстро; все ID/цены — на 2026-11-06. Перед внедрением
   перепроверяйте `/api/models/{id}` и каталог router.

---

## 8. Как перепроверить самому (команды 2026-11-06)

```bash
# 1) Каталог HF-роутера и наличие модели (без токена)
curl -s https://router.huggingface.co/v1/models | jq -r '.data[].id' | grep -i qwen | head
curl -s https://huggingface.co/api/models/Qwen/Qwen3.5-9B \
  | jq '{id,downloads,likes,gated,license:.cardData.license}'

# 2) GGUF-файлы и размеры
curl -s https://huggingface.co/api/models/unsloth/Qwen3.5-9B-GGUF/tree/main \
  | jq -r '.[] | select(.path|endswith(".gguf")) | "\(.path) \(.size/1000000|floor) MB"'

# 3) Статус и Gradio API бесплатного спейса
curl -s https://huggingface.co/api/spaces/huggingface-projects/gemma-3-12b-it \
  | jq '{runtime:.runtime.stage, subdomain}'
curl -s -o /dev/null -w '%{http_code}\n' \
  https://huggingface-projects-gemma-3-12b-it.hf.space/gradio_api/info

# 4) Датасет: лицензия/объём/свежесть
curl -s "https://huggingface.co/api/datasets/RussianNLP/Mixed-Summarization-Dataset?full=true" \
  | jq '{downloads,likes,lastModified,license:.cardData.license}'

# 5) Локальная проверка конфига проекта
./.venv/bin/python -m content_factory llm-test
```

Ключевые внешние ссылки: [hf.co/pricing](https://huggingface.co/pricing) ·
[Inference Providers pricing](https://huggingface.co/docs/inference-providers/pricing) ·
[ZeroGPU docs](https://huggingface.co/docs/hub/spaces-zerogpu) ·
[Ollama library](https://ollama.com/library) ·
[MERA — бенчмарк русского](https://mera.a-ai.ru/) · [LLM Arena RU](https://llmarena.ru/) ·
[check-host](https://check-host.net) (проверка доступности из РФ).

---

## 9. Итог одной фразой

HF в 2026 — это **не бесплатный LLM-API**, а **склад бесплатных весов, данных и кода**:
локальные модели (`Qwen3.5-9B` / `T-lite-it-2.1` / `GigaChat3.1-10B-A1.8B`) закрывают
генерацию бесплатно и офлайн, датасеты дают benchmark и стиль, GitHub MIT-проекты —
готовую архитектуру пайплайна; бесплатные Spaces — только аварийный резерв на 1–2 запроса
в сутки, а router — платный fallback.

---

*Отчёт подготовлен по трём live-исследованиям 2026-11-06; сырые данные, команды проверки и
пометки «не проверено» — в `.research/hf/01-spaces-inference.md`, `02-models-local.md`,
`03-datasets-projects.md`.*
