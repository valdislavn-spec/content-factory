# Шаблоны deals-постов и закрепов (EN/ES)

Дата: 09.11.2026. Проект: `product-deals-project.md`.
Использование: тексты копируются в очередь `data/deals/queue.yaml` и рендерятся
скриптом `scripts/deals_post.py` (он же подставляет shortlink + UTM и маркировку).

## Правила

- 1 товарный пост на 3–4 обычных поста в канале.
- В каждом посте — маркировка «партнёрская ссылка / advertising / enlace de afiliado».
- Цена всегда с оговоркой «на момент публикации» — она меняется.
- Ссылки только через shortlink + UTM: `utm_source=tg_<channel>&utm_medium=telegram&utm_campaign=deals_<program>`.
- Для агентов (Sugargoo) честно писать: «цена товара, доставка считается отдельно».

## Формат A — «Находка дня» (EN)

```
🛒 {TITLE}

Price: {OLD} → {PRICE} ({DISCOUNT}%){EXTRA_HOOK}

👉 {LINK}

⚠️ Affiliate link. Price at time of posting.
```

## Формат A — «Находка дня» (ES)

```
🛒 {TITLE}

Precio: {OLD} → {PRICE} ({DISCOUNT}%){EXTRA_HOOK}

👉 {LINK}

⚠️ Enlace de afiliado. Precio al momento de la publicación.
```

## Формат B — «Подборка» (EN/ES)

```
🔥 {TITLE}

1. {ITEM_1} — {PRICE_1} → {LINK_1}
2. {ITEM_2} — {PRICE_2} → {LINK_2}
3. {ITEM_3} — {PRICE_3} → {LINK_3}

⚠️ Affiliate links. / ⚠️ Enlaces de afiliado.
```

## Формат C — «Как заказать из Китая через агента» (ES — основной для futbol-es)

```
👕 {TITLE}: {PRICE} vía agente

• Cómo pedir: {STEPS}
• Plazo/entrega: {DELIVERY}
• Precio del producto, envío se calcula aparte

👉 {LINK}

⚠️ Enlace de afiliado.
```

## Закреп «Deals» (EN, для ai-news/sport-news)

```
🛒 Deals & finds we use

• Temu — gadgets under $10 → {TEMU_LINK}
• Banggood — RC/FPV, e-bikes, tools → {BANGG_LINK}
• Sugargoo — order from China via agent → {SUGARGOO_LINK}
• AliExpress — daily deals → {ALIEXPRESS_LINK}

⚠️ Affiliate links. Prices may change.
```

## Закреп «Ofertas» (ES, для futbol-es/tech-ai-es)

```
🛒 Ofertas y hallazgos

• Sugargoo — pedir de China por agente (camisetas, botas, gadgets) → {SUGARGOO_LINK}
• Temu — gadgets y ofertas del día → {TEMU_LINK}
• Banggood — drones RC/FPV y bicis eléctricas → {BANGG_LINK}
• AliExpress — ofertas diarias → {ALIEXPRESS_LINK}

⚠️ Enlaces de afiliado. Los precios pueden cambiar.
```

## Примеры готовых постов (ES, Sugargoo)

Смотри сгенерированные тексты: `data/reports/deals-posts-2026-11-09.md`
(там же EN-версии для ai-news/sport-news).
