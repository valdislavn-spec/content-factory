# Travel-монетизация: Travelpayouts + Aviasales (08.11.2026)

## Аккаунт Travelpayouts
- Вход: **Google SSO** (аккаунт `valdislav.n@gmail.com`), способ входа — «Continue with Google» на passport.travelpayouts.com.
- Account ID: **674170**, проект: `Valdislavn-spec` (Telegram).
- Кабинет: `https://app.travelpayouts.com/dashboard`
- Статус: Payout method не настроен (баланс $0) — для выплат добавить способ вывода.
- Подключённые программы: **Aviasales** (flights), AirHelp.
- Не подключены: Hotellook (отели), Klook, страховки, туры — можно join в «Programs catalog».

## Аффилиатные ссылки (Aviasales, инструмент Links)
Оригиналы:
- Общая: `https://aviasales.tpk.ro/0bCPUgFS`
- Бали: `https://aviasales.tpk.ro/rYaenwKl`
- Дубай: `https://aviasales.tpk.ro/n0Fu4qCV`

Короткие маски (is.gd):
- `https://is.gd/FlightsDeals` → общая
- `https://is.gd/BaliFlights` → Бали
- `https://is.gd/DubaiFlights` → Дубай

## Посты (опубликованы 08.11.2026, shareNow)
- **Bluesky** (187 зн.): Бали + Дубай, ссылка FlightsDeals —
  https://bsky.app/profile/did:plc:p67ksvae6f5gara4vueu7edo/post/3mzswwkuo7z22
- **X** (160 зн.): зимние направления + BaliFlights/DubaiFlights —
  https://twitter.com/NValdislav/status/2119483092930818147
- **Facebook** (400 зн.): Бали, Дубай, Лиссабон + FlightsDeals —
  https://facebook.com/865322629989875_122148510069054089

## Идеи дальше
1. Join Hotellook/Klook → hotel & activities links (выше комиссии).
2. Серия постов: «зимние направления» по 2–3 места с аффилиатными ссылками (Бали, Дубай, Лиссабон, Тбилиси, Стамбул).
3. Ставить subID по каналам (bsky/x/fb) в инструменте Links → трекинг по соцсетям.
4. Настроить payout method, иначе выплаты не пройдут.


## Однословные ссылки (08.11.2026)

Правило: короткие ссылки — **одно слово** после домена.

| Слово | Ссылка | Ведёт на |
|---|---|---|
| Flights | `https://is.gd/Flights` | Aviasales (общая) |
| BaliTrip | `https://is.gd/BaliTrip` | Aviasales Бали |
| DubaiTrip | `https://is.gd/DubaiTrip` | Aviasales Дубай |
| CryptoDigest | `https://is.gd/CryptoDigest` | t.me/HOOPY0007 |
| AINews | `https://is.gd/AINews` | t.me/AINEWS0007 |
| SportsNews | `https://is.gd/SportsNews` | t.me/SPORTNews0007 |
| ESCrypto | `https://is.gd/ESCrypto` | t.me/TechnologiesNews01 |
| ESNews | `https://is.gd/ESNews` | t.me/WORLDNews0007 |
| ESport | `https://is.gd/ESport` | t.me/SPORTSAnalytics007 |

Запланированные посты 19:16 и 21:16 обновлены на однословные ссылки (6 постов,
status: scheduled). Уже **отправленные** посты (17:16 и travel) редактировать
нельзя — API возвращает «Account is not allowed to perform this action on post»;
там остались прежние алиасы (FlightsDeals/BaliFlights/DubaiFlights/CryptoBlockchain).


## Перевыпуск travel-постов с однословными партнёрскими ссылками (08.11.2026)

- **Bluesky** (211 зн.): Бали → `is.gd/BaliTrip`, Дубай → `is.gd/DubaiTrip`, рейсы → `is.gd/Flights`
  https://bsky.app/profile/did:plc:p67ksvae6f5gara4vueu7edo/post/3mzsx5t5joz24
- **X** (143 зн.): Бали + Дубай с партнёрскими ссылками
  https://twitter.com/NValdislav/status/2119484113899921582
- **Facebook** (440 зн.): Бали, Дубай, Лиссабон + `is.gd/Flights`
  https://facebook.com/865322629989875_122148510351054089

Ссылки: `https://is.gd/Flights`, `https://is.gd/BaliTrip`, `https://is.gd/DubaiTrip`
(Travelpayouts / Aviasales, аккаунт ID 674170). Предыдущие версии постов
остались в лентах (отправленные посты API не редактирует/не удаляет).

## Aviasales на Facebook — проверка правил (08.11.2026)

В кабинете Travelpayouts (программа «Авиасейлс», `programs/100`):
- **Разрешённые способы продвижения:** Контент-проект — *любой канал*;
  Кэшбэк-проект — *любой канал*; Туристический бизнес — *любой канал*;
  Личные бронирования; Купоны/промокоды.
- **Арбитраж:** любая контекстная реклама запрещена; нельзя упоминать бренд/логотип
  в контекстной рекламе (такие продажи не оплачиваются).

**Вывод:** Facebook допустим (органические посты — это «любой канал»), запрет только
на контекстную рекламу и упоминание бренда в ней. Ставка 40% от дохода
(~1,1–1,3% стоимости билета), cookie 30 дней, учитываются десктоп/моб.сайт/приложение.

Опубликован FB-пост с партнёрской ссылкой:
- «Cheap flights alert ✈️» → `https://is.gd/Flights`
- https://facebook.com/865322629989875_122148527169054089

## Travelpayouts API (токен + маркер 674170, 08.11.2026)

- API-токен и маркер добавлены в `.env` (`TRAVELPAYOUTS_API_TOKEN`,
  `TRAVELPAYOUTS_MARKER=674170`), шаблон — в `.env.example`.
- Скрипт `scripts/travel_links.py`: берёт цены через API Travelpayouts
  (`/v1/city-directions`, `/v1/prices/cheap`) и строит аффилиатные ссылки
  Aviasales с маркером: `https://aviasales.ru/search/<ORIGIN><DDMM><DEST>1?marker=674170`.

Пример запуска:
```bash
.venv/bin/python scripts/travel_links.py --origin MOW --limit 5
```

Тестовый вывод (08.11.2026):
- MOW→LED 3 388 ₽ → https://aviasales.ru/search/MOW1011LED1?marker=674170
- MOW→AER 5 926 ₽ → https://aviasales.ru/search/MOW0911AER1?marker=674170
- MOW→EVN 14 723 ₽ → https://aviasales.ru/search/MOW2011EVN1?marker=674170

Важно: маркер работает на aviasales.ru (RU-аудитория). Для EN-каналов
(US/global) нужен отдельный маркер под aviasales.com или другой travel-бренд.

## Серия «Winter sun» (08.11.2026, опубликовано)

- **Bluesky** (189 зн.): Лиссабон / Дубай / Бали → `https://is.gd/Flights`
  https://bsky.app/profile/did:plc:p67ksvae6f5gara4vueu7edo/post/3mztdxg7lah2o
- **X** (154 зн.): шортлист зимнего солнца → `https://is.gd/Flights`
  https://twitter.com/NValdislav/status/2119541759562731646
- **Facebook** (428 зн.): 3 направления с описанием + `https://is.gd/Flights`
  https://facebook.com/865322629989875_122148528393054089

Формат: короткий список направлений, температура/чем заняться, одна словесная
партнёрская ссылка. Подходит для серии (менять города и сезон).

## Benable: Pinterest-карточки с QR-пинами (09.11.2026)

Сделаны пины 1000×1500, где партнёрская ссылка **вшита в изображение** (QR +
короткий адрес + пометка «Ad · affiliate link»), и опубликованы карточками в Benable.

| Пин | QR ведёт на | Публичный файл |
|---|---|---|
| Bali on a budget | is.gd/BaliTrip | `assets/pins/qr/bali-budget-qr.png` |
| Dubai weekend | is.gd/DubaiTrip | `assets/pins/qr/dubai-weekend-qr.png` |
| 3 winter escapes | is.gd/Flights | `assets/pins/qr/winter-sun-qr.png` |
| Europe under $300 | is.gd/EuropeTrip | `assets/pins/qr/europe-under-300-qr.png` |

Benable-списки (аккаунт Huk007):
- Dubai weekend → +«Dubai Trip» (6 items): https://benable.com/Huk007/dubai-weekend-a4
- Travel essentials → +«Europe under $300», +«3 winter escapes» (12 items):
  https://benable.com/Huk007/travel-essentials-i-actually-use-ad
- Bali on a budget → +«Bali Trip» (6 items): https://benable.com/Huk007/bali-on-a-budget-c3
- AI & Crypto tools → +«Bali Trip» (3 items; можно перенести/удалить позже):
  https://benable.com/Huk007/ai-crypto-tools-i-use

Каждая карточка: фото нашего QR-пина (импорт по ссылке из GitHub Pages),
заметка с описанием и «Ad: affiliate link», ссылка карточки = партнёрская is.gd.

Pinterest: готов `docs/pinterest-import-qr.csv` (Title, Media URL, Link, Description,
board «Travel ideas») — импортировать через Pinterest Bulk create pins.
Скрипт генерации: `scripts/build_qr_pins.py` (Pillow+segno, рендер в Docker).

## QR-пины travel-essentials (09.11.2026)

Сгенерированы и опубликованы (Benable + CSV для Pinterest) ещё 3 пина:

| Пин | Партнёрка | Ссылка (QR) | Список Benable |
|---|---|---|---|
| Travel eSIM | Saily (`saily.tpk.ro/r5oQ96LR`) | is.gd/ESimDeal | Travel essentials I actually use |
| Car rental, no surprises | Localrent (`localrent.tpk.ro/ZZ36vFV4`) | is.gd/CarRental | Travel essentials I actually use |
| Flight delayed? up to €600 | Compensair (`compensair.tpk.ro/4klXfGpD`) | is.gd/Compensair | Travel essentials (через хаб `go/04-travel-insurance-mistakes.html`) |

Benable «Travel essentials I actually use» — 15 items (добавлены карточки eSIM, аренды авто,
insurance/compensation; остальные пины: Europe under $300, 3 winter escapes).
Всего QR-пинов: 7 (`assets/pins/qr/`), CSV для Pinterest: `docs/pinterest-import-qr.csv`
(7 строк: Media URL + Link + Description).

## Редизайн пинов v2 — по best practices Pinterest 2026 (09.11.2026)

Источник практик: [Pin design 2026 — verified](https://github.com/social-media-skills/skills/blob/main/skills/pinterest-pin-design/references/pin-design-2026-reality.md)
(2:3 1000×1500; ≤6 слов крупным bold-оверлеем; текст в верхней трети;
5–8% поля; бренд НЕ в правом нижнем углу; lifestyle/outcome imagery;
свежие пины = новый дизайн, а не репін).

Что изменено в v2 (`assets/pins/qr-v2/`, скрипт `scripts/build_qr_pins_v2.py`):
- светлая редакционная палитра (крем/чернила) вместо тёмного градиента;
- крупный Playfair-заголовок ≤6 слов + ключевик в оверлее и в title;
- keyword-пилюля справа сверху, бренд «VALDISLAV · TRAVEL NOTES» слева сверху;
- иллюстративная сцена-«фото» (исход/пейзаж), а не стерильный фон;
- QR и короткая ссылка — слева снизу (не под иконками Pinterest справа снизу);
- CTA-кнопка «Find flights →», дисклеймер «Ad · affiliate link»;
- поля ~6%, критичное не у краёв.

CSV обновлён на v2: `docs/pinterest-import-qr.csv` (7 строк, Media URL → `/assets/pins/qr-v2/...`).
Старые v1 остаются в `/assets/pins/qr/` (для A/B и «fresh pins» — это разные дизайны одного URL).
