# Email-дайджест: что готово и как включить за 10 минут

**Дата: 08.11.2026.** Еженедельное письмо (EN/ES) с лучшими постами каналов.
Подписка — через форму на GitHub Pages, отправка — через Brevo (free: 300 писем/день).
Ничего не отправляется без явного `--send`; регистрация адресов уже работает.

## Что уже готово

| Компонент | Где | Статус |
|---|---|---|
| Форма подписки EN | https://valdislavn-spec.github.io/content-factory/subscribe/ | ✅ live |
| Форма подписки ES | https://valdislavn-spec.github.io/content-factory/subscribe/es/ | ✅ live |
| Приём адресов | Cloudflare Worker `https://cf-subscribe.valdislav-n.workers.dev/` + KV namespace `content-factory-subscribers` | ✅ задеплоено |
| Генератор письма | `content_factory/integrations/email_digest.py`, `scripts/email_digest.py` | ✅ |
| Workflow | `.github/workflows/email-digest.yml` (вторник 14:00 UTC; ручной dry-run) | ✅ |
| Ссылки на форму | футер хаба, гео-лендинги, закрепы каналов | ✅ |

Форма сохраняет `email`, `language`, `topics`, `consent_at` в Cloudflare KV.
Если у Worker заданы Brevo-секреты — контакт сразу дублируется в список Brevo.

## Шаг 1. Brevo (бесплатно)

1. Регистрация: https://www.brevo.com/ (free: 300 писем/день, 9 000/мес).
2. Подтвердите **отправителя и домен**: Sender & Domain → добавьте домен,
   пропишите SPF/DKIM/DMARC в DNS. Без этого письма уходят в спам/блокируются.
3. Создайте два списка: `EN weekly digest`, `ES weekly digest` — запомните их ID
   (Contacts → Lists; ID виден в URL/API).
4. API key: Settings → SMTP & API → API Keys → создайте ключ (`BREVO_API_KEY`).

## Шаг 2. Секреты GitHub

Repo → Settings → Secrets and variables → Actions → New repository secret:

| Секрет | Значение |
|---|---|
| `BREVO_API_KEY` | API-ключ Brevo |
| `BREVO_LIST_ID_EN` | ID списка EN |
| `BREVO_LIST_ID_ES` | ID списка ES |
| `EMAIL_FROM` | подтверждённый email отправителя (например `digest@ваш-домен`) |
| `EMAIL_FROM_NAME` | `Content Factory` (или имя каналов) |

После этого рассылка включится автоматически по расписанию (вторник 14:00 UTC).

## Шаг 3. Секреты Worker (чтобы подписки сразу попадали в Brevo)

Cloudflare Dashboard → Workers & Pages → `cf-subscribe` → Settings → Variables →
добавьте как **Secret**: `BREVO_API_KEY`, `BREVO_LIST_ID_EN`, `BREVO_LIST_ID_ES`.
Переменные добавляются в Worker через API или dashboard; после сохранения форма
начнёт синхронизировать контакты. До этого адреса просто копятся в KV — ничего
не теряется (их можно выгрузить/импортировать в Brevo позже).

## Шаг 4. Проверка

1. Actions → **email-digest** → Run workflow:
   - `language: all`, `send: dry-run`, `smoke_test: true` — проверит форму
     (POST в Worker + удаление тестовой записи) и соберёт письма в артефакт.
2. Проверьте HTML в артефакте `email-digest-<run>`.
3. Повторите с `send: live` — письмо уйдёт в списки Brevo (отправитель должен
   быть подтверждён, списки не пустые).
4. Раз в неделю проверяйте статистику Brevo: открытия, клики, отписки.

## Шаг 5. Double opt-in (важно для доставляемости и закона)

Сейчас форма собирает согласие (`consent_at`) и синхронизирует контакт в Brevo
(одиночный opt-in). Перед публичным продвижением формы включите **double
opt-in**: в Brevo создайте DOI-шаблон подтверждения и включите его для списков
(Settings → Double opt-in), либо переключите форму на Brevo-форму с DOI.
Не добавляйте в рассылку адреса без согласия: это спам (GDPR / CAN-SPAM / 152-ФЗ).

## Шаг 6. Если уже есть база адресов

- CSV с колонками `email, language, topics` → Brevo → Contacts → Import;
  маппинг: `LANGUAGE`, `TOPICS`; список — EN или ES.
- Либо загрузить в KV напрямую (для истории): ключи `sub:<email>` со значением
  `{"email": ..., "language": ..., "consent_at": ...}` через Cloudflare API.

## Эксплуатация

- Расписание: вторник 14:00 UTC (10:00 ET, 08:00 Mexico) — лучшее время для
  US + LatAm. Поменять — в `email-digest.yml` (`cron`).
- Ручной dry-run: Actions → email-digest → `send: dry-run`.
- Письма: 5–6 новостей, 2 на канал, ссылки на Telegram; тема по языку.
- Отписки: Brevo добавляет unsubscribe-ссылку в кампанию (проверьте в шаблоне
  письма перед первым запуском).
- Лимит Brevo 300/день: 1 000 подписчиков × 1 письмо/нед = 4 000/мес — с запасом.

## Ссылки

- Brevo: https://www.brevo.com/pricing/
- Free-тарифы и GitHub-проекты: [email-newsletter-free.md](email-newsletter-free.md)
- Форма EN: https://valdislavn-spec.github.io/content-factory/subscribe/
- Форма ES: https://valdislavn-spec.github.io/content-factory/subscribe/es/
- Worker: https://cf-subscribe.valdislav-n.workers.dev/
  (KV namespace: `content-factory-subscribers`)
