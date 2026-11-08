# Автопостинг: все платформы, статус и что нужно

Обновлено: 07.11.2026. Цель — публиковать посты контент-завода во все соцсети,
где есть API для автопостинга. Публикаторы включаются в `publisher_ids` канала
(`config/channels.*.yaml`) и берут креды из `.env`.

Рекомендуемый пайплайн: Telegram — основной канал; X/Facebook/LinkedIn/Medium —
репост текста; Instagram/Threads/YouTube/TikTok/Pinterest — медиа-контент
(нужен публичный URL картинки/видео, см. `LANDING_HOST`).

## Статус по платформам

| Платформа | API | Что нужно в `.env` | Контент | Статус |
|---|---|---|---|---|
| **Telegram** | Bot API | `TELEGRAM_BOT_TOKEN` | текст/фото/опросы | ✅ работает |
| **X (Twitter)** | API v2, OAuth 1.0a | `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET` | текст 280 | ✅ реализован, нужны ключи |
| **VK** | VK API | `VK_ACCESS_TOKEN`, `VK_GROUP_ID` | текст/фото | ✅ реализован, нужен токен |
| **Facebook Page** | Graph API v21 | `FACEBOOK_PAGE_ID`, `FACEBOOK_PAGE_TOKEN` | текст | ✅ реализован, нужен токен |
| **LinkedIn** | REST Posts API | `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_AUTHOR_URN` | текст | ✅ реализован, нужен токен |
| **Medium** | Integration API | `MEDIUM_TOKEN` | статья (markdown) | ✅ реализован, нужен токен |
| **Bluesky** | AT Protocol | `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD` | текст | ✅ реализован, нужен app password |
| **Mastodon** | Mastodon API | `MASTODON_BASE_URL`, `MASTODON_TOKEN` | текст | ✅ реализован, нужен токен |
| **Discord** | Webhook | `DISCORD_WEBHOOK_URL` | текст | ✅ реализован, нужен webhook |
| **Instagram** | Graph API | `IG_USER_ID`, `IG_ACCESS_TOKEN` + публичный URL фото | фото+подпись | 🔲 нужен хостинг картинок |
| **Threads** | Graph API | `THREADS_USER_ID`, `THREADS_ACCESS_TOKEN` | текст | 🔲 могу добавить (30 мин) |
| **Reddit** | OAuth2 script app | `REDDIT_CLIENT_ID/SECRET/USERNAME/PASSWORD/SUBREDDIT` | self-пост | ✅ реализован, нужны ключи |
| **YouTube** | Data API v3 | OAuth2 Google (`YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN`) | видео | 🔲 только видео, нужен OAuth |
| **TikTok** | Content Posting API | app + токен (после ревью) | видео | 🔲 нужен ревью приложения |
| **Pinterest** | API v5 | `PINTEREST_TOKEN` + URL картинки | пины | 🔲 нужен хостинг картинок |
| **Tumblr** | API v2, OAuth 1.0a | `TUMBLR_CONSUMER_KEY`, `TUMBLR_CONSUMER_SECRET`, `TUMBLR_OAUTH_TOKEN`, `TUMBLR_OAUTH_TOKEN_SECRET`, `TUMBLR_BLOG` | текст до 12 000 символов | ✅ реализован и подключён (`vlad-007`), автопостинг из GitHub Actions |

## Как получить ключи (коротко)

- **X**: <https://developer.x.com> → Sign up (free tier: ~500 постов/мес) →
  Project & App → Keys and tokens → API Key/Secret + Access Token/Secret
  (права **Write**). Ключи от приложения с write-доступом.
- **Facebook/Instagram/Threads**: <https://developers.facebook.com> → Create app
  (Business) → Graph API Explorer → permissions `pages_manage_posts` (FB),
  `instagram_content_publish` + `instagram_basic` (IG, нужен Professional account),
  `threads_basic` + `threads_content_publish` (Threads) → Page/IG/Threads token.
- **LinkedIn**: <https://developer.linkedin.com> → Create app → products
  «Share on LinkedIn», «Sign In with LinkedIn» → OAuth 2.0 (`w_member_social`
  или `w_organization_social`) → нужен `access_token` и author URN.
- **Medium**: Settings → Security and apps → Integration tokens → `MEDIUM_TOKEN`.
- **Bluesky**: Settings → App Passwords → `BLUESKY_HANDLE` + пароль.
- **Mastodon**: Preferences → Development → New application → токен.
- **Discord**: Server settings → Integrations → Webhooks → URL.
- **VK**: <https://dev.vk.com> → Standalone app → Implicit Flow token с правами
  `wall,manage` (для группы) → `VK_ACCESS_TOKEN` + `VK_GROUP_ID`.
- **Reddit**: <https://www.reddit.com/prefs/apps> → script app → client id/secret,
  логин/пароль бота, сабреддит.
- **YouTube**: Google Cloud Console → OAuth client (Desktop) → consent screen →
  refresh token (Google-аккаунт уже подключён в `.local/google-connect`).
- **Tumblr**: <https://www.tumblr.com/oauth/apps> → Register application → **Show secret key** → `TUMBLR_CONSUMER_KEY/SECRET`; затем OAuth 1.0a (request_token → authorize → access_token) → `TUMBLR_OAUTH_TOKEN/SECRET`, `TUMBLR_BLOG` — имя блога (напр. `vlad-007`).
- **TikTok**: <https://developers.tiktok.com> → Content Posting API → app review.

## Как включить публикацию в канал

1. Добавьте креды в `.env` (см. `.env.example`).
2. В `config/channels.en.yaml` / `channels.es.yaml` у канала:
   ```yaml
   publisher_ids: [telegram, x, facebook, linkedin, medium]
   ```
3. Проверка без постинга:
   ```bash
   python -m content_factory.cli publish --help   # см. доступные команды
   ```
4. В dry-run (`CONTENT_FACTORY_DRY_RUN=true`) ничего не уходит в сеть.

## Ограничения

- X: бесплатный тариф ~500 постов/мес; текст 280 символов (ссылка съедает ~23).
- Instagram/Threads/Pinterest: нужен публичный HTTPS-URL изображения —
  можно отдавать карточки через `LANDING_HOST`/Cloudflare R2.
- YouTube/TikTok: только видео, текстовые посты не публикуются.
- Facebook/Instagram: приложение Meta должно быть в Live-режиме для чужих
  токенов; для своих страниц достаточно dev-режима.
- Telegram остаётся главным каналом; остальные — дополнительный охват.

## Tumblr в облаке (GitHub Actions)

Автопостинг по расписанию идёт из `content-factory.yml`. Секреты репозитория:
`TUMBLR_CONSUMER_KEY`, `TUMBLR_CONSUMER_SECRET`, `TUMBLR_OAUTH_TOKEN`,
`TUMBLR_OAUTH_TOKEN_SECRET`, `TUMBLR_BLOG` (Settings → Secrets and variables →
Actions). В `config/channels.en.yaml` и `config/channels.es.yaml` включено
`publisher_ids: [telegram, tumblr]` — посты кросспостятся в Tumblr автоматически.

- Текст: plain-text из Telegram-поста (HTML снимается), лимит **12 000 символов**,
  хэштеги → теги Tumblr, в конце ссылка на Telegram-канал; пер-канальный блог
  задаётся `TUMBLR_BLOG_<CHANNEL_ID>`.
- Секреты добавлены 2026-11-07; первый облачный прогон с ними — run `42431211988`.

