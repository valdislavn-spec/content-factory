# Telegram аутрич: шаблоны писем + tracking-ссылки

Дата: 2026-11-25. Дополнение к [telegram-shoutout-list-latam-us.md](telegram-shoutout-list-latam-us.md).

## 1. Готовые tracking-ссылки

Созданы в `links-tracker` (D1), каждая редиректит на наш канал и считает клики:

| code | ссылка | куда ведёт |
|---|---|---|
| `tg-es-crypto` | https://links-tracker.valdislav-n.workers.dev/r/tg-es-crypto | @TechnologiesNews01 (ES Crypto) |
| `tg-es-sport` | https://links-tracker.valdislav-n.workers.dev/r/tg-es-sport | @SPORTSAnalytics007 (ES Sport) |
| `tg-es-ai` | https://links-tracker.valdislav-n.workers.dev/r/tg-es-ai | @WORLDNews0007 (ES AI) |
| `tg-en-crypto` | https://links-tracker.valdislav-n.workers.dev/r/tg-en-crypto | @HOOPY0007 (EN Crypto) |
| `tg-en-sport` | https://links-tracker.valdislav-n.workers.dev/r/tg-en-sport | @SPORTNews0007 (EN Sport) |
| `tg-en-ai` | https://links-tracker.valdislav-n.workers.dev/r/tg-en-ai | @AINEWS0007 (EN AI) |

Проверено: все отдают HTTP 302 на нужный `t.me`.

### Правило атрибуции

Не давать один и тот же код двум разным каналам. На каждую закупку — свой код
с суффиксом источника: `tg-es-crypto-telonews`, `tg-en-crypto-watcher` и т.д.
Создание кода (делаю я, токен не публикуется):

```bash
curl -X POST "$LINK_TRACKER_BASE/admin/links?token=$LINK_TRACKER_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"code":"tg-es-crypto-telonews","target":"https://t.me/TechnologiesNews01",
       "channel":"telegram-es","network":"telegram","label":"Telo News shout-out"}'
```

После размещения: клики по коду видны в `click_log` (страна/город/referer/UA);
отчёт по кликам и подпискам собираю отдельно.

## 2. Шаблон первого сообщения (ES)

> Hola, buenas tardes.
>
> Мы издаём Telegram-канал «ES Crypto & Blockchain» (@TechnologiesNews01) —
> новости крипто/блокчейна для испаноязычной аудитории (LATAM + España).
> Хотим разместить пост или нативную интеграцию в вашем канале @<canal> (~N подписчиков).
>
> Подскажите, пожалуйста:
> 1) стоимость поста на 24 ч — с закрепом и без;
> 2) формат: текст + ссылка, можно ли с картинкой;
> 3) свежую статистику: средние просмотры поста и гео (MX / AR / CO / ES / US);
> 4) условия оплаты: постоплата или CPM;
> 5) можно ли ставить нашу tracking-ссылку (редирект) — это важно для замера.
>
> Если есть прайс — пришлите, пожалуйста. Gracias.

## 3. Шаблон первого сообщения (EN, US crypto)

> Hi! We run a Telegram crypto-news channel for a US/global audience (@HOOPY0007).
> We'd like to book a sponsored post / native mention in @<channel> (~N subscribers).
>
> Could you share: price for a 24h post (pinned / unpinned), post format,
> average views per post and geo split (US share especially), payment terms
> (postpay or CPM), and whether a tracked redirect link is OK?
>
> If you have a media kit/price list, please send it. Thanks!

## 4. Follow-up (через 3 дня)

ES: «Hola, возвращаюсь к вопросу о размещении в @<canal>. Актуально ли предложение?
Если да — пришлите цену и статистику, запускаем тест на этой неделе.»

EN: «Hi, following up on the sponsored post in @<channel>. Still interested?
If yes, send price + stats — we're running a test this week.»

## 5. Чеклист перед оплатой

- [ ] views ≥ 10–20% от подписчиков, живые комментарии, посты свежие;
- [ ] скриншот статистики канала: охваты, гео, динамика;
- [ ] формат зафиксирован: текст/фото/видео, ссылка в тексте или кнопкой;
- [ ] закреп (если нужен), срок удаления, возврат при недоборе просмотров;
- [ ] оплата: постоплата или 50/50; предоплата — только официальным медиа
      с юрлицом/реквизитами;
- [ ] brand safety: без пиратки, казино и скама — иначе отказ;
- [ ] tracking-код уникален и проверен (302 на наш канал);
- [ ] после публикации: скриншот поста + ссылка, затем отчёт по кликам.

## 6. Guardrails по бюджету

| Сегмент | Ориентир за пост | CPM по факту |
|---|---|---|
| ES 100–200k подписчиков | $30–150 | $0.9–3 |
| ES медиа 20–70k | $20–80 | $1–4 |
| EN топ (Watcher Guru, Cointelegraph) | $1–5k | не брать для теста |
| EN средние (CoinMarketCap и др.) | $200–800 | $2–5 |

Тест: 3–5 каналов × $50–100, 2 креатива на канал, срок 48 ч.
KPI: ≤ $0.10–0.15 за подписчика (ES), ≤ $0.30 (US).

## 7. Таблица сделок (вести по мере аутрича)

| Канал | Подписчики | Направление | Статус | Цена | Формат | Гео | Оплата | Code | Клики | Подписки | CPL |
|---|---|---|---|---|---|---|---|---|---|---|---|
| @telonews_es | 67 075 | ES crypto | не писали | | | | | tg-es-crypto-telonews | | | |
| @criptonoticias | 41 801 | ES crypto | не писали | | | | | tg-es-crypto-criptonoticias | | | |
| @cointelegraph_es | 25 969 | ES crypto | не писали | | | | | tg-es-crypto-ct-es | | | |
| @chiringuitotelegram | 44 597 | ES sport | не писали | | | | | tg-es-sport-chiringuito | | | |
| @buzzfutbol | 48 581 | ES sport | не писали | | | | | tg-es-sport-buzzfutbol | | | |
| @coinmarketcap | 66 420 | EN crypto | не писали | | | | | tg-en-crypto-cmc | | | |
| @watcherguru | 639 186 | EN crypto | не писали | | | | | tg-en-crypto-watcher | | | |

Коды из таблицы создаю перед отправкой сообщения — тогда клики сразу лягут
в нужную строку.
