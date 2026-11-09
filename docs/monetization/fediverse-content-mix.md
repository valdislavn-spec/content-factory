# Fediverse: контент-микс (крипто → AI → travel)

Аккаунт: **@hoopy0007ak@miraiverse.xyz** (Akkoma). Постим по одной теме за раз, по
кругу, с travel-рекламой каждый третий пост.

## Ротация

```
crypto/trading → AI×trading → crypto/trading → travel-реклама → повтор
```

- **crypto** — рынок + цифры BingX, ссылка на @HOOPY0007;
- **AI** — AI×трейдинг (LLM-ресёрч, сентимент, автоматизация), ссылка на @AINEWS0007;
- **travel** — реклама travel-направления (пока ссылка на Booking.com через наш
  трекер; после одобрения Travelpayouts заменить на партнёрскую), с маркировкой
  «Ad · travel partner».

Конфиг: [`config/fediverse_mix.yaml`](../../config/fediverse_mix.yaml).
Скрипт: [`scripts/fediverse_mix.py`](../../scripts/fediverse_mix.py).
Автопостинг: `.github/workflows/fediverse-mix.yml` — **4 раза в сутки**:
10:17, 14:17, 18:17 и 22:17 UTC (≈ 6:17, 10:17, 14:17, 18:17 ET — утро, день,
вечер и прайм-тайм US-аудитории). State ротации кэшируется между запусками.

## Как смешивать трейдинг, крипто и AI

1. **Цифры + вывод**: каждый крипто-пост — 1 цифра/уровень + 1 короткий вывод.
2. **AI только через призму трейдинга**: не «AI вообще», а «AI ускоряет ресёрч,
   но риск-менеджмент остаётся за трейдером».
3. **Чередование**: не два AI-поста подряд; после travel-рекламы — снова
   крипто-цифры (восстанавливаем доверие).
4. **Реклама не чаще 1 из 3** и всегда с дисклеймером; без обещаний доходности.
5. **Ссылки**: только через [трекер](link-tracker.md) — видно клики по каналам и
   темам (crypto/ai/travel).
6. **Хэштеги**: 3–5, разные под тему (#Bitcoin #Crypto #Trading / #AI #Travel).

## Оформление и картинки

**Приоритет — картинка из статьи.** Скрипт берёт свежие RSS-новости каналов
(`channels_config`), вытаскивает `media:content`/`enclosure`/`<img>` из фида или
`og:image` страницы (до 48 часов, до 6 кандидатов на фид), кропает в 1200×675 и
добавляет кредит: `📷 Photo: <домен> — <ссылка>`. Если картинки нет — рисует
свою карточку (Pillow):

- **crypto** — тёмная карточка с заголовком + реальный 24-часовой график BTC
  (BingX klines) и строкой рынка BTC/ETH/SOL;
- **ai** — карточка «AI × TRADING» с нейросетевым паттерном;
- **travel** — карточка «TRAVEL DEALS» с солнцем/горами/самолётом и
  дисклеймером.

Для **travel-поста** отдельный набор фидов: The Points Guy, Nomadic Matt,
Atlas Obscura, Travel Daily Media, Travelpayouts Blog
(`article_images.feeds.travel`); заголовок статьи становится
заголовком travel-поста, картинка прикрепляется с кредитом, ниже — партнёрская
ссылка и дисклеймер.

Картинка (из статьи или сгенерированная) загружается в Akkoma через
`/api/v2/media` и прикрепляется к посту (`media_ids`). Если загрузка не удалась —
пост публикуется текстом (graceful fallback). Настройки источника:
`config/fediverse_mix.yaml → article_images` (enabled, channels_config,
max_age_hours, max_feeds, max_candidates). Локальные копии:
`data/outbox/fediverse/`.

## Дублирование: Mastodon + Pixelfed

Каждый пост уходит в Akkoma и дублируется в **Mastodon**
(@Yeti01@mastodon.social) и **Pixelfed**
(@hoopy0007@pixelfed.au) — с картинкой и ссылками
(`crosspost.mastodon`, `crosspost.pixelfed` в конфиге).

## Mastodon-дублирование

Каждый fediverse-пост дублируется в **Mastodon** (@Yeti01@mastodon.social),
если заданы `MASTODON_BASE_URL`/`MASTODON_TOKEN` (`crosspost.mastodon: true`).
Публикация идёт через `/api/v1/statuses`; ссылки вырезаются при
`MASTODON_NO_LINKS=1` (правило mastodon.social для новых аккаунтов).

Токен обновлён (приложение `content-factory-media`, scopes `read write follow`) —
**картинки прикрепляются** в Mastodon так же, как в Akkoma; ссылки (включая
партнёрские) сохраняются в дублях. GitHub Secret `MASTODON_TOKEN` обновлён.

## Ручной запуск

```bash
python scripts/fediverse_mix.py --dry-run        # посмотреть следующий пост
python scripts/fediverse_mix.py --once           # опубликовать следующий
python scripts/fediverse_mix.py --sequence 3     # опубликовать 3 по кругу
python scripts/fediverse_mix.py --topic ai       # внеочередной AI-пост
```

## Travel-реклама — когда появится партнёрка

**Партнёрские ссылки подключены:** Travelpayouts-аккаунт (ID 674170) активен,
сгенерированы 4 оффера с subid `akkoma` и заведены коды в трекере:

| Оффер | Код трекера | Куда ведёт |
|---|---|---|
| Aviasales | `travel-aviasales` | aviasales.tpk.ro/IhIQwQjr |
| Airalo | `travel-airalo` | airalo.tpk.ro/3MTQ3pYY |
| Yesim | `travel-yesim` | yesim.tpk.ro/GJVi1V64 |
| Kiwitaxi | `travel-kiwitaxi` | kiwitaxi.tpk.ro/6eYqEgwC |

Travel-посты **ротируются** по `travel_offers` в конфиге (по одному офферу за
пост, CTA подставляется). Клики считаются трекером и Travelpayouts.

Для быстрого переключения без коммита остаётся env-override `TRAVEL_AFFILIATE_URL`
(локально или GitHub Secret) — если задан, travel-пост берёт его напрямую. После входа в Travelpayouts и одобрения бренда:
1. получить партнёрскую ссылку (или через [links API](https://support.travelpayouts.com/hc/en-us/articles/25289759198226-API-for-Travelpayouts-partner-links));
2. обновить target у `travel-default`:
   `python scripts/links_admin.py create --code travel-default --target "<affiliate>" ...`;
3. статистика кликов сохранится, конверсии пойдут в кабинет Travelpayouts.

## Опубликованные посты (08.11.2026)

1. crypto: https://nuages.cloud/notice/BCF9gozBId1VPEJuym
2. ai: https://nuages.cloud/notice/BCF9h8Q72ir5gG4C5w
3. travel: https://nuages.cloud/notice/BCF9hRqKpS7Vv5Tu6a
