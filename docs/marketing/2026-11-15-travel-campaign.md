# Travel-кампания: 15–21 ноября 2026

Страницы и их канонические адреса:
- RU «Туры за рубеж» — https://valdislavn-spec.github.io/content-factory/flight-hotel-abroad/
- EN «US travel deals» — https://valdislavn-spec.github.io/content-factory/flight-hotel-us/

## Каналы

| Канал | Статус | Что публикуем |
|---|---|---|
| Telegram TRAVEL (@GOODTRAVEL007) | работает (через relay) | RU-посты: abroad + промо |
| Pinterest (VV) | работает | 4 новых пина (1000×1500) → abroad |
| Bluesky (@b-rave007) | работает | EN-пост про US travel deals |
| Akkoma (miraiverse.xyz) | работает | EN-пост (RU-контент не публикуем) |
| Tumblr (vlad-007) | работает | лонгрид «где дешевле зимой» |
| ES-Telegram | работает | испаноязычный дайджест |
| X / Buffer, Mastodon, VK, Reddit, FB, IG, LinkedIn, Medium, Discord | недоступны | — |

## Календарь на 7 дней

| День | Канал | Текст |
|---|---|---|
| Пн 16.11 | Telegram + Pinterest | «12 стран: от 18 473 ₽ за двоих — Турция, Египет, ОАЭ, Таиланд, Мальдивы. Сводка цен на ноябрь–декабрь» → abroad |
| Вт 17.11 | Bluesky (EN) | «US travel deals: 12 winter escapes from New York — flight times, best months, verified promo codes» → US |
| Ср 18.11 | Akkoma (EN) | повтор анонса направлений + промо партнёров |
| Чт 19.11 | Tumblr | лонгрид «Куда поехать зимой дешевле: 5 направлений с ценами» |
| Пт 20.11 | Telegram | «Абхазия от 18 473 ₽ — самое дешёвое зарубежное направление. 58 предложений, 5 ночей» |
| Сб 21.11 | Pinterest | пин «Италия от 240 442 ₽ + промо музеев» |
| Вс 22.11 | Telegram/email | дайджест недели; лучшее по вовлечению — повторить |

## Трекинг и своя база (обновлено 15.11, 08:35 PST)

**Хранилище переехало с Cloudflare KV на D1** — дневной лимит записей KV (1000/сутки) больше не блокирует:
воркер `links-tracker` переписан на D1 (`links`, `clicks`, `subscribers`), задеплоен, проверен end-to-end
(создание ссылки → редирект 200 → клик 204 → статистика). Free-план D1: 100k записей/сутки.

Созданы 10 кодов кампании:

| Код | Канал | Цель |
|---|---|---|
| tr-hub-tg / tr-hub-bsky / tr-hub-akkoma | telegram / bluesky / akkoma | хаб направлений |
| tr-ab-tg / tr-ab-pin / tr-ab-bsky / tr-ab-akkoma | telegram / pinterest / bluesky / akkoma | туры за рубеж |
| tr-us-bsky / tr-us-pin | bluesky / pinterest | US deals |
| tr-ru-tg | telegram | пакетные туры (surge) |

Формат: `https://links-tracker.valdislav-n.workers.dev/r/<код>` · статистика: `.../stats?token=...`

**Своя email-база (вместо Brevo-списка)** — на всех 12 страницах направлений, хабе и трёх лендингах
стоит форма подписки, которая пишет email в D1 через `POST /subscribe` (lang ru/en).
Выгрузка: `GET /admin/subscribers?token=...`. Brevo больше не обязателен: рассылку можно делать
из выгрузки, а Brevo подключить позже (нужен ключ + импорт CSV).

## KPI недели

- 100 переходов на abroad, 50 на US, 20 кликов по партнёрским ссылкам (`*.tpk.ro` в Travelpayouts).
- Pinterest: 4 пина → ≥3% saves/impressions.
- Индексация: 3 страницы с JSON-LD (WebPage + BreadcrumbList + ItemList + FAQPage) — проверено на живых страницах 15.11.

## Уже опубликовано (15.11.2026)

- Bluesky (EN): https://bsky.app/profile/b-rave007.bsky.social/post/3n2efvx7jcm2r — анонс 12 направлений + US deals
- Akkoma (EN): см. пост «Destination pages are live» (RU-версия удалена по требованию: Akkoma — англоязычная площадка)
- Telegram TRAVEL (RU): https://t.me/GOODTRAVEL007/6 — хаб направлений с ценами и ссылками
- Pinterest: 4 пина (pin/1105774514796612676, …612694, …612725, …612744)

## Programmatic SEO (новое, 13 страниц)

- Хаб: https://valdislavn-spec.github.io/content-factory/destinations/
- 12 страниц: /destinations/abkhaziya/, /turciya/, /oae/, /egipet/, /kipr/, /greciya/, /tailand/,
  /vietnam/, /indoneziya/, /maldivy/, /ispaniya/, /italiya/ — у каждой canonical, JSON-LD
  (WebPage + BreadcrumbList + Product/Offer + FAQPage), видимый FAQ, перелинковка и партнёрские CTA.
- Все 13 URL добавлены в sitemap.xml.

## Подписка

На страницах направлений и хабе стоит блок «Новые цены — раз в неделю»: основной CTA — Telegram-канал
(работает), email-вариант — mailto до подключения Brevo. Для полноценного double opt-in нужен
BREVO_API_KEY и RU-список в Brevo (сейчас списки пустые, ключа в .env нет).

## Брендированный email (15.11, 08:50 PST)

Собрано:
- `scripts/brand_email.py` — брендированное письмо RU/EN (тёмный дизайн, таблица 8 цен, промо партнёров,
  CTA с трекинг-кодами `tr-mail-hub` / `tr-mail-abroad` / `tr-mail-us`, подвал с отпиской).
  Превью: `.local/email/digest-ru.png`.
- `scripts/send_digest.py` — рассылка по списку из D1: `--dry-run` (собирает `.eml`),
  `--to addr` (тест), `--limit`, `--lang`. SMTP: `smtp-relay.brevo.com:587` (креды в `listmonk/.env`).
- Отписка: `GET /unsubscribe?e=<email>&t=<sha256(email|ADMIN_TOKEN)[:32]>` на воркере — одним кликом,
  без подтверждений; подписка снова снимает флаг (resubscribe).
- Страница политики для дайджеста: `/privacy-digest.html` (ссылка в каждом письме).

**Блокер отправки:** Brevo SMTP отвечает `525 5.7.1 Unauthorized IP address` — у аккаунта включён
список разрешённых IP. Чтобы письма пошли, нужно в Brevo → SMTP & API → Authorized IPs добавить
текущий IP `79.172.64.10` (или выдать `BREVO_API_KEY` для HTTP API). Код и письма готовы,
отправка — одна команда: `python3 scripts/send_digest.py --to valdislav.n@gmail.com`.

## Замена Brevo (варианты отправки)

Отправка абстрагирована: `scripts/email_providers.py` + `EMAIL_PROVIDER` в `.env`.
Поддержаны: `smtp`, `resend`, `mailersend`, `sendgrid`, `mailgun`, `postmark`, `unisender`.
Проверка настроек: `.venv/bin/python scripts/send_digest.py --check`.

| Провайдер | Free-tier (ориентир) | Что нужно | Комментарий |
|---|---|---|---|
| Resend | 3 000 писем/мес, 100/день | `RESEND_API_KEY` + домен (или onboarding@resend.dev) | самый быстрый старт, хорошая доставляемость |
| MailerSend | 3 000 писем/мес | `MAILERSEND_API_KEY` + домен | аналог Resend |
| SendGrid | 100 писем/день | `SENDGRID_API_KEY` + verify sender | иногда ручная проверка аккаунта |
| Mailgun | 100 писем/день (trial) | `MAILGUN_API_KEY`, `MAILGUN_DOMAIN` | удобный sandbox-домен |
| Postmark | 100 писем/мес (dev) | `POSTMARK_TOKEN` | лучший для транзакционных |
| AWS SES | ~$0.10/1000 | AWS + DKIM + выход из sandbox | дешевле всех на объёме |
| Gmail SMTP | 500 писем/день | App Password (2FA) | 0 регистраций, но подпись «via gmail» |
| Unisender Go | 1 500 писем/мес (RU) | `UNISENDER_API_KEY` | лучшая доставляемость на mail.ru/yandex |
| Brevo (текущий) | 300/день | добавить IP `79.172.64.10` в Authorized IPs | уже настроен, нужен один клик |

Проверено с этой машины: API и SMTP всех перечисленных провайдеров доступны (TCP 587 открыт,
HTTP-эндпоинты отвечают 401/403/405 без ключей).
