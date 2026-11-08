# Интеграции: Dify-приложения для новостей, трендов и SEO

В Dify Cloud можно собрать отдельные Workflow-приложения и использовать их из
контент-завода как сервисы:

| Назначение | Что делает | Куда подключается |
|---|---|---|
| Новостной агрегатор | ищет свежие новости по теме (Tavily, Currents API и т.п.) и отдаёт статьи | новый источник статей (RSS + Dify workflow) |
| Поиск трендов | возвращает актуальные темы/сюжеты по каналу | подсказки тем, хештегов и отбор сюжетов для постов |
| SEO-оптимизация | переписывает заголовок/текст под поисковые запросы, подбирает ключевые слова | пост-обработка готового поста перед публикацией |

## Ключи приложений

У каждого приложения Dify **свой** API-ключ: приложение → **Access Point** →
**API Keys** → **Create new API key**. Ключ чат-приложения для workflow-приложений
не подходит.

Записать ключи в `.env` (ввод скрыт, ключи проверяются через `/v1/info`):

```bash
python3 scripts/set_dify_app_keys.py
```

Скрипт спрашивает по очереди:

- `DIFY_NEWS_API_KEY` — новостной агрегатор;
- `DIFY_TRENDS_API_KEY` — поиск трендов;
- `DIFY_SEO_API_KEY` — SEO-оптимизация.

Enter без ввода пропускает приложение.

## Требования к приложениям

- Workflow должен быть **опубликован** и иметь **End-узел с выходными
  переменными** — иначе API вернёт пустые `outputs`.
- Входные переменные лучше называть предсказуемо: `topic`, `query`, `text`,
  `channel` — чтобы завод мог подставлять значения без ручной настройки.
- Ответ желательно отдавать текстом или JSON-строкой (список статей/трендов).

## Готовый пост → сразу в Telegram

В `config/settings.yaml`:

```yaml
pipeline:
  post_generator: dify_app   # internal | dify_app
  dify_post_app: posts       # ключ из integrations.dify_apps
integrations:
  dify_apps:
    posts:
      api_key_env: DIFY_POSTS_API_KEY
      timeout: 180
      daily_limit: 20        # запусков workflow в сутки, 0 = без лимита
      output_key: ''         # имя переменной End-узла; пусто = первая непустая
      inputs:
        channel: '{channel}'
        topic: '{topic}'
```

Завод берёт сюжет из свежих новостей, отправляет `channel` и `topic` в
приложение, проверяет ответ (язык, отсутствие кириллицы в EN, длина,
стоп-слова), экранирует под Telegram HTML и публикует. Если приложение
недоступно, вернуло пустой ответ или дневной лимит исчерпан — срабатывает
встроенная генерация (LLM/extractive), постинг не останавливается.

Публикация в Telegram настраивается скриптом:

```bash
python3 scripts/set_telegram_env.py
```

Токен бота — у @BotFather, бота нужно добавить администратором в каждый
канал с правом «Публикация». Скрипт проверит токен, запишет id каналов и
по подтверждению выключит dry-run.

## Проверка приложений

Команда показывает имя, тип, объявленные входы и может сделать тестовый
запуск с вашими значениями:

```bash
# только проверка ключей и входов
python3 -m content_factory dify-apps

# тестовый запуск новостного приложения
python3 -m content_factory dify-apps --run news \
  --input channel=tech-ai --input topic="AI news"
```

Если в ответе `outputs: {}` — в Workflow нет End-узла с выходной
переменной, либо приложение не опубликовано (API работает только с
опубликованной версией).

## Как переделать «Six-Channel Editorial News Draft Factory»

Цель: приложение, которое по `channel` + `topic` само ищет новости, делает
SEO-оптимизацию и отдаёт **готовый пост** (текст для Telegram).

1. Откройте приложение → **Orchestrate** (редактор workflow).
2. Убедитесь, что у финального узла (LLM/Answer/Tool) есть выход.
3. Добавьте узел **End** из панели узлов и соедините с финальным узлом.
4. В узле End нажмите **Add output variable**:
   - имя: `result` (или `draft`), тип: String;
   - значение: выход финального узла, например `{{#llm.text#}}` — это и есть
     готовый пост, который завод опубликует в Telegram.
5. Нажмите **Publish** — Service API берёт только опубликованную версию.
6. Проверьте через **Run** в Dify: должны появиться входы `channel` и
   `topic`, а в конце — `result`.
7. **Access Point → API Keys → Create new API key** и вставьте ключ в
   `DIFY_NEWS_API_KEY` через `python3 scripts/set_dify_app_keys.py`.

Важно: если LLM-узел использует Dify Hosted OpenAI, а его бесплатная квота
исчерпана (`provider_quota_exceeded`), переключите модель на своего
провайдера в настройках узла или в Settings → Model Provider.

После добавления ключей завод снимает `/parameters` каждого приложения,
проверяет входы/выходы тестовым запуском и подключает их к конвейеру.

## World News API — новости и картинки (бесплатно)

Бесплатный тариф [World News API](https://worldnewsapi.com): **50 points/сутки**,
запрос стоит 1 point + 0.01 за каждый результат, сброс в 00:00 UTC. В ответе —
заголовок, полный текст, `summary`, **`image`** (картинка статьи), дата
публикации, категория, язык и тональность.

Подключение ключа (скрытый ввод, ключ проверяется запросом search-news):

```bash
python3 scripts/set_worldnews_key.py
```

Ключ сохраняется в `.env` как `WORLD_NEWS_API_KEY`.

Источник объявляется в `config/channels.en.yaml` (у каждого канала свой запрос):

```yaml
  - id: worldnews
    type: worldnews
    url: https://api.worldnewsapi.com/search-news
    name: World News API
    weight: 1.1
    options:
      query: artificial intelligence technology
      language: en
      max_items: 10
      sort: publish-time
      trust: true
```

Расход под наш график: **1 запрос на канал за запуск** (каждый час) ≈ 24–26
points/сутки — укладывается в бесплатные 50. При исчерпании квоты API отвечает
HTTP 402: источник пропускается с предупреждением, завод продолжает работать на
RSS. Картинка статьи сохраняется в `article.meta["image"]`.

## newsdata.io и Currents API — новости с картинками

Оба подключаются ключами из `scripts/set_extra_keys.py`
(`NEWSDATA_API_KEY`, `CURRENTS_API_KEY`). Источники уже добавлены в
`config/channels.en.yaml` (`type: newsdata` / `type: currents`), ключи берутся
из `.env`.

Бесплатные лимиты (проверяйте актуальные в личных кабинетах): newsdata.io —
около 200 кредитов/сутки, Currents — около 600 запросов/сутки. При нашем графике
(1 запуск канала в час) это ~24 запроса/сутки на сервис.

Оба API отдают картинку статьи (`image_url` / `image`) — она сохраняется в
`article.meta["image"]` и используется для фото-поста в Telegram.

## Картинки и короткие ссылки в посте

- Картинка берётся из Dify-приложения (`image_url`) или из статьи
  (`meta["image"]` — World News API / RSS media / newsdata / Currents).
- Telegram-публикатор отправляет **фото с подписью** (`sendPhoto`), если текст
  ≤1000 символов; иначе — обычное сообщение (чтобы не обрезать пост).
- Ссылка на источник сокращается через TinyURL и добавляется в конец поста.

## Рост и контент: Similarweb + кураторские RSS (Feedly/Substack/Beehiiv)

Из списка «Помогает росту и контенту — держать под рукой» подключены две вещи,
не требующие платных API-ключей.

### Кураторские RSS-источники

`config/sources.curated.yaml` — отдельный файл с подборкой лент «как в Feedly/
Feedspot»: Substack-авторы (Import AI, One Useful Thing, Simon Willison,
The Defiant), дайджесты (TLDR AI) и отраслевые медиа (Blockworks, BeInCrypto).
Источники подмешиваются к каналам по `id` (`ai-news`, `crypto-news`), ключ `*` —
ко всем каналам; дубли по `url`/`id` с уже прописанными источниками
отбрасываются. Аккаунты Feedly/Feedspot для этого не нужны — у всех лент есть
открытый RSS.

```bash
# посмотреть количество источников по каналам (с учётом кураторских)
python -m content_factory channels
# проверить, что ленты реально отдаются
python -m content_factory sources check --channel ai-news
python -m content_factory sources check --channel crypto-news
```

Свой файл можно положить в другое место и указать путь переменной
`CONTENT_FACTORY_CURATED_SOURCES` (или `app.curated_sources_file` в settings.yaml).

### Similarweb — конкуренты и их трафик

Бесплатный endpoint из Chrome-расширения Similarweb (ключ не нужен):
визиты/мес, глобальный и страновой ранг, отказы, глубина, время на сайте,
категория, доли стран и источники трафика.

```bash
# отчёт по группам ai / crypto / sports (по умолчанию все)
python scripts/competitor_traffic.py --group crypto
# свои домены и отправка сводки в Telegram (TELEGRAM_ALERT_CHAT_ID)
python scripts/competitor_traffic.py --domains cointelegraph.com,decrypt.co --send
```

Отчёт пишется в `data/reports/competitors-YYYY-MM-DD.md`, JSON — по `--json-out`.
В облаке это делает workflow `competitors` (ежедневно, 10:25 МСК).

**Важно:** `data.similarweb.com` отдаёт 403 из РФ (CloudFront geo-block) и,
как показал запуск на раннере, из GitHub Actions тоже (блок по ASN облачных
провайдеров). Поэтому отчёт в Actions сейчас заполняется строкой «нет данных».
Варианты, если данные нужны: запускать с residential/VPN-IP, использовать
платный Similarweb API или бесплатный keyed-провайдер (например, OpenWeb Ninja)
— тогда в `content_factory/integrations/similarweb.py` меняется только
`_http_get_json` + заголовок с ключом.
