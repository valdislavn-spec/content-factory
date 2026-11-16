# Social publishing

## X / Twitter

Опубликованный промо-пост: https://twitter.com/NValdislav/status/2122428906288378209

Публикация выполнена через Buffer API, потому что прямое X API-приложение
сейчас имеет read-only OAuth-права.

### Повторный ручной запуск

GitHub Actions → `post-telegram-channels-buffer` → Run workflow.

Скрипт: `scripts/post_telegram_channels_buffer.py`.
Защита от дублей: `growth-funnel/.tweeted-telegram-channels`.

### Прямое X API

`tweet-telegram-channels` оставлен как ручной workflow. Для него нужно
в X Developer Portal выставить app permissions **Read and write** и
перегенерировать Access Token/Secret.
