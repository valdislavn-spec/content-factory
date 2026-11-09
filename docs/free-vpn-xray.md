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


## Автозапуск (launchd, безопасно)

Прокси поднимается сам при входе в систему и восстанавливается, если нода умерла.

```bash
cd content-factory
bash scripts/install_proxy_schedule.sh              # установить
bash scripts/install_proxy_schedule.sh --uninstall  # удалить
```

Агент `com.contentfactory.free-proxy` запускает
`scripts/free_proxy_daemon.py` от **обычного пользователя** (не root).

Что делает демон:
- держит Xray на SOCKS `127.0.0.1:1080`;
- каждые 2 минуты проверяет доступ к x.com через прокси;
- после 3 неудач подряд перезапускает Xray и **находит новую ноду**;
- пишет события в `data/logs/free_proxy.log` (только служебные строки, без
  токенов и паролей).

### Почему это безопасно

- **Только localhost**: SOCKS слушает `127.0.0.1`, из локальной сети/интернета
  доступа к прокси нет.
- **Без root**: агент и Xray работают от пользователя, не меняют системные
  настройки и сетевые интерфейсы.
- **Системный прокси НЕ включается**: весь обычный трафик (банки, госуслуги,
  покупки) идёт напрямую; через ноду ходит только то, что вы сами направили
  (`--proxy-server` в Chrome, `--socks5-hostname` в curl).
- **TLS не ломается**: нода не может расшифровать HTTPS; видит только домены.
- **Логи локальные**, без содержимого запросов.
- Нода — публичная: не вводите банковские пароли и не оплачивайте покупки в
  браузере, направленном через прокси. Для чувствительного — обычный трафик.
- Остановить в любой момент:
  ```bash
  launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.contentfactory.free-proxy.plist
  ```

Проверка после установки:
```bash
../tools/markitdown-venv/bin/python scripts/free_proxy.py test
```

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

## Системный прокси на macOS (настроено 09.11.2026)

Прокси поднят в двух режимах и включён системно для Wi-Fi:

| Что | Адрес | Назначение |
|---|---|---|
| SOCKS5 | `127.0.0.1:1080` | curl `--socks5-hostname`, Telegram, старые клиенты |
| HTTP | `127.0.0.1:1081` | системный прокси macOS, Chrome/Safari, Playwright |
| Системный HTTP/HTTPS-прокси Wi-Fi | `127.0.0.1:1081` | включён (`networksetup`) |
| Автозапуск | launchd `com.contentfactory.free-proxy` | поднимает Xray при входе и после падения |

**Управление:**

```bash
bash scripts/mac_vpn.sh status    # состояние + проверка 6 сайтов
bash scripts/mac_vpn.sh on        # запустить Xray и включить системный прокси
bash scripts/mac_vpn.sh off       # выключить системный прокси (Xray остаётся)
bash scripts/mac_vpn.sh test      # проверить сайты через HTTP-прокси
bash scripts/mac_vpn.sh restart   # перезапустить Xray
```

**Bypass-лист** (идут напрямую, мимо публичной ноды): локальные сети, банки
(Сбер/Т-Банк/ВТБ/Альфа/Газпромбанк/Райффайзен), госуслуги/налог/mos.ru,
маркетплейсы (WB/Ozon), Яндекс/Мейл/Авито/VK/OK, GitHub CDN, Cloudflare Workers.
Остальной трафик — через ноду.

**Проверено после настройки:**
- `t.me`, `api.telegram.org`, `oauth.telegram.org`, `bsky.app`,
  `admin.adminhub.tools`, `x.com` — 200/302 через прокси (6/6);
- Telegram Bot API работает **с этой машины**: `getMe` → ok (бот `@Novyi0007Bot`),
  `getChatMemberCount` по каналам — ok;
- Chromium (Playwright) использует системный прокси: `t.me` открылся, AdminHub
  загрузился (можно входить через Telegram OIDC);
- автозапуск: агент `com.contentfactory.free-proxy` загружен (PID в `launchctl list`).

**Важно:**
- Нода публичная: оператор видит домены/время (TLS содержимое не раскрывает).
  Банковские/госуслуги — в bypass; не вводите пароли на сторонних сайтах
  без необходимости.
- `scripts/free_proxy.py setup` теперь сохраняет HTTP-inbound (порт socks+1),
  чтобы ротация ноды не ломала системный прокси.
- Отключить всё: `bash scripts/mac_vpn.sh off` + выгрузить агент:
  `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.contentfactory.free-proxy.plist`.
