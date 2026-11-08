# Fediverse: контент-микс (крипто → AI → travel)

Аккаунт: **@hoopy0007@nuages.cloud** (Akkoma). Постим по одной теме за раз, по
кругу, с travel-рекламой каждый третий пост.

## Ротация

```
crypto/trading → AI×trading → travel-реклама → повтор
```

- **crypto** — рынок + цифры BingX, ссылка на @HOOPY0007;
- **AI** — AI×трейдинг (LLM-ресёрч, сентимент, автоматизация), ссылка на @AINEWS0007;
- **travel** — реклама travel-направления (пока ссылка на Booking.com через наш
  трекер; после одобрения Travelpayouts заменить на партнёрскую), с маркировкой
  «Ad · travel partner».

Конфиг: [`config/fediverse_mix.yaml`](../../config/fediverse_mix.yaml).
Скрипт: [`scripts/fediverse_mix.py`](../../scripts/fediverse_mix.py).
Автопостинг: `.github/workflows/fediverse-mix.yml` — **2 раза в сутки**
(10:17 и 18:17 UTC), state ротации кэшируется между запусками.

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

## Ручной запуск

```bash
python scripts/fediverse_mix.py --dry-run        # посмотреть следующий пост
python scripts/fediverse_mix.py --once           # опубликовать следующий
python scripts/fediverse_mix.py --sequence 3     # опубликовать 3 по кругу
python scripts/fediverse_mix.py --topic ai       # внеочередной AI-пост
```

## Travel-реклама — когда появится партнёрка

Сейчас `travel_link` ведёт на Booking.com через трекер (клики считаются, но
комиссии нет). После входа в Travelpayouts и одобрения бренда:
1. получить партнёрскую ссылку (или через [links API](https://support.travelpayouts.com/hc/en-us/articles/25289759198226-API-for-Travelpayouts-partner-links));
2. обновить target у `travel-default`:
   `python scripts/links_admin.py create --code travel-default --target "<affiliate>" ...`;
3. статистика кликов сохранится, конверсии пойдут в кабинет Travelpayouts.

## Опубликованные посты (08.11.2026)

1. crypto: https://nuages.cloud/notice/BCF9gozBId1VPEJuym
2. ai: https://nuages.cloud/notice/BCF9h8Q72ir5gG4C5w
3. travel: https://nuages.cloud/notice/BCF9hRqKpS7Vv5Tu6a
