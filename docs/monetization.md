# Монетизация: продажа рекламных постов за Telegram Stars

**Что это.** Бот принимает заказы на рекламные посты в наших каналах (US/EN + LatAm/ES),
берёт оплату в **⭐ Telegram Stars** и после ручной модерации отдаёт пост в очередь на
публикацию. Без платёжного провайдера, без сервера (long-polling), без комиссии платформ
за сам факт сделки.

> **Честно про заработок:** цены в `config/monetization.yaml` — стартовые. Реальные продажи
> начнутся, когда у каналов будет аудитория: сейчас у 5 из 6 каналов ~3 подписчика, у
> `crypto-news` ~3 666. Продавать рекламу в канале с 3 подписчиками никто не будет —
> инструмент готов заранее и включается, когда канал подрастёт (см. `tg-growth.md`).

## Как устроено

```
рекламодатель → /start → канал → тариф → счёт в Stars (XTR)
      ↓ оплата
successful_payment → бот просит текст → заявка админу (кнопки ✅/❌)
      ↓ одобрено
data/ads/queue/<id>.json → scripts/publish_ads.py --publish → пост в канале
```

Статусы заявки: `pending_invoice → awaiting_text → moderation → approved / rejected → published`,
плюс `refunded` для возврата Stars.

| Файл | Роль |
|---|---|
| `content_factory/monetization.py` | заказы в SQLite, счета, сценарии бота, возвраты Stars |
| `config/monetization.yaml` | каналы, тарифы и цены в Stars |
| `scripts/ad_bot.py` | long-polling бот продажи (dry-run/once/loop) |
| `scripts/ad_orders.py` | ручное управление: list/approve/reject/refund/stats |
| `scripts/publish_ads.py` | публикация одобренных постов (по умолчанию dry-run) |
| `scripts/bot_setup.py` | настройка имени/описаний/команд/меню бота через Bot API |
| `tests/test_monetization.py`, `tests/test_bot_setup.py` | 18 тестов без сети |

## Быстрый старт

```bash
# 1) в .env
TELEGRAM_BOT_TOKEN=...            # бот, который уже админ каналов (тот же, что публикует)
TELEGRAM_ADMIN_CHAT_ID=...        # ваш user_id/chat_id для уведомлений и модерации

# 2) проверить, что всё на месте (без сети)
./.venv/bin/python scripts/ad_bot.py --dry-run

# 3) настроить бота (команды, описание, меню) — Bot API
./.venv/bin/python scripts/bot_setup.py --dry-run
./.venv/bin/python scripts/bot_setup.py --apply

# 4) запустить продажи
./.venv/bin/python scripts/ad_bot.py
```

**Где узнать `TELEGRAM_ADMIN_CHAT_ID`:** напишите своему боту `/start`, затем откройте
`https://api.telegram.org/bot<TOKEN>/getUpdates` и возьмите `message.chat.id` (или
`from.id`). Это личный id — не публикуйте его.

## BotFather: что вручную, что скриптом

`scripts/bot_setup.py --apply` через Bot API настраивает: команды `/start /buy /orders /help`,
описание, короткое описание, кнопку меню. **Через @BotFather** (скрипт печатает чек-лист):

1. создать бота, получить токен;
2. `/setinline` — включить inline mode (нужно для growth-бота и кнопок «Поделиться»);
3. `/setjoingroups` и `/setprivacy` — по желанию (если бот работает в группах);
4. добавить бота **админом в каналы** с правом «Публикация сообщений»;
5. платёжный провайдер **не нужен** — оплата Stars (XTR) идёт без провайдера.

## Telegram Stars: что важно знать

- Счёт выставляется через `sendInvoice` с `currency: "XTR"` и пустым `provider_token`;
  после оплаты приходит `successful_payment` с `telegram_payment_charge_id` (храним).
- **Выплаты** Stars: через Fragment (TON), с холдом (обычно ~21 день); нужен TON-кошелёк
  и проверка доступности в вашей стране. Это не автоматизируется — только после запуска
  продаж, риски/налоги проверяйте сами.
- **Возврат** отклонённой заявки: `scripts/ad_orders.py refund <id>` → Bot API
  `refundStarPayment` (нужен `TELEGRAM_BOT_TOKEN`); статус станет `refunded`.
- **Правила:** продаём только рекламу в своих каналах; текст проходит модерацию; нельзя
  продавать накрутку/фейковые подписки/18+/скам — это нарушение ToS Telegram и риск бана.
- Минимальная цена — 1 ⭐ (в конфиге `min_amount`), цены — целые числа.

## Управление заявками

```bash
./.venv/bin/python scripts/ad_orders.py stats
./.venv/bin/python scripts/ad_orders.py list --status moderation
./.venv/bin/python scripts/ad_orders.py approve <order_id>   # → data/ads/queue/<id>.json
./.venv/bin/python scripts/ad_orders.py reject <order_id>
./.venv/bin/python scripts/ad_orders.py refund <order_id>   # вернуть Stars
```

Публикация одобренного:

```bash
./.venv/bin/python scripts/publish_ads.py --dry-run          # показать пост
./.venv/bin/python scripts/publish_ads.py --order <id> --publish
./.venv/bin/python scripts/publish_ads.py --all --publish
```

После публикации заявка получает `published`, файл переезжает в `data/ads/published/`.
Для `--publish` нужен `TELEGRAM_BOT_TOKEN`; бот должен быть админом канала.

## Ограничения

- **Один getUpdates-процесс на бота**: `ad_bot.py` и `telegram-growth-bot.py` теперь
  ставят общий lock по токену; второй процесс завершится с понятной ошибкой.
  Для одновременной работы нужен отдельный бот на каждый long-polling процесс.
- Рекламный пост сейчас текстовый (без поля image_url), до **3000 символов**;
  обычные посты завода при этом поддерживают `sendPhoto` (карточка/картинка статьи).
- Это не Telegram Ads: мы не покупаем рекламу, а **продаём посты в своих каналах**.
- Сеть: из этой машины `api.telegram.org` недоступен — запускать бота на VPS/машине с
  доступом к Telegram (или через Actions с long-poll нельзя: Actions не держит процесс).

## Что дальше (когда каналы подрастут)

1. Привязать `publish_ads.py` к общему планировщику (публиковать в согласованное время).
2. Добавить учёт статистики по каналам (сколько заработано, средний чек) в growth-отчёт.
3. Продажа «пакета 3 канала» (скидка), автопостинг после модерации без ручного `--publish`.
4. Telegram Stars → TON вывод (Fragment) — только после первых продаж.
