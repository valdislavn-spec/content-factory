# Fediverse: Pleroma, Akkoma, GoToSocial, Friendica, Misskey

Fediverse — сеть независимых серверов без рекламы и ревью контента. В проекте уже
работает Mastodon; добавлены ещё пять сетей того же типа.

| Сеть | API | Env | Лимит поста |
|---|---|---|---|
| Pleroma | Mastodon API (`/api/v1/statuses`) | `PLEROMA_BASE_URL` / `PLEROMA_TOKEN` | 500 (безопасный) |
| Akkoma | Mastodon API | `AKKOMA_BASE_URL` / `AKKOMA_TOKEN` | 500 |
| GoToSocial | Mastodon API | `GOTOSOCIAL_BASE_URL` / `GOTOSOCIAL_TOKEN` | 500 |
| Friendica | Mastodon API | `FRIENDICA_BASE_URL` / `FRIENDICA_TOKEN` | 500 |
| Misskey / Firefish / Sharkey | Misskey API (`/api/notes/create`) | `MISSKEY_HOST` / `MISSKEY_TOKEN` | 3000 (`MISSKEY_MAX_CHARS`) |

Все публикаторы **опциональные**: если креды не заданы, конвейер молча
пропускает сеть (ошибкой не считается). По умолчанию они **не включены** в
каналы — чтобы один аккаунт не заспамил все темы. Включаются добавлением имени
в `publisher_ids` нужного канала:

```yaml
  publisher_ids: [telegram, mastodon, pleroma, misskey]
```

## Как получить токен

### Pleroma / Akkoma
1. Зарегистрироваться на инстансе (например, `https://pleroma.site`, список —
   <https://fediverse.party> или <https://fedidb.org/software>);
2. **Settings → Applications → New application** (или `/api/v1/apps`), scopes:
   `read write follow`;
3. Скопировать access token.

### GoToSocial
1. Инстанс (например, `https://gts.superseriousbusiness.org` / федеративные
   списки), аккаунт;
2. **Settings → Applications** → создать приложение → access token.

### Friendica
1. Аккаунт на инстансе Friendica;
2. **Settings (Настройки) → Applications** → создать приложение/Mastodon API
   token, scopes read/write.

### Misskey / Firefish / Sharkey
1. Аккаунт на инстансе (`https://misskey.io`, `https://firefish.social`, …);
2. **Settings → API → Access Tokens → Generate**;
3. Права: `write:notes`, `read:account`; скопировать токен;
4. `MISSKEY_HOST` — домен **без** `https://`, например `misskey.io`.

## Env

```env
# Mastodon-совместимые
PLEROMA_BASE_URL=https://pleroma.example
PLEROMA_TOKEN=...
AKKOMA_BASE_URL=https://akkoma.example
AKKOMA_TOKEN=...
GOTOSOCIAL_BASE_URL=https://gts.example
GOTOSOCIAL_TOKEN=...
FRIENDICA_BASE_URL=https://friendica.example
FRIENDICA_TOKEN=...

# Misskey
MISSKEY_HOST=misskey.example
MISSKEY_TOKEN=...
MISSKEY_MAX_CHARS=3000
```

Отдельный аккаунт на канал — суффикс `<CHANNEL_ID>`:
`PLEROMA_TOKEN_AI_NEWS`, `MISSKEY_HOST_CRYPTO_ES` и т.п. (как у Mastodon/Bluesky).

## Проверка и включение

```bash
python -m content_factory social-check   # покажет ✓ по настроенным сетям
```

Публикация постов идёт из общего конвейера: при наличии кредов каждый новый пост
уходит в Telegram → Bluesky → Mastodon → Discord → Pleroma → Akkoma →
GoToSocial → Friendica → Misskey (настроенные сети). Недоступные — пропускаются.

## Ссылки и антиспам

Пока новые аккаунты «прогреваются», действует общий флаг `MASTODON_NO_LINKS=1`:
URL вырезаются из текста (остаются упоминания `@channel`). Через 1–2 недели
активности выставить `0` — ссылки вернутся и в эти сети.

## Безопасность

- токен = доступ к аккаунту (посты/профиль) — только в `.env`/GitHub Secrets;
- лучше отдельные аккаунты на сеть/канал, а не один токен везде;
- Misskey-токен с правами `write:notes` не может удалять чужие посты, но может
  писать от вашего имени;
- неавторизованные инстансы могут быть нестабильны — публикатор просто
  пропускает пост при ошибке.

## Что можно добавить дальше

- **Lemmy** — посты в сообщества (нужен JWT-login, другой формат: link/text post);
- **Nostr** — децентрализованные релеи (подпись событий ключом, NIP-01);
- **Pixelfed** — фото-сеть (нужны картинки, сейчас пайплайн текстовый).
