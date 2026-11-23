# /partners/ads/ — прайс на рекламу в Telegram-сетке

Сгенерировано из `ad-sales/inventory.json`:

```
python3 ad-sales/scripts/packages.py sync --yes
python3 ad-sales/scripts/rate_card.py --out content-factory/docs/partners/ads/index.html
```

Не редактировать HTML руками — правки в инвентаре и пере-генерация.
