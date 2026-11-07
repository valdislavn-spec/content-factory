# Фото-карточки постов

Каждый пост перед публикацией получает фирменную карточку-изображение
(1080×1350): она уходит в Telegram через `sendPhoto` вместо случайной
картинки из статьи.

## Типографика

- **Заголовок** — [Playfair Display](https://fonts.google.com/specimen/Playfair+Display)
  (variable, вес 850): крупный характерный serif, автоматически подбирает
  кегль под длину заголовка (до 5 строк).
- **Тело** — [Inter](https://fonts.google.com/specimen/Inter) (variable, 400):
  максимально читаемый гротеск, авто-перенос и обрезка по высоте с «…».
- Запасные шрифты: Georgia (заголовок) и Arial (тело) — macOS.
- Оба шрифта распространяются по лицензии SIL OFL, лежат в
  `assets/fonts/` вместе с текстами лицензий.

## Как это работает

1. `content_factory/cards.py` рисует PNG: градиент канала, круглый логотип
   (`assets/logos/<channel>.png`), название канала, дату и язык, плашку
   формата (DIGEST/NEWS/ANALYSIS), заголовок, тело, хэштеги и @канал.
2. Пайплайн вызывает `_attach_card()` после генерации поста и кладёт путь в
   `post.meta["card_path"]`; файл сохраняется в `data/outbox/cards/`.
3. Telegram-публикатор сначала пробует отправить карточку (`sendPhoto`
   multipart). Если карточки нет или загрузка не удалась — публикует как
   раньше: картинка статьи или текст.

## Настройки

`config/settings.yaml`:

```yaml
publishers:
  telegram:
    photo_card:
      enabled: true      # выключить: false
      width: 1080
      height: 1350
      body_chars: 640    # сколько символов тела помещать на карточку
```

Перегенерировать логотипы/обложки: `python scripts/make_logos.py`
(нужен Pillow; в Actions он ставится из `requirements.txt`).
