# Фабрика пинов для рекламных/партнёрских ссылок

Генератор эффективных Pinterest-пинов (1000×1500) для travel и других ниш:
заголовок, подзаголовок, 3–4 буллета, CTA-кнопка, партнёрская ссылка и
обязательная пометка **Ad · affiliate link**. Каждый пин — PNG + JSON с готовым
payload для `POST /v5/pins`.

## Как это устроено

| Компонент | Файл |
|---|---|
| Рендер пина (Pillow, Playfair + Inter) | `content_factory/integrations/pins.py` |
| Генерация из конфига | `scripts/generate_pins.py` |
| Публикация в Pinterest (API v5) | `scripts/post_pins.py` |
| Конфиг ниш, текстов и ссылок | `config/pins.yaml` |
| Ежедневная генерация | `.github/workflows/pins-generate.yml` |

### Фоны

- **Hugging Face Inference API**: модель `black-forest-labs/FLUX.1-schnell`
  (`HUGGINGFACE_API_KEY` в secrets). Промпт — поле `image_prompt` в конфиге.
- Если ключа нет/модель недоступна — брендовый градиент (никогда не падает).

### Хранение и публичные URL

PNG и JSON коммитятся в `docs/assets/pins/<YYYY-MM-DD>/` и автоматически
публикуются на GitHub Pages:
`https://valdislavn-spec.github.io/content-factory/assets/pins/<date>/<file>.png`
— этот URL идёт в Pinterest как `media_source.image_url`.

## Запуск

```bash
# локально (2 пина, ротация, без AI-фонов)
python scripts/generate_pins.py --out docs/assets/pins --rotate 2 --no-ai

# в Actions: pins-generate → Run workflow
#   post=true — после генерации попробовать опубликовать в Pinterest
```

## Эффективные пины: практика

1. **Формат 2:3 (1000×1500)**, текст читается в превью; 1 идея = 1 пин.
2. **Заголовок ≤ 6 слов**, цифры и конкретика («Europe for under $300»).
3. **Текст на картинке** дублирует идею, а не весь текст поста.
4. **Свежие фоны** — не публикуйте один и тот же креатив десятки раз.
5. **Ключевые слова** в title/description (Pinterest — поисковик).
6. **Ссылка** — на лендинг/партнёрскую страницу, **с пометкой Ad**.
7. **2–4 пина в день**, разнесённые по времени; не спамить.
8. **Claim your website** в Pinterest (HTML-тег или DNS) — даёт rich pins и
   доверие; наш домен уже на GitHub Pages.

## Партнёрские программы (travel)

Нужен свой аккаунт и одобрение — ссылка вставляется в `link` пина:

- **Travelpayouts** — агрегатор: Booking.com, Kiwi.com, GetYourGuide, Viator,
  Hotels.com, Aviasales (одна регистрация).
- **Expedia Group** — через Impact.
- **GetYourGuide** — через Partnerize.
- **Viator** — через Impact.
- **Booking.com** — напрямую или через Travelpayouts.

Для других ниш: crypto/биржи (нужна лицензия/дисклеймер, не инвестсовет),
AI-сервисы (реф-программы), спорт (18+).

## Юридическое

- Пометка `Ad` / «affiliate link» **обязательна** (FTC, Pinterest policy).
- Никаких «гарантированных заработков» и фейковых скидок.
- Обещания в пине должны совпадать с тем, что на лендинге.
- Для беттинга/финансов — 18+ и «not investment advice».

## Источники/библиотеки

- [Pillow](https://github.com/python-pillow/Pillow) — рендер пинов.
- [Hugging Face Inference API](https://huggingface.co/docs/api-inference) —
  FLUX.1-schnell / SDXL фоны.
- [Postiz](https://github.com/gitroomhq/postiz-app) — если позже понадобится
  UI-календарь и мультиплатформенный постинг (Pinterest поддерживается).
- [n8n](https://github.com/n8n-io/n8n) — альтернатива для визуальных воркфлоу.
