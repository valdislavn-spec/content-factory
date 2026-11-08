# Реферальная строка в постах (BingX)

В посты крипто-каналов добавляется реферальная ссылка BingX с маркировкой.
Работает через `publish_post` (после рыночной строки), конфиг — на канале.

## Что уже подключено

- Ссылка: **https://bingxdao.com/invite/WYYEGK/** (код `WYYEGK`, 10% от комиссий).
- Каналы: `crypto-news` (EN) и `crypto-es` (ES).
- Частота: **1 пост из 3** (`every_n_posts: 3`), начиная с первого поста дня.
- Маркировка: «ad · affiliate link» (EN) / «anuncio · enlace de afiliado» (ES) +
  дисклеймер о гео-ограничениях и волатильности.

Пример EN-поста в конце (перед хештегами):

```
🤝 Trade crypto on BingX (ad · affiliate link): https://bingxdao.com/invite/WYYEGK/
Ad · affiliate link. Not available in the US, UK, Canada, Singapore, Netherlands and Hong Kong. Crypto is volatile — risk of loss.
```

## Настройка (config/channels.*.yaml)

```yaml
  affiliate:
    enabled: true
    link: "https://bingxdao.com/invite/WYYEGK/"
    every_n_posts: 3
    disclaimer: "Ad · affiliate link. Not available in the US, ..."
    # texts:                    # опционально, переопределение текста
    #   en: "🤝 Trade crypto on BingX (ad · affiliate link): {link}"
```

Переопределение ссылки без коммита (например, новая реф-ссылка):

```bash
AFFILIATE_LINK_CRYPTO_NEWS=https://bingx.com/invite/NEWCODE   # для канала crypto-news
AFFILIATE_LINK=https://bingx.com/invite/NEWCODE               # для всех каналов
```

Порядок: env канала → общий env → YAML `link`. Битая/пустая ссылка → строка
не добавляется (пост не ломается).

## Важно: гео BingX

BingX не обслуживает **США, Канаду, Великобританию, Сингапур, Нидерланды,
Гонконг** ([restricted jurisdictions](https://bingx.com/en/support/articles/360033286474)).
Поэтому:

- EN-канал: аудитория US — конверсия будет низкой; строка стоит с дисклеймером,
  но это не основной источник дохода.
- ES-канал (ЛатАм) — целевая гео для BingX, там ссылка уместнее.

Для US-аудитории альтернативы: Coinbase, Kraken, Crypto.com, Binance.US
(см. `docs/monetization/partner-programs.md`).

## Тесты

`tests/test_affiliate.py` — тексты EN/ES, env-override, частота, отключение,
невалидная ссылка.

## Статус Affiliate Program (до 50%)

**08.11.2026** заявка в BingX Affiliate Program отправлена через кабинет BingX:
имя, email, Telegram @HOOPY0007, страна/регион, промо-платформа Telegram,
~3 700 подписчиков, скриншот канала, план продвижения.

Ответ BingX: «Thank you for your application. Our official team will contact you
via the contact info you provided within 5 workdays after reviewing it» (Success).

Что дальше:
- до одобрения в постах остаётся стандартная реферальная ссылка
  `https://bingxdao.com/invite/WYYEGK/` (10%);
- после одобрения — заменить `affiliate.link` в `channels.*.yaml` на выданную
  affiliate-ссылку (или задать `AFFILIATE_LINK_CRYPTO_NEWS`) и проверить в Partner Hub,
  что ставка 50% и выплаты ежедневные.
