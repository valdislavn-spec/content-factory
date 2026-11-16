# Travel Finds — аудит и первые 6 страниц (16.11.2026)

## Что было проверено

- 11 URL в sitemap: главная EN/ES, 2 индекса блога, 4 EN-статьи, 2 ES-статьи, feed.
- Партнёрские ссылки в `assets/site-config.js`, `assets/main.js` и статьях.
- White Label виджет (`wl_id=24664`) и fallback-кнопки.
- 25 доступных программ Travelpayouts в проекте `Travel-finds` (`source=597756`).
- Трекер `links-tracker.valdislav-n.workers.dev`: 302 работает, клики пишутся.

## Найденные проблемы

1. В 5 статьях были вложенные битые ссылки вида `<a href="<a href="...">...`.
2. В 6 статьях было по два `<h1>`.
3. На главной дублировалась ссылка «Guides».
4. Не было GA4/аналитики страниц.
5. Не было отдельных SubID под страницы и рынки.
6. В `site-config.js` оставался placeholder `YOUR_WIDGET_PROMO_ID`.
7. В sitemap не было новых money-страниц.

## Что исправлено

- Битые вложенные ссылки заменены на нормальные партнёрские ссылки с `rel="sponsored nofollow noopener"`.
- Удалены дубли `<h1>`.
- Исправлена навигация на главной.
- Подключён GA4 `G-LC39S1FD7B` через `assets/analytics.js` на всех страницах.
- Placeholder `promoId` убран; White Label работает через `wlId`.
- Созданы 18 deep links Travelpayouts + 18 коротких ссылок трекера с SubID.
- Созданы 6 страниц:
  - `/guides/us-car-rental.html`
  - `/guides/us-esim.html`
  - `/guides/us-airport-transfers.html`
  - `/es/guias/alquiler-coches-espana.html`
  - `/es/guias/esim-viajar-latam.html`
  - `/es/guias/traslados-aeropuerto.html`
- Добавлены карточки на главные EN/ES и в индексы блогов.
- Sitemap обновлён.

## SubID / каналы

- US: `tf-us-car-*`, `tf-us-esim-*`, `tf-us-transfer-*`, канал `travel-finds-us`.
- Spain: `tf-es-car-*`, `tf-es-transfer-*`, канал `travel-finds-es`.
- LatAm: `tf-latam-esim-*`, канал `travel-finds-latam`.

## Экономика первых $100

Ориентир при текущих ставках:

- 3–4 бронирования авто: ~$60–100.
- 5–7 трансферов: ~$30–45.
- 10–15 продаж eSIM: ~$30–45.
- 3–5 активностей: ~$15–30.

Реалистичный первый чек — не «100 кликов», а 2–3 страницы с высоким чеком (аренда авто) + eSIM как повторяемая продажа.

## Что осталось

- Указать способ выплаты в Travelpayouts (баланс 0 ₽, минимум 1 000 ₽).
- Открыть Booking.com / GetYourGuide / DiscoverCars после 3 месяцев стабильного трафика.
- Смотреть GA4 + статистику трекера: pageviews → affiliate_click → бронирование.
- Добавить ещё страницы под города/аэропорты после первых кликов.

## Статус деплоя

- Ветка: `travel-finds/merge-money-pages-2026-11-16`.
- Коммит в `main`: `a9945c7`.
- GitHub Actions `deploy-surge` — success.
- Live: https://travel-finds.surge.sh/guides/us-car-rental.html
- Проверено: 6 страниц отдают 200, партнёрские ссылки ведут через трекер, GA4 `page_view` отправляется.
