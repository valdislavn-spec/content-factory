# Travelpayouts: все подключённые программы и их API

Аккаунт: marker **674170**; проекты: **597635** (Telegram), **597672** (сайт).
API-токен: `TRAVELPAYOUTS_API_TOKEN` (локально `.env`; добавить в GitHub Secrets).
Ссылки генерируются API: `POST https://api.travelpayouts.com/links/v1/create`
(заголовок `X-Access-Token`, до 10 ссылок/запрос, 100 запросов/мин).

Скрипт: `python scripts/tp_all_links.py --write` → обновляет `config/affiliate_links.yaml`.

## Подключённые программы (11)

| Программа | Партнёрская ссылка | API программы |
|---|---|---|
| Aviasales | https://aviasales.tpk.ro/2ZW95Xpf | Flight Data API (`/v2/prices/latest`, `/v1/prices/cheap`, `/v1/city-directions`), Flight Search API, partner links API |
| Tiqets | https://tiqets.tpk.ro/ia533rks | Day tours API / partner links |
| Klook | https://klook.tpk.ro/v1zmjFuk | Day tours API / partner links |
| Saily | https://saily.tpk.ro/hQujMoYq | eSIM data / partner links |
| Airalo | https://airalo.tpk.ro/nGPgTNDu | eSIM data / partner links |
| Yesim | https://yesim.tpk.ro/aU7AT4LC | eSIM data / partner links |
| Kiwitaxi | https://kiwitaxi.tpk.ro/EuN6AoPO | Transfers / partner links |
| Compensair | https://compensair.tpk.ro/yhsBLUP1 | Claims / partner links |
| AirHelp | https://airhelp.tpk.ro/WbJKruUg | Claims / partner links |
| Welcome Pickups | https://tpk.ro/a66T8gV7 | Transfers / partner links |
| WeGoTrip | https://wegotrip.tpk.ro/JpsOLmuW | Day tours API / partner links |

## Не подключены (14) — можно Join в кабинете

hotellook, booking, getyourguide, trip, agoda, expedia, hotels, discovercars,
rentalcars, omio, 12go, musement, viator, cheapoair.
Ошибка API: `trs is not subscribed for brand` → программа не подключена к проекту.

## Куда уже встроено

- **Buffer-посты (travel)**: строка `Ad: <program link>` ротируется по дню через
  все 11 программ (`config/affiliate_links.yaml`), поэтому каждый пост несёт
  партнёрскую ссылку и каждый день — новую программу.
- **go-страницы** (`docs/go/*.html`) — партнёрские ссылки для пинов.
- **Fediverse/Mastodon** — travel-офферы (Aviasales, Airalo, Yesim, Kiwitaxi).
- **Price alerts** — BingX-ссылка (не Travelpayouts).

## Ограничения

- Kiwi.com, HolidayTaxis, Ticketmaster, Priority Pass, Indrive не поддерживаются links API.
- Для контекстной рекламы Aviasales бренд упоминать нельзя (см. travel-monetization.md).
- Маркер 674170 привязан к RU/global Aviasales (aviasales.ru); для US-аудитории
  лучше отдельный маркер под aviasales.com (проверить в кабинете).
