# Расширение контент-завода

Проект специально разделён на слои: источники, NLP, публикаторы, аналитика.
Добавляя новое, вы почти всегда меняете один слой и одну запись в реестре.
Ниже — рабочие рецепты с реальными интерфейсами.

> Перед изменениями сделайте копию проекта или коммит в git. После —
> запустите `python -m unittest discover -s tests -v` и
> `python -m content_factory run --channel all --dry-run`.

## 1. Новый канал (без кода)

Самый частый случай — просто добавить седьмой канал. Код не нужен.

1. Скопируйте блок канала в `config/channels.yaml`, задайте новый `id`,
   `topics`, `sources`, `schedule`, `formats`.
2. Создайте канал в Telegram, добавьте бота администратором.
3. Добавьте в `.env` переменную `TELEGRAM_CHAT_ID_<ID>` (см.
   [channels.md](channels.md)).
4. Проверьте и запустите:

```bash
python -m content_factory channels
python -m content_factory sources check --channel my-new-channel
python -m content_factory run --channel my-new-channel --dry-run
```

Подробнее — [channels.md](channels.md).

## 2. Новый тип источника

### 2.1. Как устроено

- `content_factory/sources/base.py` — базовый класс `SourceAdapter`:
  атрибут `type`, методы `fetch(source, settings) -> list[Article]` и
  `check(source, settings) -> (bool, str)`. Метод `check` можно не
  переопределять: базовый класс сам делает пробную загрузку.
- Готовые адаптеры: `rss.py` (`type = "rss"`), `web.py` (`type = "web"`),
  `telegram.py` (`type = "telegram"`).
- `content_factory/sources/__init__.py` — реестр `_ADAPTERS`: по строке `type`
  из `channels.yaml` возвращается нужный адаптер.
- Вспомогательные функции в `sources/base.py`: `build_article`,
  `request_params`, `absolute_url`, `clean_title`, `make_summary`,
  `extract_paragraphs`, `same_domain`, `max_text_chars`.

### 2.2. Пример: источник из JSON API

Создайте `content_factory/sources/json_feed.py`:

```python
"""Пример адаптера: новости из JSON API."""
from __future__ import annotations

import json
from typing import List

from ..config import Settings
from ..models import Article, SourceConfig
from ..utils import FetchError, http_get_text, parse_datetime
from .base import (
    SourceAdapter,
    build_article,
    clean_title,
    make_summary,
    request_params,
)


class JsonFeedAdapter(SourceAdapter):
    type = "json_feed"

    def fetch(self, source: SourceConfig, settings: Settings) -> List[Article]:
        params = request_params(settings)
        try:
            raw = http_get_text(source.url, **params)
            payload = json.loads(raw)
        except (FetchError, ValueError) as exc:
            raise FetchError(f"{source.id}: {exc}") from exc

        items = payload.get("items") or []
        limit = int(source.options.get("max_items", 30))
        articles: List[Article] = []
        for item in items[:limit]:
            url = str(item.get("url") or "")
            article = build_article(
                source,
                settings,
                url=url,
                title=clean_title(str(item.get("title") or "")),
                published_at=parse_datetime(item.get("date")),
                text=str(item.get("text") or ""),
                summary=make_summary(str(item.get("summary") or "")),
            )
            if article is not None:
                articles.append(article)
        return articles
```

Зарегистрируйте адаптер в `content_factory/sources/__init__.py`:

```python
from .json_feed import JsonFeedAdapter

_ADAPTERS = {
    RSSAdapter.type: RSSAdapter(),
    WebAdapter.type: WebAdapter(),
    TelegramAdapter.type: TelegramAdapter(),
    JsonFeedAdapter.type: JsonFeedAdapter(),
}
```

Подключите в `config/channels.yaml`:

```yaml
sources:
  - id: my-json
    type: json_feed
    url: https://example.com/api/news.json
    name: Мой JSON-источник
    weight: 1.1
    options: {max_items: 20}
```

Проверьте:

```bash
python -m content_factory sources check --channel tech-ai
```

### 2.3. Правила для адаптера

- Возвращайте только `Article` (из `content_factory/models.py`), созданные
  через `build_article` — тогда дедупликация и веса источников работают.
- Сетевые/форматные ошибки оборачивайте в `FetchError`: конвейер поймает его
  и продолжит работу с другими источниками.
- Не бросайте исключения из `check` — базовый класс сам их гасит, но лучше
  возвращать понятное сообщение.
- Не ходите в сеть в конструкторе; адаптер должен быть лёгким.
- Уважайте `robots.txt` и не делайте частых запросов: конвейер и так
  последовательный.

## 3. Новая соцсеть (публикатор)

### 3.1. Как устроено

- `content_factory/publishers/base.py` — абстрактный `Publisher`:
  атрибут `name`, метод `publish(post, channel, settings) -> PublishResult`,
  метод `check() -> (bool, str)`, помощник `_result(...)`.
- Готовые: `telegram.py` (`telegram`), `vk.py` (`vk`), `dryrun.py`
  (`dryrun`).
- `content_factory/publishers/__init__.py` — реестр `_REGISTRY` и алиасы.
- `get_publisher(name, settings)` **при `settings.dry_run` всегда возвращает
  `DryRunPublisher`**, даже если запрошен telegram/vk. Это защита от
  случайной публикации: реально отправлять можно только при выключенном
  dry-run.
- Длинный HTML режется `split_html_message(text, limit)` без разрыва тегов
  (лимит Telegram — 4096). Для ВК используйте `strip_html` и лимит
  `VK_MESSAGE_LIMIT`.

### 3.2. Пример: публикатор для сайта/заглушки

```python
"""Пример: запись поста в файл или отправка на свой сайт."""
from __future__ import annotations

from typing import Tuple

from ..config import Settings
from ..models import ChannelConfig, GeneratedPost, PublishResult
from ..utils import env, strip_html
from .base import Publisher


class WebhookPublisher(Publisher):
    name = "webhook"

    def publish(
        self, post: GeneratedPost, channel: ChannelConfig, settings: Settings
    ) -> PublishResult:
        # Никаких исключений наружу: любая ошибка -> PublishResult(ok=False).
        webhook_url = env("WEBHOOK_URL", "")
        if not webhook_url:
            return self._result(
                post, channel, ok=False, error="WEBHOOK_URL не задан"
            )
        try:
            # ... здесь отправка strip_html(post.text) на webhook_url ...
            external_id = "webhook-42"
            return self._result(
                post,
                channel,
                ok=True,
                external_id=external_id,
                url=webhook_url,
            )
        except Exception as exc:  # noqa: BLE001
            return self._result(post, channel, ok=False, error=str(exc))

    def check(self) -> Tuple[bool, str]:
        return (bool(env("WEBHOOK_URL", "")), "WEBHOOK_URL задан/не задан")
```

Регистрация в `publishers/__init__.py`:

```python
from .webhook import WebhookPublisher

_REGISTRY = {
    "telegram": TelegramPublisher,
    "vk": VKPublisher,
    "dryrun": DryRunPublisher,
    "webhook": WebhookPublisher,
}
```

Включение у канала (`config/channels.yaml`):

```yaml
publisher_ids: [telegram, webhook]
```

и токен/URL в `.env` (`WEBHOOK_URL=...`). Для ВК/Telegram также должны быть
заданы токены, иначе `publish` вернёт `ok=False` с понятной ошибкой.

### 3.3. Пример «ВКонтакте уже есть»

`VKPublisher` использует:
- `VK_ACCESS_TOKEN` — токен группы с правами `wall`, `manage`;
- `VK_GROUP_ID` — числовой id сообщества;
- `api_version` из `config/settings.yaml` (`publishers.vk.api_version`);
- метод `wall.post`.

По этой же схеме добавляются Одноклассники (API OK), Дзен, собственный сайт
или email-рассылка. Главное — вернуть корректный `PublishResult` и не
бросать исключения.

## 4. Новый формат поста

1. Добавьте генератор в `content_factory/nlp/generator.py` (по аналогии с
   `generate_post`/`generate_digest`). Он должен возвращать `GeneratedPost`.
2. Разрешите формат в валидаторе `content_factory/config.py`
   (`_parse_channel`: множество `allowed_formats`).
3. Добавьте формат в `formats` нужных каналов в `config/channels.yaml`.
4. Проверьте на dry-run: `run --channel ... --dry-run` и откройте
   `data/outbox/`.

Формат должен:
- укладываться в `channel.max_post_chars` (по умолчанию 3500);
- содержать блок ссылок на источники (проверка `quality_issues`);
- не содержать стоп-слов (`pipeline.banned_words`);
- быть валидным Telegram HTML (`<b>`, `<i>`, `<a href="...">`, `<br>` и
  т.п.).

## 5. Новый LLM-провайдер

1. В `content_factory/nlp/llm.py` создайте класс-наследник `LLMClient`,
   реализуйте `_generate(prompt, system, max_tokens, temperature) -> str`.
   Сетевые ошибки должны приводить к `LLMError`.
2. Добавьте ветку в `get_llm()`.
3. Разрешите имя провайдера в `content_factory/config.py`
   (`_validate_settings`, множество `allowed`).
4. Добавьте настройки в `config/settings.yaml` (секция `llm.<provider>`), а
   секреты — в `.env`.
5. Проверьте: `python -m content_factory llm-test`.

Контракт клиента: атрибуты `name` (str), `available` (bool) и метод
`generate(prompt, system="", max_tokens=None, temperature=None) -> str`,
который **не бросает исключений** и возвращает пустую строку при сбое.
Конвейер сам откатится на extractive-режим.

## 6. Своя аналитика

- `content_factory/analytics/collector.py` — `collect_all(channels, settings,
  storage)` собирает снимки метрик (`MetricSnapshot`) и сохраняет в SQLite.
- `content_factory/analytics/report.py` — `save_report(settings, storage,
  channels, days=7)` формирует HTML и Markdown.
- Данные берите из `Storage`: `global_stats`, `channel_stats`,
  `recent_runs`, `recent_publishes`, `latest_metrics`, `article_sources`.

Чтобы добавить метрику:

1. Добавьте поле в `MetricSnapshot` (`content_factory/models.py`).
2. Заполните его в коллекторе и сохраните в `metrics.payload` (JSON) —
   схему SQLite менять не нужно.
3. Выведите в отчёте.

Помните: Bot API не отдаёт просмотры постов, только подписчиков. Для
просмотров нужна Telethon-сессия или ручной экспорт.

## 7. Тесты и проверки

- Тесты: `python -m unittest discover -s tests -t . -v`.
- Синтаксис: `python -m compileall -q content_factory`.
- Быстрая проверка: `bash scripts/check.sh`.
- Перед реальной публикацией — всегда `--dry-run` и просмотр
  `data/outbox/<канал>/`.

Если добавляете модуль, покройте его хотя бы одним тестом в `tests/` с
запуском без сети (моки `http_get`/`http_get_text`). Это ускоряет проверку
после обновлений.
