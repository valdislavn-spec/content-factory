# Партнёрские программы: Travelpayouts и альтернативы

Дата: 08.11.2026. Цель — монетизировать пины/посты ссылками на travel-сервисы.
Текущий аккаунт: Travelpayouts **marker 674170**, projects: telegram 597635, website 597672.

## 1. Travelpayouts: каталог (45 программ)

Уже подключены к проекту и дают партнёрские ссылки (22):

| Программа | Комиссия | Ссылка-пример |
|---|---|---|
| Klook | 2–5% | https://klook.tpk.ro/xqUojI5K |
| Saily (eSIM) | 15% | https://saily.tpk.ro/r5oQ96LR |
| Yesim (eSIM) | 18% | https://yesim.tpk.ro/6FFBmBAp |
| Airalo (eSIM) | — | https://airalo.tpk.ro/nljrSdgG |
| Kiwitaxi (трансфер) | 9–11% | https://kiwitaxi.tpk.ro/xmQYmqIl |
| Localrent (аренда авто) | — | https://localrent.tpk.ro/ZZ36vFV4 |
| QEEQ (аренда авто) | — | — |
| DiscoverCars | 23–54% (не подключён) | — |
| Tiqets (билеты) | — | https://tiqets.tpk.ro/ufgJDVmO |
| WeGoTrip (аудиогиды) | — | https://wegotrip.tpk.ro/VdRdU8Fp |
| GetTransfer | — | https://gettransfer.tpk.ro/bVVZnmUN |
| Welcome Pickups | — | https://tpk.ro/kTevGAQP |
| RadicalStorage (камеры хранения) | — | — |
| AirHelp / Compensair (компенсации) | — | https://compensair.tpk.ro/4klXfGpD |
| EconomyBookings | — | — |
| GetRentacar | — | — |
| BikesBooking | — | — |
| Intui (багаж) | — | — |
| KKday | 1–3% | — |
| Drimsim (eSIM) | — | — |
| Gocity (City Pass) | — | — |
| Kiwi (авиабилеты) | — | https://kiwi.tpk.ro/RJINNJJm |

**Не подключены (нужно нажать Join в кабинете Travelpayouts):**

| Программа | Комиссия | Почему интересна |
|---|---|---|
| Booking.com | 3–5% + €1.5 flights | максимальный спрос на отели |
| GetYourGuide | 8% | экскурсии/туры — высокая конверсия |
| Viator | 8% | туры, высокий EPC |
| Agoda | 1–6% | Азия/ЛатАм отели |
| Expedia | 1.35–3.6% | отели+авиа, глобально |
| Trip.com | 1–5.5% | отели/билеты, Азия |
| Tripadvisor Experiences | 8% | туры |
| Traveloka | 0.36–3.6% | Юго-Восточная Азия |
| DiscoverCars | 23–54% | аренда авто — самая высокая ставка |

Подключение: `app.travelpayouts.com` → Programs catalog → найти бренд → **Join** (часть брендов одобряет мгновенно, часть — вручную).

## 2. Альтернативные сети (аккаунты уже есть)

| Сеть | Аккаунт | Статус | Что даёт |
|---|---|---|---|
| **MyLead** | Vald001 | logged_in | 1000+ офферов: страховки, eSIM, отели, CPA-финансы |
| **Admitad** | valdislav.n | logged_in (verification pending: нужен @adspace_verification_bot админом канала) | AliExpress, Trip.com, отели, авиа, страховки |
| **N1 Partners** | valdislav.n | login rejected (2FA/локаут) | казино/беттинг — **не используем** (репутация) |
| **CJ (CJ Affiliate)** | нет аккаунта | — | Booking.com (официальная программа), агентства |
| **Impact** | нет аккаунта | — | Expedia, Viator, Travelodge и др. |
| **Partnerize** | нет аккаунта | — | GetYourGuide, Agoda |
| **Awin** | нет аккаунта | — | Booking.com (в некоторых гео), бренды |

## 3. Прямые программы (без агрегатора)

- **SafetyWing** (страховка путешественника) — affiliate через их сайт.
- **World Nomads / Heymondo** — travel insurance, часто через Impact/Awin.
- **Rentalcars / DiscoverCars** — аренда авто (DiscoverCars есть в Travelpayouts).
- **Klook / KKday** — уже в Travelpayouts.
- **Airbnb** — публичной affiliate-программы нет (только через партнёрства/агентства).

## 4. Что делаем дальше

1. Подключить в Travelpayouts: Booking.com, GetYourGuide, Viator, DiscoverCars, Agoda (5 брендов = покрытие отели/туры/авто).
2. Сгенерировать ссылки через API (`content_factory/integrations/travelpayouts.py`), создать `/go/<slug>` страницы на хабе.
3. Новые пины (по мере подключения): отели, туры/экскурсии, аренда авто, eSIM, трансферы, компенсации.
4. Проверить MyLead/Admitad на офферы страховок и аренды (CPA-выплаты часто выше).

## 5. Комплаенс

- Пометка `Ad · affiliate link` обязательна (FTC / Pinterest).
- Беттинг/казино не берём; для финансов — «not investment advice».
- В Travelpayouts заполнить **Legal requirements (реклама)** и **Payout method**, иначе выплаты не начисляются.
