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

## Статус на 09.11.2026 (проверено)

- Приложение **Depseek007** (App ID `1636122`): **Trial access на рассмотрении**,
  App secret недоступен.
- Кнопка **«Создать маркер»** в Configure генерирует токен, но он **read-only**
  (`pins:read`, `boards:read`, `user_accounts:read`, `ads:read`, `catalogs:read`)
  и живёт **24 часа**.
- Любой запрос к `api.pinterest.com/v5` с этим токеном возвращает
  `401 code 3 "Your application consumer type is not supported"` — API
  недоступен до одобрения Trial/Production доступа Pinterest.
- **Рабочий обход без API:** Business Hub → *Массовое создание пинов* →
  CSV. 09.11.2026 так загружены 6 карточек Telegram-каналов в доску
  **Travel ideas** (Pinterest подтвердил: «Файл загружен, создание пинов ~2 часа»).
  CSV лежит в [pinterest-channel-cards.csv](pinterest-channel-cards.csv)
  (колонки: Title, Media URL, Pinterest board, Thumbnail, Description, Link,
  Publish date, Keywords; картинки — `assets/channel-cards/*.png`).

### Чтобы включить API-постинг

1. Дождаться/получить одобрение **Trial access** (или Production) в
   developers.pinterest.com; при отказе — писать в поддержку Pinterest.
2. В приложении добавить scopes **`pins:write`**, **`boards:write`**
   (для создания пинов/досок) и заново сгенерировать токен.
3. Обновить секреты: `PINTEREST_ACCESS_TOKEN`, `PINTEREST_BOARD_ID`
   (ID доски можно взять из `GET /v5/boards` после одобрения).
4. Запустить `channel-cards` с `platforms: pinterest` — пины уйдут через
   API v5.

## Статус на 13.11.2026 (проверено)

- **Trial access одобрен.** `api-sandbox.pinterest.com/v5` с токеном из секрета
  отвечает `200`: `GET /boards` работает, `GET /user_account` отдаёт аккаунт,
  `POST /boards` → `201`, `POST /pins` → `201` (тестовый пин создан в доске
  `Content Factory Test`, id `1105774583449702771`).
- **Production по-прежнему закрыт:** `api.pinterest.com/v5` → `401 code 2
  "Authentication failed"` (токен sandbox-овый; для продакшена нужен отдельный
  токен после Standard access).
- Sandbox-аккаунт отдельный: доски/пины sandbox **не видны** на публичном
  профиле (там 2 доски: `Content Factory Test`, `DSH sandbox test`).
- `pinterest-check` умеет sandbox: добавлен input `api_base` (пусто =
  production, `https://api-sandbox.pinterest.com/v5` = sandbox); переменная
  `PINTEREST_API_BASE` (используется и `pins-generate`) **не менялась**.
- Секрет `PINTEREST_ACCESS_TOKEN` обновлён рабочим sandbox-токеном (13.11.2026).
- **Дальше:** залогиниться в developers.pinterest.com → запросить
  **Standard access** → сгенерировать production-токен со scope `pins:write`,
  `boards:write` → обновить секреты `PINTEREST_ACCESS_TOKEN` и
  `PINTEREST_BOARD_ID` (боевая доска) → `pinterest-check` без `api_base`.
  Кабинет/почта сейчас недоступны из окружения (сессии Chrome слетели из-за
  Keychain), нужен вход владельца.

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

## OAuth-flow (когда приложение одобрено)

Если Product-limited тестовый токен не подходит, можно получить пользовательский
токен через OAuth2:

1. Configure → **Redirect URIs** → добавить `http://localhost:8085/callback`.
2. Запустить:
   ```bash
   python scripts/pinterest_oauth.py --client-id 1636122 --client-secret <APP_SECRET>
   ```
3. Браузер откроет авторизацию Pinterest; после подтверждения скрипт поймает
   redirect на localhost, обменяет код на токен и сохранит `.pinterest-token.json`
   (access + refresh token).

Требуется **App secret** (Configure → App secret) и одобренный доступ приложения.
