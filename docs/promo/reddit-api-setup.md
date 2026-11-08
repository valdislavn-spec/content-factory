# Reddit API: где взять ключи и как включить публикатор

**Дата: 08.11.2026.** Коротко: ссылка на `developers.reddit.com/docs/api/redditapi/...`
— это **Devvit RedditClient**, у него **нет API-ключей**. Для нашего публикатора
нужен **Reddit Data API** (OAuth), а доступ к нему в 2026 выдаётся **после
регистрации приложения и одобрения** (Responsible Builder Policy). Поэтому
«не могу найти» — нормально: в открытом виде ключей больше нет.

> **Статус на 08.11.2026: новые заявки на Reddit Data API больше не принимаются.**
> Приём закрыт **31.10.2026** (анонс Reddit от 30.09.2026). Ключи для новых
> проектов получить нельзя. Существующие approved-приложения должны
> зарегистрироваться на Developer Platform до **12.01.2027**, публичный Data API
> закрывается в **марте 2027**. Единственный официальный путь для новых проектов
> сейчас — **Devvit** (приложение в своём сабреддите, без ключей).

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

## Где находится «create another app» (и почему её может не быть)

Кнопка исторически живёт здесь:

1. Войти в Reddit — **только desktop web** (в мобильном приложении её нет).
2. Открыть **https://www.reddit.com/prefs/apps** — страница «developed applications».
   Fallback: **https://old.reddit.com/prefs/apps** (старый интерфейс, кнопка внизу).
3. Внизу страницы — кнопка **«create another app…»**.

**Важно (2026):** с ноября 2025 self-serve создание приложений закрыто — кнопка
может отсутствовать или редиректить на Responsible Builder Policy, а не открывать
форму. Это не баг и не твоя ошибка: доступ к Reddit Data API теперь только через
**заявку (Data Access Request) с ручным одобрением**. Если форма всё-таки
открылась — заполняй её по шагам ниже; если нет — сразу к разделу
«Регистрация и одобрение».

Если форма открылась:
   - **name**: `content-factory-digest` (понятное, не `test`);
   - **type**: **script** (для собственного бота);
   - **description**: что делает приложение (см. готовый текст ниже);
   - **about url**: `https://github.com/valdislavn-spec/content-factory`;
   - **redirect uri**: `http://localhost:8080` (обязательное поле, для password grant не используется).

После создания на странице приложения:
   - **client_id** — короткая строка **под названием приложения** (14–22 символа);
   - **secret** — поле с подписью **«secret»**.

Эти два значения + логин/пароль аккаунта + сабреддит — в секреты (см. ниже).
Если self-serve закрыт, ключи выдаются/включаются после одобрения заявки.

## Регистрация и одобрение: окно закрыто

Хронология Reddit (анонсы в r/redditdev):

| Дата | Что происходит |
|---|---|
| 11.11.2025 | Responsible Builder Policy: self-service ключи закрыты, только заявки |
| 31.10.2026 | **приём новых заявок на публичный Data API прекращён** |
| 10.11.2026 | апдейт по миграции |
| 12.01.2027 | у незарегистрированных приложений начинают отзывать доступ |
| март 2027 | публичный Data API закрывается для всех |

Смысл: **новому проекту ключи сейчас не выдают**. Тикет на доступ
(https://support.reddithelp.com/hc/en-us/requests/new?ticket_form_id=14868593862164)
имеет смысл только для уже существующих approved-приложений (регистрация на
Developer Platform), для новых заявок он не работает.

Если у тебя уже есть approved app (выданные ранее client_id/secret) —
зарегистрируй его на https://developers.reddit.com/app-registration до 12.01.2027.
Если ключей никогда не было — путь только через Devvit (см. ниже).

### Готовый текст заявки (скопировать в тикет)

```
App: content-factory-digest (script app, OAuth password grant)
Developer role: external integration not supported by Devvit
Public product URL: https://valdislavn-spec.github.io/content-factory/
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

## Что реально доступно сейчас (после 31.10.2026)

1. **Devvit-приложение в своём сабреддите** — единственный официальный способ
   автоматизации для нового проекта: без ключей и approval, но постит только
   туда, куда установлено; чужие сабреддиты недоступны. Это TypeScript/Devvit CLI,
   не наш Python-публикатор.
2. **Ручной постинг** в Reddit — легально и без API (для рекламы TG-каналов
   хватит закреплённого поста/профиля).
3. **Reddit Ads** — платная реклама, если нужен охват.
4. **Сторонние data API** — только чтение Reddit (платно); писать посты в Reddit
   через них нельзя.
5. Не обходить ограничения скрейпингом/мультиаккаунтами: Reddit за это банит.

Для нашего репозитория: `RedditPublisher` и workflow `reddit-digest` остаются
как legacy для аккаунтов с уже выданными ключами; включить их «с нуля» нельзя.

## Ссылки

- Создать script app: https://www.reddit.com/prefs/apps
- Регистрация приложения: https://developers.reddit.com/app-registration
- Responsible Builder Policy: https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy
- Data API Terms: https://redditinc.com/policies/data-api-terms
- Тикет на доступ: https://support.reddithelp.com/hc/en-us/requests/new?ticket_form_id=14868593862164&tf_42139884615700=api_request_type_developer_clone
- Devvit docs (RedditClient): https://developers.reddit.com/docs/
- API reference: https://www.reddit.com/dev/api
