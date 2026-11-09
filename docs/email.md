# Email-рассылки: бесплатные варианты + наш дайджест

## 1. Что бесплатного есть на GitHub

| Проект | Что это | Лицензия | Плюсы |
|---|---|---|---|
| [listmonk](https://github.com/knadh/listmonk) | self-hosted newsletter/mailing-list менеджер (Go + Postgres, один бинарник) | AGPL | подписчики, шаблоны, API, кампании; бесплатно навсегда |
| [Mailtrain](https://github.com/mailtrain-org/mailtrain) | newsletter-платформа (Node + MySQL) | GPL | сегменты, CSV-импорт, шаблоны |
| [Keila](https://github.com/pentacent/keila) | open-source newsletter (Elixir) | AGPL | визуальный редактор, self-host или облако |
| [Plunk](https://github.com/useplunk/plunk) | open-source email-платформа (SES) | AGPL | транзакционные письма + кампании, API |
| [Mautic](https://github.com/mautic/mautic) | marketing automation | GPL | воронки, сегменты, автоматизация |
| [Postal](https://github.com/postalserver/postal) / [Cuttlefish](https://github.com/mhfs/cuttlefish) | self-hosted MTA для рассылок | MIT/GPL | свой SMTP-сервер |
| [docker-mailserver](https://github.com/docker-mailserver/docker-mailserver) | почтовый сервер в Docker | MIT | если нужен свой домен/ящики |
| [Mailpit](https://github.com/axllent/mailpit) / [MailHog](https://github.com/mailhog/MailHog) | тестовый SMTP для разработки | MIT | проверять письма локально |

**Рекомендация:** для начала — наш дайджест через бесплатный SMTP; для роста
базы подписчиков — **Listmonk** (лёгкий, не требует платных сервисов).

## 2. Бесплатные SMTP/API-провайдеры (отправка)

| Провайдер | Бесплатный лимит | SMTP-хост |
|---|---|---|
| Gmail | ~500 писем/день (`App Password`) | `smtp.gmail.com:587` |
| Brevo | 300 писем/день | `smtp-relay.brevo.com:587` |
| Mailjet | 200 писем/день | `in-v3.mailjet.com:587` |
| Resend | 100 писем/день (3000/мес) | API/SMTP |
| SendGrid | 100 писем/день | `smtp.sendgrid.net:587` |

Для своего домена нужны SPF/DKIM (иначе спам). Для Gmail — только App Password,
не основной пароль; лимиты и ToS Google учитывать.

## 3. Наш дайджест (готово)

`scripts/email_digest.py` собирает письмо из постов в SQLite (HTML + plain text)
и отправляет через SMTP. Без внешних зависимостей.

```bash
# dry-run: .eml в data/outbox/email/ (ничего не отправляет)
EMAIL_FROM=you@gmail.com python scripts/email_digest.py --to you@gmail.com --days 7

# отправка (Gmail/Brevo/Mailjet)
EMAIL_SMTP_HOST=smtp.gmail.com EMAIL_SMTP_USER=you@gmail.com \
EMAIL_SMTP_PASSWORD=app-password EMAIL_FROM=you@gmail.com \
python scripts/email_digest.py --send --to subscribers@example.com --days 7
```

Env:

```env
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USER=you@gmail.com
EMAIL_SMTP_PASSWORD=app-password
EMAIL_FROM=you@gmail.com
EMAIL_TO=subscriber1@example.com,subscriber2@example.com
EMAIL_SUBJECT_PREFIX=
```

Автоматизация: `.github/workflows/email-digest.yml` — еженедельный дайджест
(понедельник 08:17 UTC). Если SMTP-секреты не заданы — workflow делает dry-run
и загружает `.eml` артефактом.

## 4. Юридическое и анти-спам

- отправляйте только тем, кто **сам подписался** (double opt-in);
- в письме должна быть отписка (в шаблоне есть заглушка — замените на ссылку);
- не покупайте базы email — домен быстро заблокируют;
- GDPR/CAN-SPAM: храните согласие, дату подписки и умеете удалять данные.

## 5. Что можно добавить

- таблица подписчиков в SQLite + double opt-in (Listmonk-совместимый API);
- еженедельная автоматическая отправка через Listmonk вместо SMTP;
- персональные дайджесты «только AI» / «только Crypto»;
- отслеживание открытий (пиксель) и кликов — аккуратно, без трекинга без согласия.
