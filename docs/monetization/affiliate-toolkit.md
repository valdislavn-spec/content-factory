# Affiliate-маркетинг: инструменты (GitHub + сервисы), 08.11.2026

Что искали: трекинг партнёрских ссылок/кликов, self-hosted сервисы, боты и API
для монетизации Telegram-каналов. Ниже — только то, что реально применимо к нам.

## GitHub — что стоит забрать

| Репозиторий | Стек | Что даёт | Вердикт |
|---|---|---|---|
| [berlonak/BingX_CRM](https://github.com/berlonak/BingX_CRM) | Python, SQLite | Read-only Telegram-бот для **BingX-аффилиатов**: тянет через BingX Agent API объёмы рефералов, комиссии и депозиты, рейтинги, алерты, ежедневные отчёты, CSV | ⭐ **забрать после одобрения** Affiliate Program — это наш случай 1:1 |
| [botnick/shortlink](https://github.com/botnick/shortlink) | TS, Cloudflare Workers + D1 | Self-hosted сокращатель ссылок: клик-аналитика, брендированные ссылки, REST API + MCP, бесплатно на free-плане CF | ⭐ **забрать** — трекинг партнёрских ссылок под нашим воркером, вместо TinyURL без статистики |
| [muleiwu/dwz-server](https://github.com/muleiwu/dwz-server) | Go (134★) | Короткие ссылки + маркетинг-атрибуция, A/B, мультидомены | альтернатива, если нужен свой сервер |
| [sanmaxdev/linkforge](https://github.com/sanmaxdev/linkforge) | PHP/Laravel | Short links + QR + аналитика | избыточно, есть CF-вариант |
| [ZAK123DSFDF/refearnapp](https://github.com/ZAK123DSFDF/refearnapp), [thebigasif/affiliate-tracking](https://github.com/thebigasif/affiliate-tracking) | Next.js/Go | Полные affiliate-программы (Stripe/Shopify, выплаты партнёрам) | ❌ не наш кейс: мы издатель, а не магазин с партнёркой |
| [izzipizzy/slimtds](https://github.com/izzipizzy/slimtds) | PHP | TDS/распределение трафика, S2S postbacks | ❌ оверкилл |
| n8n-репозитории с affiliate-воркфлоу | n8n | Автоматизация контента/офферов | ⏳ можно, но у нас свой Python-пайплайн |

## Сервисы (не GitHub) — где реально брать деньги/клики

### 1. Сети и программы с API (автоматизация ссылок/статистики)

| Сервис | Что даёт | Статус у нас |
|---|---|---|
| **MyLead** | CPA-офферы + API/postback | ✅ аккаунт есть, реф-ссылка `mylead.global/r/dJ67Qo` |
| **Admitad** | CPA-сеть + API traffic | ✅ аккаунт есть (вход через VPN) |
| **Travelpayouts** | 100+ брендов + [API партнёрских ссылок](https://support.travelpayouts.com/hc/en-us/articles/25289759198226-API-for-Travelpayouts-partner-links) и [статистики](https://support.travelpayouts.com/hc/en-us/articles/360019864079-API-of-affiliate-programs-booking-statistics) | ⏳ аккаунт есть, вход сложный |
| **KMA / N1 / LeadBit / CPA.house / Shakes** | CPA-сети (крипто/гемблинг/nutra) | ⏳ частично, по гео |
| **Telega.io / Collaborator.pro / Tagio** | Биржи рекламы в TG-каналах | ⏳ регистрация вручную |
| **BingX Affiliate** | RevShare до 50% | ⏳ заявка отправлена, ждём ≤5 раб. дней |

### 2. Трекинг ссылок и кликов

- **Cloudflare Workers** (у нас уже есть аккаунт/воркеры) — свой сокращатель с клик-статистикой (по мотивам `botnick/shortlink`), бесплатно.
- **Dub.co** — open-source link management, free tier, аналитика кликов.
- **Shlink** — self-hosted на своём сервере (Docker).
- **TinyURL** — уже в коде (`shortlink.py`), но **без статистики** — только косметика.
- **Umami / Plausible / Cloudflare Web Analytics** — если появятся лендинги.

### 3. Аналитика каналов

- **TGStat / Telemetr** — уже используем; смотрим подписчиков, просмотры, ER.
- Telegram Bot API — deep links `/start?start=...` (в базе уже есть growth-события).

## Рекомендуемый стек под нас

1. **Shortlink-worker на Cloudflare** (по образцу `botnick/shortlink`, но проще):
   `GET /r/{code}` → 302 на партнёрскую ссылку + запись клика (канал, дата, UA hash)
   `GET /stats` → клики по каналу/ссылке.
   Заменяем TinyURL для партнёрских ссылок; в постах/алертах — короткая ссылка
   вида `https://links.<наш-домен>/r/bingx-news` (или workers.dev).
2. **BingX_CRM** — как только Affiliate одобрят и появится Agent API key:
   бот сам присылает комиссии/депозиты/лидеров, CSV.
3. **MyLead API** — генерировать оффер-ссылки и тянуть статистику в наш пайплайн
   (вместо ручного копирования).
4. **Travelpayouts links API** — если запустим travel-контент (пока нет).

## Что НЕ берём

- Полные affiliate-платформы (refearnapp/affiliate-tracking): мы не продаём SaaS
  с партнёркой, нам не нужны выплаты/Stripe.
- TDS/slimtds: распределение трафика — не наш профиль (не арбитраж).
- Telegram referral-боты с накрутками — риск бана, нет ценности.

## Следующие шаги

- [x] Развернуть shortlink-worker на Cloudflare (KV/D1 + `/r/` + `/stats`) — `links-tracker.valdislav-n.workers.dev`, см. `link-tracker.md`.
- [x] Подключить трекаемые ссылки в партнёрские строки постов/алертов (`tracked_url` в конфиге).
- [ ] После одобрения BingX: развернуть `BingX_CRM`, получить Agent API key, включить daily-отчёты в Telegram.
- [ ] Добавить MyLead API-клиент (ссылки/статистика) в интеграции.
