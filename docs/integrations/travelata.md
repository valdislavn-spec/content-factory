# Travelata: API пакетных туров (Travelpayouts campaign 18)

Дата: 08.11.2026. Аккаунт: Travelpayouts marker **674170**, проект **597672** (Valdislavn-spec).
Страница программы: https://app.travelpayouts.com/programs/18/about?source=597672
Комиссия: **3,8–7%** от суммы бронирования, cookie **180 дней**.

## Что даёт

- реальные цены на пакетные туры (отель + перелёт) в реальном времени;
- справочники: страны, курорты, отели, категории, питание, города вылета;
- ссылки на страницы бронирования Travelata (конвертируются в партнёрские).

## Доступ

1. Проект должен быть подключён к программе Travelata (campaign 18).
   Сейчас: **запрос на проверку проекта можно отправить после 9 ноября 2026**.
2. После подключения — запрос доступов API в поддержку Travelpayouts:
   `support.travelpayouts.com/hc/ru/requests/new` (указать цель использования и площадки),
   либо форма Travelata: https://forms.gle/4GCqGxJcFyEWfxs78
3. Travelata выдаёт **логин и пароль** (HTTP Basic Auth) индивидуально.

## API

- База: `https://api-gateway.travelata.ru`, все пути с префиксом `/partners`.
- Авторизация: `Authorization: Basic base64(login:password)`.
- Ответ: `{"success": true, "result": ...}`.
- Лимиты: заголовки `X-RateLimit-*`, при превышении 429.
- Массивные параметры — со скобками: `countries[]=92`, `resort[]=2161`.

### Эндпоинты

| Запрос | Назначение |
|---|---|
| `GET /partners/directory/countries` | страны |
| `GET /partners/directory/resorts?country[]=92` | курорты |
| `GET /partners/directory/hotels?resort[]=1` | отели |
| `GET /partners/directory/hotelCategories` | категории отелей |
| `GET /partners/directory/meals` | типы питания |
| `GET /partners/directory/departureCities` | города вылета |
| `GET /partners/statistic/cheapestTours` | самые дешёвые туры (реальное время) |

`cheapestTours` обязательные: `countries[]`, `departureCity`, `touristGroup[adults]`,
`checkInDateRange[from]`, `checkInDateRange[to]` (окно ~30 дней).
Опционально: `touristGroup[kids]`, `nightRange[from/to]`, `resorts[]`, `meals[]`, `hotelCategories[]`.

## Реализация в репозитории

- `content_factory/integrations/travelata.py` — клиент API + парсер недельного фида
  (UTF-16, tab-separated: Страна, Курорт, Отель, Средняя цена, взрослые, ночи, ссылка).
- `scripts/travelata_tours.py` — вывод дешёвых туров (API) или сводка по фиду (`--feed`).
- `tests/test_travelata.py` — тесты кодирования параметров и парсера фида.

Переменные окружения (после получения доступов):

```
TRAVELATA_LOGIN=...
TRAVELATA_PASSWORD=...
```

## План использования

1. После одобрения проекта (после 9 ноября) — запросить доступы API.
2. Ежедневный/еженедельный сбор: топ-5 дешёвых туров по популярным странам
   (Турция, Египет, ОАЭ, Таиланд, Абхазия) из Москвы/Казахстана.
3. Посты/пины: «Тур в Анталью 7 ночей — от N ₽», ссылка через `/go/<slug>` →
   партнёрская ссылка Travelpayouts (campaign 18).
4. Недельный фид — источник «популярных направлений» для тревел-раздела сайта
   (`/travel/`), что также повышает шансы на одобрение программ.
