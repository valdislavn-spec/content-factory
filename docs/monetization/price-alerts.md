# Авто-алерты по цене (BingX) → посты в каналы

Движок следит за ценой BTC/ETH (публичный BingX API, без ключа) и публикует
пост в крипто-каналы при **пробое уровня** или **быстром ходе**. Это дешёвый
способ поднять охваты и клики по рефералке: алерты выходят чаще обычных постов
и всегда с актуальной цифрой.

Пример (EN):

```
🚀 BTC (BTC/USDT) broke above $78,000 — now $78,120.50 (+2.31% / 24h).

Data: BingX · not financial advice.
#Bitcoin #BTC
```

ES-версия («superó los $78,000…») публикуется в `crypto-es`; язык берётся из
канала. Рассылка идёт через тот же Telegram-публикатор, что и обычные посты
(релей/токен те же).

## Конфиг: `config/price_alerts.yaml`

```yaml
interval_seconds: 60
state_path: data/price_alerts_state.json
channels_files: [config/channels.en.yaml, config/channels.es.yaml]
channels: [crypto-news, crypto-es]
rules:
  - symbol: BTC/USDT
    above: 78000          # алерт при пересечении вверх
    below: 73500          # алерт при пересечении вниз
    cooldown_minutes: 360
  - symbol: BTC/USDT
    move_percent: 2.5     # быстрый ход ±2.5% за окно
    move_window_minutes: 60
    cooldown_minutes: 120
```

- `above`/`below` срабатывают **только в момент пересечения** (если цена уже была
  выше уровня — повтора не будет).
- `move_percent` сравнивает с ценой `move_window_minutes` назад.
- `cooldown_minutes` — минимальный интервал между одинаковыми алертами.
- Состояние (последняя цена + время срабатывания) хранится в
  `data/price_alerts_state.json`, чтобы рестарт не давал дублей.

## Запуск

```bash
# один прогон без реальной публикации
python scripts/price_alerts.py --once --dry-run

# тестовый алерт (проверить текст/канал)
python scripts/price_alerts.py --sample --dry-run

# демон: проверка каждые 60 секунд
python scripts/price_alerts.py --loop

# только один канал
python scripts/price_alerts.py --once --channel crypto-news
```

Реальная публикация включается флагом **`--live`**: он выставляет
`CONTENT_FACTORY_DRY_RUN=false` только для процесса алертов, не меняя режим
остального завода. `--dry-run` наоборот принудительно включает dryrun.

```bash
python scripts/price_alerts.py --loop --live    # боевой режим
```

## Автозапуск (launchd, macOS)

```bash
bash scripts/install_price_alerts_schedule.sh            # установить
bash scripts/install_price_alerts_schedule.sh --uninstall
```

Агент `com.contentfactory.price-alerts` (уже установлен 08.11.2026):
- запускается как `scripts/price_alerts.py --loop --live` (боевой режим);
- `RunAtLoad` + `KeepAlive` — стартует при входе и перезапускается при падении;
- логи: `data/logs/price-alerts.log`;
- проверить: `launchctl print gui/$(id -u)/com.contentfactory.price-alerts`;
- рабочий каталог — репозиторий, поэтому `.env` подхватывается.

## Когда менять уровни

Пороги в конфиге — стартовые (BTC $78k/$73.5k, ETH $2.4k/$2.05k на 08.11.2026).
Раз в 1–2 недели двигайте их к текущей цене (±3–5%), иначе алерты будут
молчать или срабатывать слишком часто. Быстрый ход ±2.5–3% за час — хороший
баланс для крипты.

## Ограничения

- Polling раз в 60 с (а не WebSocket): для постов этого достаточно; если нужна
  секундная точность — можно перейти на WS BingX (есть Python SDK).
- Алерты не заменяют обычный контент-план: максимум 2–4 алерта в день на канал,
  cooldown это ограничивает.
- Не является инвестиционной рекомендацией; футер об этом напоминает.

## Реферальная строка в алертах

К алертам добавляется рефералка BingX **1 раз в 3 алерта** (на канал) с
маркировкой «ad · affiliate link» и гео-дисклеймером; хештеги остаются в конце.
Настройка — в `config/price_alerts.yaml`:

```yaml
affiliate_every_n: 3
affiliate:
  enabled: true
  link: "https://bingxdao.com/invite/WYYEGK/"
  disclaimer: "Ad · affiliate link. Not available in the US, UK, …"
```

Можно переопределить на конкретном канале блоком `affiliate:` в
`config/channels.*.yaml` (как в обычных постах). После одобрения Affiliate
Program замените `link` на 50%-ную affiliate-ссылку.
