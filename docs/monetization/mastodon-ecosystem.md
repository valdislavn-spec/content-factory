# Mastodon / Fediverse: что ещё можно подключить (08.11.2026)

Аккаунт: **@amazing_Brave007@mastodon.social** (плюс Akkoma @hoopy0007@nuages.cloud).
Ниже — каналы роста/автоматизации, которые даёт Mastodon и Fediverse.

## Мосты в другие сети

| Мост | Что даёт | Статус |
|---|---|---|
| **Bridgy Fed** (`@bsky.brid.gy@bsky.brid.gy`) | Зеркалирует Mastodon-аккаунт в **Bluesky** (AT Protocol) — посты, ответы, лайки; бесплатно | ⏳ follow отправлен, но Bridgy требует **аватар + аккаунт ≥1 недели**; аккаунту 4 дня (создан 04.11). Аватар поставлен. Повторить после 11.11 (напоминание на 12.11) |
| **mostr.pub** (Nostr bridge) | Мост Fediverse → Nostr | ❌ аккаунт бриджа не находится (сервис недоступен/сменился) |
| **pinhole / Fedisky / RSS Parrot** | Альтернативные мосты (Bluesky/веб/RSS) | ⏳ можно попробовать, если Bridgy не подойдёт |
| **Farcaster / Nostr** | Официально «under consideration» у Bridgy Fed | ❌ пока нет |

## Fediverse-платформы (публикаторы уже есть в коде)

Можно подключить отдельные аккаунты (Mastodon-совместимый API): **Pleroma,
Akkoma, GoToSocial, Friendica, Misskey**. Плюс отдельные сети (нужны аккаунты):
**Pixelfed** (фото), **PeerTube** (видео), **Lemmy** (ссылки/сообщество),
**WriteFreely** (блог). Для нас приоритет: GoToSocial/ Friendica — как резерв,
Pixelfed — если пойдут фото-посты.

## Рост и аналитика через Mastodon API

- **Расписание постов**: `scheduled_at` в `/api/v1/statuses` (можно публиковать в пиковые часы без GitHub cron).
- **Метрики**: `favourites_count`, `reblogs_count`, `replies_count` по каждому статусу — отчёт по вовлечённости.
- **Follow requests**, списки, закладки, featured hashtags, закреплённые посты — настройка профиля под рост.
- **Webhooks** — только admin-level (не для пользователя).

## Кросспостинг/автоматизация (внешние)

- **Make / Zapier** — есть действия «Create status in Mastodon»: можно связать с Telegram/Discord/формами.
- **Buffer** — официальная поддержка Mastodon (paid), но у нас уже есть прямой API + cron.
- **RSS → Mastodon**: RSS Parrot / feed2toot — если понадобится зеркалить блог/канал из RSS.
- **Telegram ↔ Mastodon боты** — редкие, качество разное; наш пайплайн уже постит напрямую.

## Следующие шаги

1. 12.11 — повторить Bridgy Fed (аккаунт станет ≥7 дней) и принять follow-back.
2. Добавить скрипт метрик Мастодона/Akkoma (favourites/reblogs/replies + клики трекера) в недельный отчёт.
3. При росте — завести GoToSocial/Friendica как резервный fediverse-аккаунт.
