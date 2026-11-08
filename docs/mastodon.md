# Mastodon: настройка аккаунта и постинг

Mastodon — бесплатная федеративная соцсеть без алгоритма и рекламы. Публикатор
в проекте уже есть и включён в `publisher_ids` всех EN/ES-каналов: как только
появятся креды, пайплайн начнёт автоматически кросс-постить каждый пост.

## 1. Регистрация (mastodon.social/start)

1. Откройте <https://mastodon.social/start>;
2. Создайте аккаунт: email, пароль, подтвердите письмо;
3. Заполните профиль: аватар, имя, описание (например: «AI News — короткие
   новости об AI. Telegram: https://t.me/AINEWS0007»);
4. В настройках профиля включите **Bot account**, чтобы аккаунт был помечен как бот.

Если mastodon.social перегружен/не подходит — можно любой инстанс
(mstdn.social, mas.to и т.д.), тогда `MASTODON_BASE_URL` = его адрес.

## 2. Токен приложения

1. Preferences → **Development** → **New application**;
2. Name: `content-factory`, Website: ссылка на канал;
3. Scopes: **`read:accounts`**, **`write:statuses`** (для постов достаточно);
4. Submit → откройте приложение → скопируйте **Your access token**.


## 2.1 OAuth-скрипт (быстрый путь)

Не нужно вручную создавать приложение в UI — есть помощник:

```bash
# 1. создать OAuth-приложение на инстансе (аккаунт пока не нужен)
python scripts/mastodon_auth.py register
#    → печатает ссылку авторизации

# 2. зарегистрироваться на https://mastodon.social/start и открыть ссылку,
#    нажать Authorize и скопировать код

# 3. обменять код на токен и записать в .env
python scripts/mastodon_auth.py token --code ВАШ_КОД --write-env

# 4. проверить
python scripts/mastodon_auth.py check
```

Права приложения ограничены `read:accounts` + `write:statuses`.
Служебный файл приложения — `data/mastodon_app.json` (gitignored).

## 3. Переменные окружения

В `.env` (локально) или GitHub Secrets (для Actions):

```env
MASTODON_BASE_URL=https://mastodon.social
MASTODON_TOKEN=ваш_токен
```

Если у каналов разные аккаунты — per-channel (суффикс = id канала):

```env
MASTODON_BASE_URL_AI_NEWS=https://mastodon.social
MASTODON_TOKEN_AI_NEWS=...
MASTODON_BASE_URL_CRYPTO_NEWS=https://mastodon.social
MASTODON_TOKEN_CRYPTO_NEWS=...
```

## 4. Проверка

```bash
python -m content_factory social-check   # mastodon ✓ для каналов с кредами
python scripts/mastodon_publish.py       # dry-run очереди (ничего не постит)
python scripts/mastodon_publish.py --apply          # опубликовать очередь
python scripts/mastodon_publish.py --channel ai-news --apply  # только один канал
```

## 5. Стартовая очередь постов

`config/mastodon_queue.yaml` — **10 готовых постов** (EN: AI/Crypto/Sports;
ES: AI/Crypto/Fútbol): интро-посты + примеры новостей. Все ≤500 символов,
plain text, хэштеги CamelCase, ссылка на Telegram-канал. Отредактируйте тексты
под свои аккаунты и публикуйте.

## 6. Автопостинг в пайплайне

В `config/channels.en.yaml`/`.es.yaml` у каждого канала:
`publisher_ids: [telegram, bluesky, mastodon, discord]`.
Когда креды заданы, каждый новый пост после Telegram автоматически уходит в
Mastodon (текст обрезается до 500 символов, HTML снимается, добавляется ссылка
на Telegram-канал). Если кредов нет — публикатор молча пропускается, ошибкой
не считается.

## 7. Формат и этикет

- **≤500 символов** (лимит инстанса по умолчанию; некоторые дают 5000);
- plain text, без markdown и HTML (пайплайн сам чистит разметку);
- хэштеги: 2–4 на пост, CamelCase (`#OpenAI`, `#LaLiga`), не более 1–2 ссылок;
- не спамить: 2–4 поста/день на аккаунт, отвечать на упоминания, делиться
  чужими постами (boost) — это главный способ роста;
- ссылки на `t.me` Mastodon превращает в превью-карточку — это плюс;
- для чувствительных тем использовать CW (`spoiler_text`), в очереди поле
  `spoiler_text` можно добавить при необходимости.

## 8. Ограничения

- API: ~300 запросов / 5 минут на токен, постинг — разумно 2–4/день;
- медиа: прикреплять можно через `POST /api/v2/media` (в пайплайне пока только
  текст; картинки — отдельная задача);
- аккаунт-бот обязан соблюдать правила инстанса; массфолловинг может привести
  к бану.
## 9. Важно для новых аккаунтов (антиспам)

Свежий аккаунт на mastodon.social помечен как «новый»: посты с внешними
ссылками (например, `t.me/...`) могут **автоматически удаляться антиспамом**
(симптом: API создаёт пост, но публичный URL отдаёт 404, а `statuses_count`
не растёт). Проверено на аккаунте @amazing_Brave007.

Что делать:

1. Подтвердите email и заполните профиль (аватар, описание, ссылки на каналы) —
   пустой профиль усиливает фильтры;
2. Включите **Bot account** в настройках профиля;
3. Первые дни постите **без внешних ссылок** — вместо `https://t.me/...`
   пишите `Telegram: @username` (в очереди уже так);
4. Ссылки на каналы — в профиле/закрепе; через 1–2 недели активности ссылки
   в постах обычно перестают фильтроваться;
5. Если пост удалён — повторите без ссылок, не спамьте повторами.
## 10. Оформление профиля (аватар, шапка, био, бот)

Картинки: `assets/mastodon/avatar.png` (400×400), `assets/mastodon/header.png` (1500×500).

```bash
python scripts/mastodon_profile.py --dry-run   # показать поля без запросов
python scripts/mastodon_profile.py             # применить
```

Скрипт ставит `display_name`, био со ссылками на Telegram-каналы, поля-ссылки,
флаг **bot**, `discoverable` и `indexable`. Нужен токен с **`write:accounts`**
(создаётся через `scripts/mastodon_auth.py`; токен сохраните как `access_token`
в `data/mastodon_app_profile.json`).

## 11. Ссылки в постах: временный режим

Пока аккаунт новый, пайплайн публикует без ссылок: переменная
`MASTODON_NO_LINKS=1` (local `.env` и GitHub variable) вырезает URL из текста
поста перед отправкой, оставляя упоминания вида `@AINEWS0007`.

- сейчас: `MASTODON_NO_LINKS=1` — ссылки в профиле, посты без URL;
- через 1–2 недели активности (заполнен профиль, подтверждён email, есть
  фолловеры/бусты): выставить `MASTODON_NO_LINKS=0` — ссылки вернутся в посты;
- GitHub variable: Settings → Secrets and variables → Actions → Variables.
