# Размещение ссылок на каналы сети

Дата: 08.11.2026. Каналы: 6 (3 EN + 3 ES). Этот файл — реестр всех мест,
куда положены ссылки, и чек-лист для тех мест, где нужен аккаунт владельца.

## Ссылки каналов

| Канал | Язык | Ссылка | Подписчики на 08.11 |
|---|---|---:|---:|
| Crypto & Blockchain (главный) | EN | https://t.me/HOOPY0007 | 3 666 |
| AI News | EN | https://t.me/AINEWS0007 | 3 |
| US Sports News | EN | https://t.me/SPORTNews0007 | 3 |
| ES Crypto & Blockchain | ES | https://t.me/TechnologiesNews01 | 3 |
| ES AI News | ES | https://t.me/WORLDNews0007 | 3 |
| ES Sports News | ES | https://t.me/SPORTSAnalytics007 | 3 |

Единая ссылка-хаб (для био внешних площадок):
**https://valdislavn-spec.github.io/content-factory/** — лендинг со всеми шестью
каналами, исходник: `docs/index.html`.

## 1. Что размещено автоматически

### Telegram — описание канала (About)

У всех 6 каналов в описании есть блок ссылок на каналы своей языковой ветки:

- EN: `🌐 Network: AI News @AINEWS0007 · Crypto & Blockchain @HOOPY0007` и т.д.
- ES: `🌐 Nuestra red: ES Crypto & Blockchain @TechnologiesNews01 · ...`

Источник правды: `description` в `config/channels.en.yaml` /
`config/channels.es.yaml`; применяется workflow `apply-profile` (Bot API
`setChatDescription`). Ограничение Telegram — 255 символов, все описания
укладываются (133–227).

### Telegram — закреплённый пост

У всех 6 каналов в закрепе блок «🌐 Our network» / «🌐 Nuestra red» с прямыми
`https://t.me/...`-ссылками на каналы ветки (по 2 ссылки на канал).

- Тексты: `config/pinned/en.yaml`, `config/pinned/es.yaml`.
- message_id закрепов: `config/pinned/ids.yaml`.
- Обновление: workflow `edit-pinned` (после фикса chat_id берётся из
  `TELEGRAM_CHAT_ID_*`, поэтому работают и ES-каналы).

### Telegram — кросс-промо-посты

`config/cross_promo.yaml`, workflow `cross-promo` (Вт/Пт 15:00 UTC):
crypto-news → AI News и US Sports News, со ссылкой в каждом тексте.
Остальные связки выключены осознанно: у каналов по 3 подписчика — промо из них
ничего не даёт. Включать при 500+ подписчиков.

### Репозиторий и веб

- `CHANNELS.md` в корне публичного репозитория — все 6 ссылок.
- GitHub Pages: `docs/index.html` → https://valdislavn-spec.github.io/content-factory/
- `homepage` публичного репозитория указывает на хаб.
- Промо-материалы со ссылками: `docs/promo/catalog-package.md`,
  `docs/promo/promo-texts-2026-11.md`, `docs/promo/vp-outreach.md`.

### Проверка

```bash
# описания и закрепы вживую
python scripts/edit_pinned.py --language en --dry-run
python scripts/edit_pinned.py --language es --dry-run
```

## 2. Куда положить ссылки (нужен твой аккаунт)

| Площадка | Что делаем | Что вставить | Статус |
|---|---|---|---|
| TikTok | био + закреп-комментарий | хаб-ссылку (единственная кликабельная) | ☐ |
| YouTube | описание канала + описание видео | хаб + 6 ссылок в описании канала | ☐ |
| X/Twitter | bio + website + закреп-твит | website = хаб; ссылки — в закрепе | ☐ |
| Instagram | био (1 ссылка) | хаб-ссылка | ☐ |
| VK | описание сообщества, ссылки, закреп | все 6 ссылок | ☐ (нет токена VK) |
| Reddit | профиль + закреп в профиле | хаб; в сабах — только по правилам | ☐ |
| Личный Telegram | био + закреп в личном канале | @-упоминания каналов | ☐ |
| Каталоги | карточки каналов | `docs/promo/catalog-package.md` | ☐ (6 каталогов) |
| Email / подпись | подпись писем | хаб-ссылка | ☐ |
| GitHub profile | README профиля | хаб + 6 ссылок | ☐ (опционально) |

### Готовые тексты

**TikTok / Reels / Shorts (bio, EN):**
`Crypto, AI and US sports news — no fluff. All channels → https://valdislavn-spec.github.io/content-factory/`

**TikTok / Reels / Shorts (bio, ES):**
`Cripto, IA y deporte en español. Todos los canales → https://valdislavn-spec.github.io/content-factory/`

**YouTube, описание канала (EN):**
```
US crypto, AI and sports news — daily, sourced, no hype.
Crypto & Blockchain: https://t.me/HOOPY0007
AI News: https://t.me/AINEWS0007
US Sports News: https://t.me/SPORTNews0007
All channels: https://valdislavn-spec.github.io/content-factory/
```

**X/Twitter, закреп-твит:**
```
Daily crypto, AI and US sports news in Telegram:
₿ https://t.me/HOOPY0007
🤖 https://t.me/AINEWS0007
🏈 https://t.me/SPORTNews0007
ES: https://t.me/TechnologiesNews01 · https://t.me/WORLDNews0007 · https://t.me/SPORTSAnalytics007
All → https://valdislavn-spec.github.io/content-factory/
```

**Личный Telegram, био:**
`Автор сети каналов: ₿ @HOOPY0007 · 🤖 @AINEWS0007 · 🏈 @SPORTNews0007`

## 3. Атрибуция

- UTM-метки для `t.me` не работают. Варианты: отдельные invite-ссылки
  (`t.me/+hash`) под каждую площадку или бот-редирект с `?start=<source>`.
  Bot API не отдаёт статистику по invite-ссылкам — смотреть в админке канала;
  для быстрой оценки достаточно дельты подписчиков за 48 ч (growth-report).
- Формула: `CPR = расходы / (подписчики после − подписчики до)`.

## 4. Чек-лист

- [x] описания 6 каналов со ссылками (Bot API, вживую)
- [x] закрепы 6 каналов с блоком «Наша сеть» (Bot API, вживую)
- [x] кросс-промо crypto → AI/Sports
- [x] публичный хаб-лендинг (GitHub Pages)
- [x] CHANNELS.md в публичном репозитории
- [ ] TikTok bio
- [ ] YouTube ссылки
- [ ] X bio + закреп-твит
- [ ] Instagram bio
- [ ] VK (нужен токен/группа)
- [ ] каталоги: TGStat, Telemetr, Tlgrm.eu, GramPedia, TelegramChannels.me,
      GruposTelegramLatAm
- [ ] личный профиль Telegram
- [ ] GitHub profile README (опционально)

## 5. Поддержание

После правок `config/channels.*.yaml` запускать workflow `apply-profile`
(language: en/es), после правок `config/pinned/*.yaml` — `edit-pinned`
(language: en/es). Ссылки в описаниях и закрепах должны совпадать с
`config/pinned/ids.yaml` и актуальными @username каналов.
