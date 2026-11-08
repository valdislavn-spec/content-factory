# Форматы постов в Buffer: X / Facebook / Bluesky

С 08.11.2026 `scripts/buffer_queue.py` собирает **разные посты под каждую сеть**,
а не один универсальный текст. Стиль задаётся в `config/buffer.yaml` → `niches`
(эмодзи, хэштеги, CTA, вопрос для Facebook).

## Что рекомендуют источники

### X (Twitter)
- **280 символов**, но выше вовлечение у постов 180–260 и длинных нативных (800–2500): хук должен попасть в первые ~240 символов до «Show more» ([twitter_playbook](https://github.com/danicat/skills/blob/main/writing/social-copy/references/twitter_playbook.md)).
- **Хэштеги практически не дают охвата**: алгоритм индексирует текст семантически; 0 хэштегов (максимум 1 под событие), 3+ — спам-дампенер.
- Ссылки не штрафуются, если текст содержательный (не «ленивая ссылка»); ссылку лучше в конце.
- Эмодзи — точечно; вопрос/цифра в первой строке; отвечать на первые ответы в течение 15–30 минут.
- Держать хук < 120 символов, 1 мысль на пост.

### Facebook (Page)
- **Первые 80 символов** решают: мобильный фид обрезает по «See more» ([facebook ref](https://github.com/forsvn-labs/conquistador/blob/110d99cd41c0203430688cab2a59126f6782739e/skills/conquistador/references/social-publishing-handoff/references/platforms/facebook.md)).
- Короткие посты (< 80 символов) дают **~66% больше вовлечения**, но для гайдов работает схема: короткий хук → 2–3 пункта пользы → вопрос → ссылка.
- **0–2 хэштега**, 0–2 эмодзи; 5+ — читается как спам.
- Ссылки немного подавляют органический охват: текст должен стоять сам, ссылка — в конце.
- Первые **60–90 минут** — решающие: комментировать/отвечать, провоцировать обсуждение, а не лайки ([facebook heuristics](https://github.com/sergebulaev/facebook-skills/blob/main/references/algorithm-heuristics.md)).
- Никакого engagement bait («лайкни, если согласен»).

### Bluesky
- **300 символов** жёстко; 1–3 хэштега, ссылки — не больше одной ([bluesky ref](https://github.com/forsvn-labs/conquistador/blob/110d99cd41c0203430688cab2a59126f6782739e/skills/conquistador/references/social-publishing-handoff/references/platforms/bluesky.md)).
- **Alt-текст к картинкам — культурная норма** (без него ругают).
- Дискавери — репосты/ответы и попадание в custom feeds; кросспост «как в X» без адаптации не любят.
- Никакого кликбейта и нагромождения ссылок.

## Наши шаблоны

- **X**: хук (≤120) → первое предложение пользы → `CTA + короткая ссылка`; **0 хэштегов**.
- **Bluesky**: 🧳 хук → польза → `CTA + ссылка` → 2–3 хэштега; до 300 символов.
- **Facebook**: хук (≤80) → 2–3 пункта «•» → вопрос → ссылка → 0–2 хэштега.
- UTM: для X/Bluesky оставляем только `utm_source` (лимиты), для Facebook — полный набор.

Проверка без публикации:

```bash
python scripts/buffer_queue.py --date 2026-11-08
```

## Картинка и ссылки (с 08.11.2026)

- **Картинка статьи** (пина, `image_url`) прикладывается к посту через
  Buffer `assets: [{image: {url}}]` (схема из [Create Image Post](https://developers.buffer.com/examples/create-image-post.html)).
  Картинка Telegram-канала больше не используется.
- **Ссылка на статью** — для travel-пинов это **партнёрская ссылка Travelpayouts**
  (`config/travelpayouts.yaml` → `pins.<slug>.partner_url`, аккаунт 674170 / проект 597635);
  для остальных — `go/<slug>.html` или hub. Длинные ссылки сокращаются TinyURL.
- **Ссылка на канал** — `links.channel_default` / `niche_channels` в конфиге,
  подставляется в каждый пост (`Telegram: https://t.me/…`).
- Длинные ссылки сокращаются (`links.shorten: true`), лимиты X/Bluesky при этом соблюдаются.

## Что можно улучшить дальше

1. **Alt-текст**: схема Buffer в примере не показывает `altText`; если появится — добавить (важно для Bluesky).
2. **A/B**: чередовать CTA («Full guide:» vs «Save this:») и замерять клики по UTM.
3. **Время**: Buffer сам ставит в очередь; при ручном расписании — X утро, FB 13:00–15:00,
   Bluesky — по активности аудитории.
