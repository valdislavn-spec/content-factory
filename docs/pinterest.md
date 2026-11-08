# Pinterest: подключение и постинг

Публикатор в заводе уже есть: `content_factory/publishers/pinterest.py` (API v5,
`POST /v5/pins`). Пин = картинка + заголовок + описание (до 500 символов) + ссылка.
Нужен **публичный HTTPS-URL картинки**.

## Что нужно от владельца аккаунта

1. **Приложение в Pinterest Developers**
   - <https://developers.pinterest.com/> → *Create app* (название, описание).
   - Configure → scopes: **`boards:read`, `pins:read`, `pins:write`**.
2. **Access token**
   - В приложении: *Configure → Access tokens → Generate token* (тестовый
     стандартный токен, живёт ограниченное время), либо полноценный OAuth2-flow
     с refresh token.
   - Токен одноразово показывается в кабинете — скопировать.
3. **Board id**
   - Открыть нужную доску в Pinterest, посмотреть её ID можно через API:
     `GET /v5/boards` (это делает `scripts/pinterest_check.py`).
4. **Картинки**
   - Брендовые обложки уже лежат в `docs/assets/pinterest/<channel>.png` и
     публикуются на GitHub Pages:
     `https://valdislavn-spec.github.io/content-factory/assets/pinterest/<channel>.png`
   - Для своего креатива — просто положить файл в эту папку.

## Что сохранить в GitHub

Secrets (Settings → Secrets and variables → Actions):

| Secret | Значение |
|---|---|
| `PINTEREST_ACCESS_TOKEN` | токен из кабинета разработчика |
| `PINTEREST_BOARD_ID` | id доски, куда постить |

Variables:

| Variable | Значение |
|---|---|
| `PINTEREST_IMAGE_URL_CRYPTO_NEWS` (и `_AI_NEWS`, `_SPORT_NEWS`, `_CRYPTO_ES`, `_TECH_AI_ES`, `_FUTBOL_ES`) | HTTPS-URL обложки канала |
| `PINTEREST_LINK` | куда вести пин (например, `https://t.me/HOOPY0007`) |

Для отдельного канала можно задать
`PINTEREST_ACCESS_TOKEN_<CHANNEL_ID>` / `PINTEREST_BOARD_ID_<CHANNEL_ID>` —
паблишер поддерживает суффикс канала.

## Проверка

Actions → **pinterest-check** → Run workflow:

1. `post=false` — покажет доски и проверит токен;
2. `post=true` — создаст один тестовый пин на доску.

## Включение в конвейер

После проверки добавить `pinterest` в `publisher_ids` нужного канала в
`config/channels.en.yaml` / `channels.es.yaml`, например:

```yaml
  publisher_ids: [telegram, bluesky, mastodon, discord, pinterest]
```

Важно: тогда пин будет создаваться **на каждый** опубликованный пост. Если это
слишком часто — либо включать Pinterest только для канала с редким расписанием,
либо использовать ручной постинг через `pinterest-check` (2–4 пина в день
достаточно; больше Pinterest считает спамом).

## Ограничения

- Pinterest API требует OAuth-токен: без него постинг невозможен (поэтому
  «просто URL business hub» не подключает API).
- Токен со временем истекает (стандартный — ограниченный срок); храните дату
  выдачи и обновляйте через кабинет или OAuth refresh.
- Картинка должна быть доступна по HTTPS без авторизации (GitHub Pages подходит).
- Описание до 500 символов — длинные посты режутся автоматически.

## Ссылки для формы Pinterest (app creation)

| Поле формы | Что вставить |
|---|---|
| Website or app link | `https://valdislavn-spec.github.io/content-factory/` |
| Privacy policy URL | `https://valdislavn-spec.github.io/content-factory/privacy.html` |
| Terms (если спросят) | `https://valdislavn-spec.github.io/content-factory/terms.html` |

Политика и Terms лежат в `docs/privacy.html` и `docs/terms.html` и публикуются на
GitHub Pages вместе с хабом. Ссылка на пин по умолчанию — хаб
(`PINTEREST_LINK`), при желании для канала можно поставить ссылку на его
Telegram-канал.

## Ошибки Pinterest API и режимы

| Ответ API | Значение | Что делать |
|---|---|---|
| `401 code 3 "Your application consumer type is not supported"` | приложение **не одобрено для Trial** или используется Production-limited токен без доступа | дождаться аппрува Trial access; после одобрения сгенерировать Production token |
| `401 code 2 "Authentication failed"` на `api-sandbox.pinterest.com` | токен **не sandbox** | сгенерировать Sandbox-токен |
| `401` на `api.pinterest.com` с sandbox-токеном | токен не от того окружения | использовать `PINTEREST_API_BASE` под окружение |

### Sandbox vs Production

- **Sandbox** (`https://api-sandbox.pinterest.com/v5`) — тестовые пины/доски,
  не видны публично, работают сразу после создания приложения (если выдан
  Sandbox token). Удобно проверить пайплайн до аппрува.
- **Production** (`https://api.pinterest.com/v5`) — реальные публичные пины;
  нужен одобренный Trial/Standard доступ.

В приложении (Configure / Access tokens) при генерации токена выберите
окружение: **Sandbox** или **Production limited**. Токен `pina_…` —
production-limited, поэтому против sandbox он даёт `code 2`, а против
production — `code 3` до одобрения.

`PINTEREST_API_BASE` (Repository variable) переключает базу API в паблишере и
скриптах.
