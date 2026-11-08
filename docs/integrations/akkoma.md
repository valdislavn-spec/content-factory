# Akkoma (Fediverse) — аккаунт и автопостинг

## Аккаунт

- **@hoopy0007@nuages.cloud** — https://nuages.cloud/@hoopy0007 (профиль)
- Инстанс: **nuages.cloud** (Akkoma, открытая регистрация без капчи/одобрения).
- E-mail: valdislav.n@gmail.com, display name «Crypto & Blockchain», bio со ссылкой на @HOOPY0007.

Почему не akkoma.social: это сайт проекта, не инстанс. В разделе `#join` он
рекомендует два инстанса:
- **Coral Castle (seafoam.space)** — живой, но регистрация с **капчей и
  ручным одобрением** (аккаунт не создан);
- **My Crowd (mycrowd.ca)** — **закрыт** («instance has been shut down»).

nuages.cloud — общий инстанс с открытой регистрацией (без капчи и approval),
аккаунт создан и подтверждён.

## Доступ для завода

OAuth-приложение `content-factory` (scope `read write follow`), выдан токен.

В `.env` (локально) и в GitHub Secrets репозитория:

```
AKKOMA_BASE_URL=https://nuages.cloud
AKKOMA_TOKEN=<access token>
```

Токен получен через password grant (`POST /oauth/token`), действует долго
(~100 лет); при отзыве — создать новое приложение и повторить grant.

## Публикация

`config/channels.en.yaml` → канал `crypto-news`:

```yaml
publisher_ids: [telegram, bluesky, mastodon, discord, akkoma]
```

Публикатор `AkkomaPublisher` (Mastodon-совместимый API) постит текст поста
(HTML конвертируется), лимит — как у инстанса (5000 символов). В dry-run
(локальный `CONTENT_FACTORY_DRY_RUN=true`) сообщения не отправляются,
пишутся в `data/outbox`.

Проверка:

```bash
python -m content_factory check-publishers   # или через CLI/тесты
```

## Правила и риски

- Инстанс общий/французский (ArmAnDangerous's HQ); в описании: «enregistrement
  ouvert sans verifs». Спам и рейды запрещены — постим аккуратно, 1–3 раза в
  день, без массовых упоминаний.
- Если админ попросит прекратить — аккаунт можно перенести на другой Akkoma
  (Move поддерживается), не теряя подписчиков.
- Ссылка на Telegram в bio; перекрёстные посты без агрессивной рекламы.
