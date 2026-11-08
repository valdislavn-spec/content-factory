# Бесплатный VPN через GitHub: Xray + публичные ноды

Дата: 07.11.2026. Ситуация: сеть блокирует `t.me`, `x.com`, `instagram`,
`facebook`, `youtube`, WARP API (`api.cloudflareclient.com`,
`engage.cloudflareclient.com`) и Telegram Bot API напрямую. GitHub, workers.dev,
Google и большинство CDN доступны.

## Что оказалось рабочим

1. **Cloudflare WARP** — установлен, но в этой сети бесполезен: блокируются
   регистрация и data-plane WARP.
2. **Cloudflare Worker TCP-туннель** — данные тянет (curl 200 к YouTube/Instagram/
   Facebook/TikTok/Reddit), но браузер через него отрисовывается нестабильно.
3. **Xray-core + бесплатные VLESS-ноды из GitHub** — ✅ **работает полностью**:
   YouTube, Instagram, Facebook, TikTok, Reddit, **X/Twitter**, t.me.
   Exit IP тестового запуска: `79.182.70.192` (ЕС).

## Быстрый старт

```bash
cd content-factory

# 1) скачать Xray (если нет) и найти рабочую ноду
../tools/markitdown-venv/bin/python scripts/free_proxy.py setup

# 2) запустить локальный SOCKS5 на 127.0.0.1:1080 (держится, пока окно открыто)
../tools/markitdown-venv/bin/python scripts/free_proxy.py start

# 3) проверить доступ к соцсетям
../tools/markitdown-venv/bin/python scripts/free_proxy.py test

# 4) открыть Chrome с Google-профилем через SOCKS (вкладки соцсетей)
../tools/markitdown-venv/bin/python scripts/free_proxy.py chrome
```

Любой клиент можно направить через прокси:
```bash
curl --socks5-hostname 127.0.0.1:1080 https://x.com
# Chrome: --proxy-server=socks5://127.0.0.1:1080
```

## Откуда берутся ноды

Скрипт скачивает публичные подписки из GitHub (репозитории вида
`ripaojiedian/freenode`, `Pawdroid/Free-servers`), парсит `vless://`/`ss://`,
сортирует (приоритет: ws+tls, порт 443, reality) и по очереди проверяет
доступность `x.com` + `t.me` через локальный SOCKS. Рабочая нода пишется в
`../tools/xray/config.json`.

Если нода умерла — просто повторите `setup` (списки обновляются).

## Безопасность (важно)

- Публичные ноды — **чужие серверы**. TLS защищает содержимое страниц, но
  оператор ноды видит домены и время соединений, может блокировать/замедлять.
- **Не вводите банковские пароли/2FA/seed-фразы** через такие ноды и не
  оплачивайте ничего в браузере через них.
- Для входа в соцсети используйте вход по Google/OAuth или 2FA — токены в
  пределах TLS; но риск утечки остаётся у оператора ноды (метаданные, не пароль).
- Для **боевого автопостинга** лучше свой VPN/VPS (или API-токены с ограниченными
  правами); токены через публичную ноду передавать нежелательно.
- Ноды меняются: если `test` показывает 0/6 — обновите (`setup`).

## Ограничения

- Скорость/стабильность зависят от ноды (может быть медленно).
- UDP/QUIC через ноду не настроен (`udp: false`) — видео обычно работает по TCP.
- Нода требует перезапуска после перезагрузки: `setup` не нужен, достаточно
  `start` (конфиг уже сохранён).
- Для фонового автозапуска можно добавить launchd-агент (как у бэкапа) —
  скажи, сделаю.
