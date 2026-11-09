# Брендовые шаблоны для всех соцсетей + партнёрские ссылки

Единый генератор изображений в фирменном стиле Content Factory
(тёмный неон, Playfair Display + Inter, монограмма «CF», сеть узлов) под все
площадки. В шаблон автоматически встраиваются:

- заголовок и подзаголовок темы (AI / Crypto / Sports);
- название сети/формата;
- **партнёрская ссылка** из `config/affiliates.yaml` (только статус `ready`);
- **QR-код** на партнёрскую ссылку;
- раскрытие «реклама/affiliate» и метка **18+** для age-restricted программ.

## Сети и размеры (config/brand_templates.yaml)

| Сеть | Размер | Layout |
|---|---|---|
| Telegram post | 1080×1350 | portrait |
| Telegram cover | 1280×640 | wide |
| Instagram square | 1080×1080 | square |
| Instagram post | 1080×1350 | portrait |
| Instagram story | 1080×1920 | story |
| X / Twitter | 1200×675 | wide |
| Facebook | 1200×630 | wide |
| LinkedIn | 1200×627 | wide |
| Mastodon | 1200×675 | wide |
| Bluesky | 1200×675 | wide |
| Threads | 1080×1350 | portrait |
| Pinterest pin | 1000×1500 | portrait |
| TikTok cover | 1080×1920 | story |
| YouTube thumbnail | 1280×720 | wide |
| OG image | 1200×630 | wide |
| Discord embed | 1200×630 | wide |

## Генерация

Рендер требует Pillow + segno. В этом окружении Pillow работает только в
DSH-python, поэтому:

```bash
DSHPY=/Users/vd/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/bin/python3
python3 -m pip install --target /tmp/segno segno pyyaml   # один раз

# список сетей/партнёрок/тем
PYTHONPATH=/tmp/segno $DSHPY scripts/brand_templates.py --list

# весь пак: все сети × все ready-партнёрки
PYTHONPATH=/tmp/segno $DSHPY scripts/brand_templates.py --all

# один шаблон с кастомным текстом
PYTHONPATH=/tmp/segno $DSHPY scripts/brand_templates.py \
  --network pinterest_pin --topic crypto --partner mylead \
  --headline "Crypto without hype" --subtitle "What actually happened" --out assets/brand
```

Результат: `assets/brand/<network>-<topic>-<partner>.png`.

## Партнёрские ссылки

Источник — `config/affiliates.yaml`, секция `programs`. В шаблоны попадают
только программы со статусом **`ready`** и непустым URL. Сейчас это:
`mylead` (MyLead) и `collaborator` (Collaborator.pro).

Чтобы добавить партнёрку:
1. в `config/affiliates.yaml` заполнить `url` и поставить `status: ready`;
2. перезапустить генерацию — появятся варианты с новой ссылкой и QR.

Правила: 1 партнёрский блок на 5 обычных постов, обязательное раскрытие
«реклама/affiliate», без обещаний доходности; для беттинга — 18+ и гео-правила.

## Настройка

- `config/brand_templates.yaml` — бренд, палитра, шрифты, темы, сети/размеры,
  партнёрки, QR, каталог вывода;
- `content_factory/brand/templates.py` — загрузка конфига, `ready_partners()`,
  `plan()`, `render()`;
- `scripts/brand_templates.py` — CLI (`--list`, `--all`, `--network`, `--topic`,
  `--partner`, `--headline`, `--subtitle`, `--cta`, `--out`, `--json`).

## Интеграция с публикациями

- Telegram: можно заменить/дополнить текущие карточки (`content_factory/cards.py`);
- Pinterest/Instagram/TikTok: готовые PNG под нужные размеры;
- OG image — для превью ссылок (лендинг, Telegram instant view);
- партнёрские вставки: изображение + disclosure (см. `config/affiliates.yaml`).

## Тесты

```bash
.venv/bin/python -m pytest -q tests/test_brand_templates.py
```

Проверяются конфиг, размеры, темы, фильтр ready-партнёрок и план рендера
(сам рендер требует PIL и в .venv недоступен).
## Автоподстановка в публикации

Партнёрские посты (строка `post.meta["affiliate"]`, вставляется раз в N постов
из `channel.affiliate`) автоматически получают брендовую карточку:

- сетка `telegram_post` (1080×1350), тема канала (AI/Crypto/Sports);
- заголовок поста, партнёрский чип, QR-код на партнёрскую ссылку;
- disclosure и 18+ (если partner age-restricted);
- путь кладётся в `post.meta["card_path"]` → Telegram отправляет её через
  `sendPhoto` вместо обычной карточки.

Выключатель: `BRAND_CARDS=0` (env) или `publishers.brand_cards.enabled: false`
в `config/settings.yaml`. Любая ошибка рендера не ломает публикацию — остаётся
обычная карточка.

Для остальных сетей шаблоны генерируются вручную/скриптом
(`scripts/brand_templates.py --network pinterest_pin ...`) — автоматическая
привязка к Pinterest/OG-превью в планах.
## GitHub Pages: брендовые пины и OG-превью

`scripts/build_brand_pages.py` генерирует пины и OG-картинки прямо в `docs/`
(их отдаёт GitHub Pages), а не только локально:

```bash
# брендовые Pinterest-пины (PNG+JSON) + манифест config/pinterest_brand_urls.yaml
python scripts/build_brand_pages.py --pins

# OG-превью для хаба и страниц каналов + meta og:image/twitter:image
python scripts/build_brand_pages.py --og

# всё сразу — этот вызов добавлен в workflow pins-generate
python scripts/build_brand_pages.py --all
```

- пины: `docs/assets/pins/brand/<channel>-<topic>-<partner>.png` + `.json`
  (готовый payload `POST /v5/pins`, `affiliate: true` → подхватывается
  `scripts/post_pins.py --only-affiliate`);
- манифест `config/pinterest_brand_urls.yaml` — публикатор Pinterest берёт
  URL брендового пина канала, если не задан `PINTEREST_IMAGE_URL[_CHANNEL]`;
- доски: `config/pinterest_boards.yaml` (channel_id → board_id) — реальные id
  подставляются в JSON-сайдкары, чтобы `post_pins.py` публиковал на нужную доску
  без `PINTEREST_BOARD_ID`;
- OG: `docs/assets/og/<page>.png`, в HTML добавляются `og:image`, `twitter:image`
  и `twitter:card=summary_large_image`;
- Pages база: `https://valdislavn-spec.github.io/content-factory`.

Workflow `pins-generate` (ежедневно) после генерации обычных пинов запускает
`build_brand_pages.py --all` и коммитит `docs/assets/pins`, `docs/assets/og`,
изменённые HTML и манифест.
