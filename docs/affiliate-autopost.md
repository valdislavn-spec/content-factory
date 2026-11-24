# Партнёрские блоки в автопостах

Код: `content_factory/affiliate_inject.py`, встроен в `content_factory/publishers/telegram.py`.
Значит работает для **всех** автопостов, которые идут через общий пайплайн — ничего в
вызывающем коде менять не нужно.

## Как работает

1. Реестр: `config/affiliates.yaml` — программы (`status: ready`), привязка к каналам, раскрытие.
2. Правило: `rules.affiliate_every: 5` → блок встаёт в каждый 5-й пост канала.
3. Программы ротируются по кругу (mylead → collaborator → …), ссылка — с UTM-метками канала.
4. Счётчик постов: `data/affiliate/autopost_state.json` (по каналам).
5. Сбой реестра не ломает публикацию: пост уходит без блока, в лог пишется warning.

Отключить: `AFFILIATE_AUTOPOST=0` в `.env` (или окружении).

## Предпросмотр

```bash
python3 -m content_factory.affiliate_inject --channel crypto-news --index 5
python3 -m content_factory.affiliate_inject --channel ai-news --program collaborator
```

## Демо (5 постов, блок на 5-м)

```html
<b>Новость #5</b>
Короткий текст поста.

<b>🤝 Partners</b>
• <a href="https://mylead.global/r/dJ67Qo?utm_source=tg_crypto_en&utm_medium=telegram&utm_campaign=partners">MyLead</a> — 5% от заработка приглашённого

<i>Advertising / affiliate link. We may earn a commission if you sign up. No guaranteed returns.</i>
```

Тесты: `./.venv/bin/python -m pytest tests/test_affiliate_inject.py -q` (8 шт).

## Что нужно, чтобы блоки реально пошли в каналы

1. Бот **@Novyi0007Bot** — администратор в канале с правом «Публикация сообщений».
2. В `.env` заполнен `TELEGRAM_CHAT_ID_<КАНАЛ>` (для US-каналов сейчас пусто, см. ниже).
3. Программа в `config/affiliates.yaml` имеет `status: ready` — у 8 программ статус
   `awaiting_login` (нужен вход в партнёрский кабинет и генерация ссылки).

## Платные рекламные посты — без партнёрских блоков

Оплаченная реклама публикуется через `ad-sales/scripts/orders.py deliver` (свой путь) —
партнёрский блок туда **не** добавляется: рекламодатель платит за свой пост, чужие ссылки
в нём недопустимы. Блоки идут только в органические автопосты.
