# ES AI News: отдельный подбор источников

World News API с испанским запросом даёт мало релевантных результатов
(`inteligencia artificial` + `categories: technology` — 4 новости, и те не про ИИ).
Поэтому для `tech-ai-es` нужен отдельный набор: испанские RSS, Google News RSS
по странам и локальная фильтрация. Ниже — что нашёл на GitHub и какие фиды
реально отдают RSS.

## GitHub: что брать

| Репозиторий | ★ | Что внутри | Как использовать |
|---|---:|---|---|
| [plenaryapp/awesome-rss-feeds](https://github.com/plenaryapp/awesome-rss-feeds) | 2.9K | OPML по странам, включая Spain и Mexico | Импортировать OPML, взять проверенные фиды |
| [fuxiaoai/tidings-rss](https://github.com/fuxiaoai/tidings-rss) | 642 | Курируемые OPML: AI, news, research, tech media | Взять `tidings-ai.opml`/`tidings-news.opml` и отфильтровать ES |
| [dav009/awesome-spanish-nlp](https://github.com/dav009/awesome-spanish-nlp) | 352 | Ресурсы для NLP на испанском | Классификация/суммаризация ES-текстов |
| [vishalshar/awesome_ML_AI_RSS_feed](https://github.com/vishalshar/awesome_ML_AI_RSS_feed) | 302 | AI/ML RSS (в основном EN) | Английские AI-фиды как дополнение |
| [chibbtx/mexico-monitor](https://github.com/chibbtx/mexico-monitor) | 0 | 25+ мексиканских RSS + перевод и фильтр релевантности | Идеи для MX-подборки |
| [rafaelxoliver4-art/tmt-clipping](https://github.com/rafaelxoliver4-art/tmt-clipping) | 0 | LatAm tech clipping: ~380 источников, Google News RSS + direct feeds | Архитектура дедупа/скоринга для LatAm |
| [IvanAtWork-agent/el-resumen-del-dia](https://github.com/IvanAtWork-agent/el-resumen-del-dia) | 0 | Ежедневный испанский дайджест из RSS | Шаблон дайджеста |
| [virtualawyer/matutino](https://github.com/virtualawyer/matutino) | 0 | Self-hosted газета из RSS, EN/ES | Идеи вёрстки/дайджеста |
| [fbalbachan/TecnoNews](https://github.com/fbalbachan/TecnoNews) | 0 | Автоматический ES-пайплайн: RSS → анализ → рерайт → WordPress | Референс пайплайна |
| [orgullodominicanoorg/rss-republica-dominicana](https://github.com/orgullodominicanoorg/rss-republica-dominicana) | 0 | OPML испаноязычных фидов | Дополнительные ES-фиды |

## OPML, которые можно импортировать

- Spain: [Spain.opml](https://github.com/plenaryapp/awesome-rss-feeds/blob/master/countries/with_category/Spain.opml)
- Mexico: [Mexico.opml](https://github.com/plenaryapp/awesome-rss-feeds/blob/master/countries/with_category/Mexico.opml)
- Tidings OPML: [opml/](https://github.com/fuxiaoai/tidings-rss/tree/main/opml)

Raw-ссылки для импорта:

```text
https://raw.githubusercontent.com/plenaryapp/awesome-rss-feeds/master/countries/with_category/Spain.opml
https://raw.githubusercontent.com/plenaryapp/awesome-rss-feeds/master/countries/with_category/Mexico.opml
```

## Проверенные ES-фиды

Все URL ниже отдали HTTP 200:

- Xataka: `https://feeds.weblogssl.com/xataka2`
- Genbeta: `https://feeds.weblogssl.com/genbeta`
- El País / Tecnología:
  `https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/tecnologia/portada`
- El Confidencial / Tecnología: `https://rss.elconfidencial.com/tecnologia/`
- Hipertextual: `https://hipertextual.com/feed` (уже в конфиге)
- FayerWayer: `https://www.fayerwayer.com/feed/` (уже)
- ABC Tecnología: `https://www.abc.es/rss/feeds/abc_tecnologia.xml` (уже)
- La Nación Tecnología: уже в конфиге
- El Financiero (MX): уже в конфиге

## Google News RSS — лучший бесплатный ES-источник

Можно генерировать под каждую страну без API-ключа:

```text
https://news.google.com/rss/search?q=inteligencia+artificial+OR+IA&hl=es-419&gl=MX&ceid=MX:es-419
https://news.google.com/rss/search?q=inteligencia+artificial+OR+IA&hl=es&gl=ES&ceid=ES:es
https://news.google.com/rss/search?q=inteligencia+artificial+OR+IA&hl=es-419&gl=AR&ceid=AR:es-419
https://news.google.com/rss/search?q=inteligencia+artificial+OR+IA&hl=es-419&gl=CO&ceid=CO:es-419
https://news.google.com/rss/search?q=inteligencia+artificial+OR+IA&hl=es-419&gl=CL&ceid=CL:es-419
```

Плюсы: бесплатно, свежие новости, локальные издания, язык/страна.
Минусы: заголовки и ссылки Google News, нужен резолв на оригинал; качество
зависит от запроса.

## Предлагаемый набор для `tech-ai-es`

```yaml
sources:
  - id: google-news-ia-mx
    type: rss
    url: https://news.google.com/rss/search?q=inteligencia+artificial+OR+IA&hl=es-419&gl=MX&ceid=MX:es-419
    name: Google News / IA México
    weight: 1.2
    options: {trust: true, max_items: 10}

  - id: google-news-ia-es
    type: rss
    url: https://news.google.com/rss/search?q=inteligencia+artificial+OR+IA&hl=es&gl=ES&ceid=ES:es
    name: Google News / IA España
    weight: 1.1
    options: {trust: true, max_items: 10}

  - id: xataka
    type: rss
    url: https://feeds.weblogssl.com/xataka2
    name: Xataka
    weight: 1.2
    options: {trust: true, max_items: 12}

  - id: genbeta
    type: rss
    url: https://feeds.weblogssl.com/genbeta
    name: Genbeta
    weight: 1.1
    options: {trust: true, max_items: 10}

  - id: elpais-tecnologia
    type: rss
    url: https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/tecnologia/portada
    name: El País / Tecnología
    weight: 1.2
    options: {trust: true, max_items: 10}

  - id: elconfidencial-tecnologia
    type: rss
    url: https://rss.elconfidencial.com/tecnologia/
    name: El Confidencial / Tecnología
    weight: 1.1
    options: {trust: true, max_items: 10}
```

## Фильтрация

В `topics` уже есть `inteligencia artificial`, `IA`, `tecnología`, `OpenAI`,
`Nvidia` и т.д. Добавить в `exclude_keywords`:

```text
fútbol, deportes, farándula, horóscopo, apuestas, recetas,
precio del dólar, type: "lotería", "celebridades"
```

И поднять `min_relevance` до **0.22–0.25**, иначе Google News подмешает
политику/спорт.

## Что уже добавлено в `tech-ai-es`

В `config/channels.es.yaml` добавлены 6 источников:

- `google-news-ia-mx` — Google News / IA México;
- `google-news-ia-es` — Google News / IA España;
- `xataka` — Xataka;
- `genbeta` — Genbeta;
- `elpais-tecnologia` — El País / Tecnología;
- `elconfidencial-tecnologia` — El Confidencial / Tecnología.

Плюс `min_relevance` поднят до **0.22**, а в `exclude_keywords` добавлены
`fútbol, deportes, farándula, recetas, lotería, celebridades, memes,
infidelidad, chisme, espectáculos`.

Проверка: `sources check --channel tech-ai-es` — **11/11 источников доступны**.

## Что я бы взял первым

1. Google News RSS **MX** и **ES** — самый быстрый прирост ES-новостей.
2. Xataka + Genbeta — tech/IA на испанском.
3. El País Tecnología + El Confidencial Tecnología — качество и авторитет.
4. `strict_topics: true` + `min_relevance: 0.25`.

Это даст 5–10 релевантных AI/tech-новостей в день без World News API.

## Оговорки

- Google News RSS может отдавать ссылки-редиректы; для полного текста нужен
  резолв или `trafilatura`/`newspaper`.
- Часть OPML-фидов может устареть; проверять `sources check`.
- Репозитории с 0 ★ — это идеи/код, не готовый прод.
- Не добавлять 10 испанских фидов сразу: сначала 3–4, потом расширять.
