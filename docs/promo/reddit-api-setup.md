# Reddit API: где взять ключи и как включить публикатор

**Дата: 08.11.2026.** Коротко: ссылка на `developers.reddit.com/docs/api/redditapi/...`
— это **Devvit RedditClient**, у него **нет API-ключей**. Для нашего публикатора
нужен **Reddit Data API** (OAuth), а доступ к нему в 2026 выдаётся **после
регистрации приложения и одобрения** (Responsible Builder Policy). Поэтому
«не могу найти» — нормально: в открытом виде ключей больше нет.

## Два разных Reddit API

| | Devvit RedditClient | Reddit Data API |
|---|---|---|
| Что это | API внутри Reddit-приложения (Devvit-платформа) | OAuth API для скриптов/ботов |
| Ключи | не нужны | `client_id` + `client_secret` |
| Куда постить | только сабреддит, куда установлено приложение | сабреддиты, где разрешено аккаунту |
| Наш случай | свой сабреддит (бесплатно, без approval) | `reddit-digest` / `RedditPublisher` |
| Документация | https://developers.reddit.com/docs/ | https://www.reddit.com/dev/api |

Наш код использует второй вариант: [reddit.py](../../content_factory/publishers/reddit.py)
(Script App OAuth, password grant) и [reddit_digest.py](../../scripts/reddit_digest.py).

## Где брать ключи (после одобрения)

1. Войти в Reddit-аккаунт, который будет постить.
2. Открыть **https://www.reddit.com/prefs/apps** (если редиректит на login — сначала войти).
3. Кнопка **«create another app…»**:
   - **name**: `content-factory-digest` (понятное, не `test`);
   - **type**: **script** (для собственного бота);
   - **description**: что делает приложение (см. готовый текст ниже);
   - **about url**: `https://github.com/valdislavn-spec/content-factory`;
   - **redirect uri**: `http://localhost:8080` (обязательное поле, для password grant не используется).
4. Создать. На странице приложения:
   - **client_id** — короткая строка **под названием приложения** (14–22 символа);
   - **secret** — поле с подписью **«secret»**.
5. Эти два значения + логин/пароль аккаунта + сабреддит — в секреты (см. ниже).

Важно: ключи появляются у **script-приложения**, но по политике Reddit доступ
к Data API нужно **зарегистрировать и получить одобрение** — см. следующий раздел.

## Регистрация и одобрение (обязательно в 2026)

Согласно [Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy):
доступ к Reddit data через API требует запроса и явного одобрения.

1. **Developer-профиль/приложение**: https://developers.reddit.com/app-registration
   — зарегистрировать приложение и получить App-метку (App Transparency).
2. **Если use case не покрывается Devvit** (наш бот постит в сабреддиты, а не
   является Devvit-приложением) — тикет:
   https://support.reddithelp.com/hc/en-us/requests/new?ticket_form_id=14868593862164&tf_42139884615700=api_request_type_developer_clone
3. Принять [Data API Terms](https://redditinc.com/policies/data-api-terms).

### Готовый текст заявки (скопировать в тикет)

```
App: content-factory-digest (script app, OAuth password grant)
Use case: non-commercial news digest bot for our own Telegram news channels.
Access requested: write (submit self-posts), read (own account + subreddit rules).
Subreddits: only subreddits we own or moderate, e.g. r/<our_subreddit>.
Frequency: up to 2-3 self-posts per day, unique titles/body per post.
Data storage: we do not store Reddit content; we only read our own account info
and the rules of the target subreddit to verify permissions.
No AI training, no resale, no scraping, no cross-subreddit spam.
Compliance: Data API Terms, Reddit Rules, subreddit rules; per-client rate limit
100 requests/min respected; descriptive User-Agent on every request.
```

Если попросят уточнить: бот публикует **свои** дайджесты новостей (крипта/ИИ/
спорт) в **свой** сабреддит, не голосует, не комментирует, не рассылает ЛС,
не собирает данные пользователей.

## Секреты GitHub

Settings → Secrets and variables → Actions:

| Секрет | Откуда |
|---|---|
| `REDDIT_CLIENT_ID` | под названием script-приложения на prefs/apps |
| `REDDIT_CLIENT_SECRET` | поле «secret» |
| `REDDIT_USERNAME` | логин аккаунта-владельца (без `u/`) |
| `REDDIT_PASSWORD` | пароль аккаунта |
| `REDDIT_SUBREDDIT` | сабреддит без `r/`, например `USCryptoFeed` |

Локально — те же имена в `.env` (файл не коммитить).

**2FA:** password grant не работает, если на аккаунте включена двухфакторка.
Варианты: отдельный бот-аккаунт без 2FA либо OAuth refresh-token flow
(сложнее, тогда пароль не нужен).

## Проверка и запуск

1. Actions → **reddit-check** → Run workflow. Скрипт
   [reddit_check.py](../../scripts/reddit_check.py) проверит:
   токен, `/api/v1/me` (карма/возраст), сабреддит, правила, rate-limit.
2. Если ок — Actions → **reddit-digest** → Run workflow, `live: true`
   (первый раз можно `live: false` — покажет текст без публикации).
3. Дальше — по расписанию 13:00/22:00 UTC, лимит 3 поста/день.

## Ограничения и правила

- **100 запросов/мин** на client_id; токен живёт 1 час (код обновляет токен сам).
- Обязателен описательный **User-Agent** вида `script:app:1.0 (by /u/username)`.
- Нельзя спамить/дублировать контент по сабреддитам — это прямо запрещено
  политикой и ведёт к бану приложения/аккаунта.
- Новый аккаунт с низкой кармой часто блокируется сабреддитами
  («You're doing that too much») — нужен аккаунт с историей.
- Соблюдать правила сабреддита: где self-promo запрещён — не постить.

## Если approval не дают / не хочется ждать

- **Devvit-приложение в своём сабреддите**: без ключей и approval, но только
  там, куда установлено; чужие сабреддиты недоступны.
- Ручной постинг/официальная реклама Reddit (Ads API) — платно.
- Не обходить ограничения скрейпингом/мультиаккаунтами: Reddit за это банит.

## Ссылки

- Создать script app: https://www.reddit.com/prefs/apps
- Регистрация приложения: https://developers.reddit.com/app-registration
- Responsible Builder Policy: https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy
- Data API Terms: https://redditinc.com/policies/data-api-terms
- Тикет на доступ: https://support.reddithelp.com/hc/en-us/requests/new?ticket_form_id=14868593862164&tf_42139884615700=api_request_type_developer_clone
- Devvit docs (RedditClient): https://developers.reddit.com/docs/
- API reference: https://www.reddit.com/dev/api
