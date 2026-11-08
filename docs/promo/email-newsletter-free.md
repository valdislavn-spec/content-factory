# Бесплатные email-рассылки: GitHub-проекты, free-тарифы и где брать адреса

**Проверено: 08.11.2026.** Цель — собирать email-подписчиков и отправлять
дайджесты постов каналов **бесплатно** (EN/ES аудитория, оператор в РФ).
Лимиты бесплатных тарифов меняются — перед запуском сверяйтесь по ссылкам.

Готовый запуск для этого репозитория (форма + Brevo + workflow):
[email-digest-setup.md](email-digest-setup.md).

Коротко: **быстро** — Beehiiv/Substack (0 ₽, без кода); **через API из GitHub
Actions** — Brevo/Resend/Mailgun (0 ₽, лимиты 100–300 писем/день);
**полный контроль** — Listmonk на Oracle Always Free + бесплатный SMTP-релей.

## 1. GitHub-проекты для self-host (бесплатно)

| Проект | Что даёт | Лицензия | ★ | Обновлён | Адрес |
|---|---|---|---:|---|---|
| **Listmonk** | рассылки/списки/сегменты/шаблоны/статистика, публичная форма подписки, REST API; один бинарник + PostgreSQL | AGPL-3.0 | 24.2k | 2026-11-07 | https://github.com/knadh/listmonk |
| **Ghost** | блог + встроенные members и email-рассылки; self-host бесплатно (Ghost Pro — платно) | MIT | 55.7k | 2026-11-08 | https://github.com/TryGhost/Ghost |
| **Keila** | лёгкий self-hosted newsletter (Rust), кампании, списки, шаблоны | AGPL-3.0 | 2.3k | 2026-11-04 | https://github.com/pentacent/keila |
| **Plunk** | open-source email-платформа (кампании + транзакционные), self-host | AGPL-3.0 | 5.6k | 2026-11-07 | https://github.com/useplunk/plunk |
| **Mautic** | marketing automation: формы, сегменты, кампании, трекинг | OSL-3.0 | 11.0k | 2026-11-08 | https://github.com/mautic/mautic |
| **Mailtrain** | классический self-host newsletter (Node.js) | GPL-3.0 | 5.8k | 2025-10-05 | https://github.com/Mailtrain-org/mailtrain |
| **Postal** | полноценный mail-сервер для домена (отправка/приём, DKIM/SPF) | MIT | 17.0k | 2026-11-04 | https://github.com/postalserver/postal |
| **Mailpit** | тестовый SMTP-сервер для разработки (проверка писем, не для отправки) | MIT | 10.9k | 2026-11-07 | https://github.com/axllent/mailpit |

**Практический вывод:** для «просто рассылка» — **Listmonk** (лучший баланс:
простой деплой, API, статистика). Для блога+рассылки — **Ghost**. Mautic/Postal/
mailcow — если нужен полноценный маркетинг/почтовый сервер, это сложнее.

## 2. Бесплатные облачные тарифы (SaaS/API)

| Сервис | Бесплатно | Ограничения | Адрес |
|---|---|---|---|
| **Brevo** | 300 писем/день (~9 000/мес), API + SMTP | брендинг Brevo в письмах; домен/отправитель надо подтвердить | https://www.brevo.com/pricing/ |
| **Resend** | 3 000 писем/мес (100/день) | без своего домена — отправка только на свой адрес (`onboarding@resend.dev`) | https://resend.com/pricing |
| **Mailgun** | 100 сообщений/день | 1 домен, 1 день хранения логов | https://www.mailgun.com/pricing/ |
| **SendPulse** | 500 подписчиков, 15 000 писем/мес | брендинг; лимиты по функциям | https://sendpulse.com/pricing |
| **MailerLite** | 250 подписчиков, 2 500 писем/мес | с 16.06.2026 лимиты урезаны (было 500/12 000) | https://www.mailerlite.com/pricing |
| **Beehiiv** | 2 500 подписчиков, отправки без лимита | брендинг Beehiiv; часть функций платно | https://www.beehiiv.com/pricing |
| **Buttondown** | 100 подписчиков | только базовые функции | https://buttondown.com/pricing |
| **Substack** | подписчики без лимита, публикация бесплатно | 10% с платных подписок + сборы Stripe | https://support.substack.com/hc/en-us/articles/360037607131-How-much-does-Substack-cost |
| **Mailchimp** | ориентир ~500 контактов/1 000 писем в мес | тарифы часто меняются — проверяйте | https://mailchimp.com/pricing/ |
| **Kit (ConvertKit)** | free-план (до 10k подписчиков, broadcasts) | часть функций платно — проверьте текущие условия | https://kit.com/pricing |
| **SendGrid** | ориентир 100 писем/день | проверяйте актуальный free-план | https://sendgrid.com/pricing |
| **Cloudflare Email Routing** | приём почты на свой домен бесплатно | это только приём/пересылка, не рассылка | https://developers.cloudflare.com/email-routing/ |

**Выбор для EN/ES-дайджеста (1 000 подписчиков, 1 письмо/нед):**
Brevo (300/день) — с запасом; Resend (3 000/мес) — впритык; Mailgun — для
небольших кампаний. Для старта без кода — Beehiiv/Substack.

## 3. Где брать адреса подписчиков (легально)

| Канал | Бесплатный инструмент | Лимит | Адрес |
|---|---|---|---|
| Форма на лендинге | **Formspree** | 50 отправок/мес | https://formspree.io/plans |
| Форма на лендинге | **Google Forms** | бесплатно | https://docs.google.com/forms/ |
| Форма на лендинге | **Tally** | бесплатный план (с брендингом) | https://tally.so/pricing |
| Своя форма + БД | **Cloudflare Workers + D1** | free-лимиты Workers/D1 | https://developers.cloudflare.com/d1/ |
| Встроенная форма | Beehiiv / Substack / Buttondown / MailerLite | по free-плану | ссылки в таблице выше |
| Telegram | закреп/пост со ссылкой на форму; бот принимает email в диалоге | Bot API бесплатно | https://core.telegram.org/bots/api |
| Лид-магнит | PDF-дайджест/гайд в обмен на email (через форму) | — | — |

**Правила (обязательно):**
- **Double opt-in**: после формы — письмо «подтвердите подписку»; только потом
  добавлять в рассылку.
- В каждом письме — ссылка **unsubscribe** и физический адрес/контакт.
- Никаких купленных, спарсенных баз и рассылок людям, не давшим согласие:
  это спам, бан домена и нарушения GDPR / CAN-SPAM / 152-ФЗ.
- Собирайте минимум данных: email + язык + канал(ы) + источник + дата согласия.

## 4. Три рабочих сценария

### A. Быстро: Beehiiv или Substack (30 минут, 0 ₽, без кода)

1. Создать publication в Beehiiv (free до 2 500 подписчиков) или Substack
   (бесплатно, 10% только с платных).
2. Вставить embed-форму подписки в хаб `docs/index.html` и в закреп Telegram.
3. Раз в неделю публиковать дайджест их редактором (или через их API — у
   Beehiiv есть API, у Substack — нет).
4. Минусы: платформа и брендинг чужие, данных для своей БД нет.

### B. Гибрид 0 ₽: своя форма → Brevo API → GitHub Actions

Схема: форма (Formspree/Cloudflare Worker) → хранилище (Google Sheet/D1/БД) →
GitHub Actions по cron собирает дайджест из БД `content-factory` и отправляет
через Brevo API. Всё в бесплатных лимитах: 1 000 подписчиков × 1 письмо/нед =
4 000 писем/мес при лимите Brevo ~9 000/мес.

Шаги:
1. Brevo: регистрация → **подтвердить домен/отправителя** (SPF/DKIM в DNS) →
   создать API key.
2. Форма: подключить Formspree/Tally/Worker; сохранять `email`, `lang`,
   `source`, `consent_at`, `status=pending`.
3. Double opt-in: письмо с токеном → `status=active`.
4. GitHub Actions workflow (`email-digest.yml`): cron weekly → Python-скрипт
   читает посты за 7 дней из SQLite → HTML-письмо → POST Brevo
   `https://api.brevo.com/v3/smtp/email` (заголовок `api-key`).
5. Секреты: `BREVO_API_KEY`, `FROM_EMAIL`, `FROM_NAME`; dry-run по умолчанию.
6. Метрики: ссылки в письме ведут на `t.me` (UTM не работают) — считать
   подписки/переходы по дельте подписчиков и открытиям Brevo.

### C. Полный контроль: Listmonk на Oracle Always Free

1. Oracle Cloud Always Free (ARM 4 OCPU / 24 ГБ) — см. `free-cloud.md`.
2. PostgreSQL + Listmonk (бинарник), systemd, бэкап БД.
3. SMTP-релей: Brevo (300/день) или Mailgun (100/день) — Listmonk отправляет
   через их SMTP, чтобы не поднимать свой почтовый сервер и не греть IP.
4. DNS: SPF, DKIM, DMARC на своём домене (обязательно для доставляемости).
5. Публичная страница подписки Listmonk (или своя форма → Listmonk API).
6. Кампании: шаблон письма → отправка по списку; статистика открытий/кликов в
   админке. Интеграция с заводом — REST API Listmonk
   (`/api/campaigns`, `/api/subscribers`) можно дёргать из GitHub Actions.

## 5. Интеграция с content-factory (план)

1. Таблица `subscribers` (email, language, channels, status, source,
   consent_at, unsubscribed_at) в `content_factory/storage.py`.
2. `scripts/email_digest.py`: посты за 7 дней по языку → HTML + plain-text
   (заголовок, 3–5 пунктов, ссылки на каналы, unsubscribe).
3. `.github/workflows/email-digest.yml`: cron 1 раз/нед, `workflow_dispatch`
   с `dry_run`, секреты Brevo; после отправки — лог и метрики.
4. Форма подписки: `/subscribe.html` на GitHub Pages → Cloudflare Worker → D1
   (или Listmonk public page) + double opt-in.
5. Лендинги каналов (`docs/channels/`) уже есть — добавить на них блок
   «Дайджест на email».

## 6. Красные флаги

- Покупка/парсинг email-баз, рассылка без согласия → спам-жалобы, бан домена,
  штрафы (GDPR, 152-ФЗ).
- Отправка «на 1 000 адресов» с Gmail/бесплатной почты → блокировка аккаунта.
- Свой SMTP без прогрева домена и DKIM/SPF → письма в спам.
- Free-тарифы: у Resend без домена — только свой адрес; у Brevo брендинг;
  лимиты в день/мес легко превысить при росте списка.
- Персональные данные: хранить только email + согласие; удаление по запросу.

## 7. Сводка адресов

- GitHub: [Listmonk](https://github.com/knadh/listmonk) ·
  [Ghost](https://github.com/TryGhost/Ghost) ·
  [Keila](https://github.com/pentacent/keila) ·
  [Plunk](https://github.com/useplunk/plunk) ·
  [Mautic](https://github.com/mautic/mautic) ·
  [Mailtrain](https://github.com/Mailtrain-org/mailtrain) ·
  [Postal](https://github.com/postalserver/postal) ·
  [Mailpit](https://github.com/axllent/mailpit)
- Free-тарифы: [Brevo](https://www.brevo.com/pricing/) ·
  [Resend](https://resend.com/pricing) ·
  [Mailgun](https://www.mailgun.com/pricing/) ·
  [SendPulse](https://sendpulse.com/pricing) ·
  [MailerLite](https://www.mailerlite.com/pricing) ·
  [Beehiiv](https://www.beehiiv.com/pricing) ·
  [Buttondown](https://buttondown.com/pricing) ·
  [Substack](https://support.substack.com/hc/en-us/articles/360037607131-How-much-does-Substack-cost) ·
  [Mailchimp](https://mailchimp.com/pricing/) ·
  [Kit](https://kit.com/pricing) ·
  [SendGrid](https://sendgrid.com/pricing)
- Формы/адреса: [Formspree](https://formspree.io/plans) ·
  [Google Forms](https://docs.google.com/forms/) ·
  [Tally](https://tally.so/pricing) ·
  [Cloudflare D1](https://developers.cloudflare.com/d1/) ·
  [Cloudflare Email Routing](https://developers.cloudflare.com/email-routing/)
- Документы проекта: [free-promo-setup.md](free-promo-setup.md) (автопостинг в
  соцсети), [free-promo-apis.md](../free-promo-apis.md) (карта бесплатных API),
  [free-cloud.md](../free-cloud.md) (Oracle Always Free).
