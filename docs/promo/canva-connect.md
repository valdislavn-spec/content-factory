# Canva Connect — статус подключения (09.11.2026)

- Аккаунт: Canva `Vlad MMoney` (valdislav.n@gmail.com), вход через Google/Facebook SSO.
- Приложение создано в Canva Developer: **«Content Factory Pins»**, App ID `AAHOGG1JxWE`,
  Distribution: Public (review требуется для публичного релиза), Version 1 (draft).
- Developer portal: https://www.canva.com/developers/apps
- Документация Connect API: https://www.canva.dev/docs/connect/

## Блокер
Canva не включает REST API (Outside Canva → Start integrating), пока на аккаунте нет
**пароля + MFA**:
> «To use REST APIs and integrate Canva into an external platform, turn on MFA…
> To set up MFA, first make sure your account has a password.»

Аккаунт создан через SSO, пароль не задан. Чтобы задать пароль, Canva требует выйти и
пройти сброс пароля по email (valdislav.n@gmail.com), затем включить MFA (authenticator).

## План после MFA
1. Outside Canva → Start integrating → создать auth client (client_id + secret).
2. Redirect URI: `http://127.0.0.1:8085/callback` (или https-домен), scopes:
   `design:meta:read design:content:read design:content:write asset:read asset:write
   brandtemplate:meta:read brandtemplate:content:read`.
3. OAuth PKCE: `https://www.canva.com/api/oauth/authorize` → token
   `https://api.canva.com/rest/v1/oauth/token`.
4. Скрипт `scripts/canva_connect.py` (создать): users/me, designs list, export PNG, upload asset.
5. Экспорт пинов из Canva-шаблонов → загрузка в Pinterest/Benable.

## Альтернативы, если Canva не подойдёт
- Pexels/Unsplash API — реальные фото для пинов (free).
- Hugging Face (ключ уже в .env) — AI-фоны для пинов.
- Собственный рендер HTML→PNG через headless Chrome — без внешних сервисов.
