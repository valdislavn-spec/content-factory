# Travel-кампания: 15–21 ноября 2026

Страницы и их канонические адреса:
- RU «Пакетные туры 2026» — https://nezabyvaemoe.surge.sh/ (дубль: github.io/nezabyvaemoe-puteshestvie/)
- RU «Туры за рубеж» — https://valdislavn-spec.github.io/content-factory/flight-hotel-abroad/
- EN «US travel deals» — https://valdislavn-spec.github.io/content-factory/flight-hotel-us/

## Каналы

| Канал | Статус | Что публикуем |
|---|---|---|
| Telegram TRAVEL (@GOODTRAVEL007) | работает (через relay) | RU-посты: abroad + промо |
| Pinterest (VV) | работает | 4 новых пина (1000×1500) → abroad |
| Bluesky (@b-rave007) | работает | EN-пост про US travel deals |
| Akkoma (miraiverse.xyz) | работает | дубль RU-поста |
| Tumblr (vlad-007) | работает | лонгрид «где дешевле зимой» |
| ES-Telegram | работает | испаноязычный дайджест |
| X / Buffer, Mastodon, VK, Reddit, FB, IG, LinkedIn, Medium, Discord | недоступны | — |

## Календарь на 7 дней

| День | Канал | Текст |
|---|---|---|
| Пн 16.11 | Telegram + Pinterest | «12 стран: от 18 473 ₽ за двоих — Турция, Египет, ОАЭ, Таиланд, Мальдивы. Сводка цен на ноябрь–декабрь» → abroad |
| Вт 17.11 | Bluesky (EN) | «US travel deals: 12 winter escapes from New York — flight times, best months, verified promo codes» → US |
| Ср 18.11 | Akkoma | повтор RU-поста + промо партнёров |
| Чт 19.11 | Tumblr | лонгрид «Куда поехать зимой дешевле: 5 направлений с ценами» |
| Пт 20.11 | Telegram | «Абхазия от 18 473 ₽ — самое дешёвое зарубежное направление. 58 предложений, 5 ночей» |
| Сб 21.11 | Pinterest | пин «Италия от 240 442 ₽ + промо музеев» |
| Вс 22.11 | Telegram/email | дайджест недели; лучшее по вовлечению — повторить |

## Трекинг

Короткие ссылки создаются `scripts/links_admin.py create --code tr-ab-pin --target <url> --channel pinterest`.
Планируемые коды: `tr-ab-pin`, `tr-ab-tg`, `tr-ab-bsky`, `tr-ab-akkoma`, `tr-ab-mail`, `tr-us-pin`, `tr-us-bsky`, `tr-us-mail`, `tr-ru-tg`, `tr-ru-pin`.

⚠️ На 15.11 06:00 PST запись кодов недоступна: Cloudflare KV исчерпал дневной лимит (HTTP 429 / CF 10048). Сброс в 00:00 UTC = 16:00 PST 15.11. Чтение статистики работает: 23 кода, 141 клик.

## Email

Brevo активен (free 300 писем/сутки), но списки пустые: EN id=5 — 0 подписчиков, ES id=6 — 0, RU-списка нет. Рассылка невозможна до сбора базы. План: добавить форму подписки на лендинги (double opt-in) и только потом рассылать дайджест.

## KPI недели

- 100 переходов на abroad, 50 на US, 20 кликов по партнёрским ссылкам (`*.tpk.ro` в Travelpayouts).
- Pinterest: 4 пина → ≥3% saves/impressions.
- Индексация: 3 страницы с JSON-LD (WebPage + BreadcrumbList + ItemList + FAQPage) — проверено на живых страницах 15.11.
