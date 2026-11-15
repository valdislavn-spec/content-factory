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

## Gmail App Password (готово к включению)

- `scripts/setup_gmail_email.py` — интерактивная настройка: принимает адрес + 16-символьный
  App Password (ввод скрыт), проверяет SMTP-логин (`smtp.gmail.com:587`, STARTTLS), отправляет
  тестовое брендированное письмо и прописывает в `.env`: `EMAIL_PROVIDER=gmail`, `GMAIL_USER`,
  `GMAIL_APP_PASSWORD`, `EMAIL_FROM` (старый `.env` бэкапится в `.env.bak-<ts>`).
- В `email_providers.py` добавлен пресет `gmail` (хост/порт/креды, AUTH PLAIN fallback).
- Проверено: SMTP-путь живой — с неверным паролем Gmail отвечает `535 5.7.8 BadCredentials`
  (то есть сеть и TLS в порядке, нужен только настоящий App Password).
- Лимит Gmail: ~500 писем/сутки, From = `valdislav.n@gmail.com` + отображаемое имя бренда.

## Reply-To для писем (добавлено 15.11, 09:56 PST)

- В `email_providers.py` добавлен `EMAIL_REPLY_TO` / `EMAIL_REPLY_TO_NAME` и прокинут во все адаптеры:
  SMTP (`Reply-To`), Resend (`reply_to`), MailerSend (`reply_to`), SendGrid (`reply_to`), Mailgun (`h:Reply-To`),
  Postmark (`ReplyTo`), Unisender (`reply_to`). В dry-run `.eml` заголовок тоже присутствует.
- Значение по умолчанию в `.env`: `EMAIL_REPLY_TO=valdislav.n+digest@gmail.com`,
  имя «Дайджест Travelata (ответы)» — плюс-алиас Gmail: ответы падают в тот же ящик,
  но их легко отфильтровать правилом по адресу `+digest`.
- Проверка: `.venv/bin/python scripts/send_digest.py --check` → строка `reply-to: ...`.

## Kit (ConvertKit) — интеграция (15.11, 10:05 PST)

Ключ `KIT_API_KEY` (22 символа, API v3) проверен: forms/tags/custom_fields/broadcasts отвечают 200,
аккаунт пустой. Для v4 ключ не подходит (401), нужен отдельный ключ из раздела API Keys.

Скрипты:
- `scripts/kit_client.py --check` — состояние аккаунта (формы, теги, поля, черновики).
- `scripts/kit_sync.py [--dry-run]` — импорт подписчиков из нашего D1-списка в Kit (нужен API Secret).
- `scripts/kit_broadcast.py [--dry-run|--create|--cleanup]` — собрать брендированное письмо и создать
  черновик рассылки в Kit; `--cleanup` удаляет пустые черновики «New Broadcast».

Ограничения, проверенные вживую:
1. **Без подтверждённого send address** Kit отвечает 422 «Please ensure your selected send address is
   confirmed…» — черновик создаётся, но тема/контент не применяются (получается «New Broadcast»).
   Нужно: Kit → Settings → Email → подтвердить адрес (письмо приходит на valdislav.n@gmail.com).
2. **API v3 не умеет отправлять broadcast** (POST /broadcasts/{id}/send → 404): только создать черновик,
   отправка — кнопкой в интерфейсе Kit.
3. **Подписчики/кастомные поля требуют API Secret** (пока в `.env` пусто).

Тест: `kit_broadcast.py --create` создал черновик id=27068393 (8 KB HTML), пустые черновики удалены.

## Kit: что уже работает (15.11, 10:10 PST)

Аккаунт: plan `creator` (14-дневный триал), send address `nonamemac@icloud.com`.

Создано через API:
- теги: **Дайджест** (id 25918468, RU), **Digest EN** (id 25918477)
- кастомные поля: **Язык** (id 1433138), **Source** (id 1433152)
- подписчик `valdislav.n@gmail.com` → subscriber id 4389188720 (через `POST /v3/tags/{id}/subscribe`)
- две **запланированные** брендированные рассылки (send_at работает!):
  - RU «Куда поехать в декабре…» id 27068499 → 2026-11-16T17:00Z (09:00 PST)
  - EN «Where to go in December…» id 27068583 → 2026-11-16T18:00Z (10:00 PST)
  - контент 8.5 KB (наш `brand_email.build`), тема применилась корректно

Ограничения v3 API (проверено):
- отправки через API нет (`POST /broadcasts/{id}/send` → 404), но **расписание через `send_at` работает** — Kit отправит сам;
- формы и sequences создавать нельзя (только читать); webhooks в v3 нет (404) — для них нужен v4-ключ;
- создание подписчика `POST /v3/subscribers` → 404; рабочий путь — тег-подписка.

Блокер: send address `nonamemac@icloud.com` должен быть подтверждён в Kit (Settings → Email),
иначе отправка в 17:00Z не пройдёт. Альтернатива — сменить send address на `valdislav.n@gmail.com` в UI.

## Kit API v4 + MCP + вебхуки (15.11, 10:20 PST)

**MCP:** `app.kit.com/mcp` — это Kit MCP, работает через OAuth от имени владельца аккаунта: headless-подключение
невозможно без интерактивного логина в браузере. Публичный `https://developers.kit.com/mcp` (Docs MCP) подключён
скриптом `scripts/kit_docs_mcp.py` — через него вытаскиваем актуальные контракты v4 (broadcasts, webhooks, subscribers).

**v4-ключ заработал** (`KIT_V4_API_KEY`): account, subscribers, tags, forms, custom_fields, webhook_endpoints — 200.

Сделано через v4:
- `POST /v4/subscribers` (upsert) + кастомные поля: подписчику `valdislav.n@gmail.com` проставлены
  `language=ru`, `source=manual-lead`; поле `Language` (key `language`) создано через `POST /v4/custom_fields`.
- `POST /v4/webhook_endpoints` → id 4100, url `https://links-tracker.valdislav-n.workers.dev/kit/webhook`,
  события: created, activated, unsubscribed, subscribed_to_form, bounced, complained, tag_added, broadcast.sent.
  Секрет возвращён один раз → сохранён в `.env` и в секрет воркера.
- Воркер принимает вебхуки: проверка `X-Kit-Signature` (HMAC-SHA256 от `t.body`), пишет в D1 `kit_events`,
  синхронизирует `subscribers` (created/activated → в список, unsubscribed/bounced/complained → флаг 1).
  Проверено: подпись принята (200), поддельная — 401.
- Две запланированные рассылки теперь таргетированы по тегам: RU id 27068499 → тег «Дайджест» (25918468),
  EN id 27068583 → тег «Digest EN» (25918477).

**Блокер отправки:** send address `nonamemac@icloud.com` не подтверждён в Kit — без этого Kit не отправит
запланированные на 16.11 письма. Подтвердить: Kit → Settings → Email (или сменить на `valdislav.n@gmail.com`).
