# Реестр реф-ссылок по каналам (монетизация)

Дата: 08.11.2026. Статус: **черновик** — ссылки добавляются после входа в кабинеты.
Правило: в посте/закрепе раскрытие «реклама · партнёрская ссылка», без обещаний
доходности и «гарантий» (см. `docs/legal.md`).

## 1. Список по каналам (что и куда ставим)

| Канал | Язык/аудитория | Приоритетные программы | Куда ставим |
|---|---|---|---|
| **crypto-news** (`@HOOPY0007`, ~3.7k) | EN / US | MEXC, Bybit, Bitget, Kraken, Writesonic | закреп «Полезное» + 1 реф-пост на 5 обычных |
| **ai-news** (`@AINEWS0007`) | EN / US | Writesonic, Synthesia, ElevenLabs, NordVPN (Admitad/MyLead) | закреп «Инструменты» + обзорные посты |
| **sport-news** (`@SPORTNews0007`) | EN / US | 1xBet (1xPartners), N1 Partners | закреп «Партнёры» + осторожные посты 18+ |
| **crypto-es** (`@TechnologiesNews01`) | ES / LatAm | Hotmart (курсы), Bitget, MEXC | закреп + реф-пост раз в 5 |
| **tech-ai-es** (`@WORLDNews0007`) | ES / LatAm | Hotmart (AI-курсы), Writesonic | закреп + обзор AI-инструментов |
| **futbol-es** (`@SPORTSAnalytics007`) | ES / LatAm | 1xBet, N1 Partners | закреп + посты 18+ |

## 2. Программы: где брать реф-ссылку

| Программа | Тип | Аккаунт | Реф-ссылка | Статус |
|---|---|---|---|---|
| Admitad | CPA-сеть | ✅ есть | ⏳ нужен вход | войти в кабинет |
| MyLead | CPA-сеть (VPN) | ✅ есть | `https://mylead.global/r/dJ67Qo` | вход выполнен (Vald001) |
| Travelpayouts | CPA-сеть | ✅ есть | ⏳ | вход через **Google** |
| N1 Partners | iGaming CPA | ✅ есть | ⏳ | вход n1.partners |
| collaborator.pro | площадка | ✅ есть | ⏳ | вход collaborator.pro/login |
| UpPromote | affiliate-платформа | ✅ есть | ⏳ | app.uppromote.com/login |
| Hotmart | digital (ES) | ✅ есть | ⏳ | app.hotmart.com/login |
| MEXC | биржа | ✅ есть | ⏳ | mexc.com → Referral |
| KuCoin | биржа | ✅ есть | ⏳ | kucoin.com/affiliate |
| Bybit | биржа | ✅ есть | ⏳ | partner.bybit.com |
| Bitget | биржа | ✅ есть | ⏳ | affiliates.bitget.com |
| Kraken | биржа | ✅ есть | ⏳ | kraken.com/affiliate |
| 1xPartners (1xBet) | беттинг | ✅ есть (1xbet) | ⏳ | 1xpartners.com/login |
| **Writesonic** | AI SaaS | ✅ новый, pending | ⏳ после одобрения | кабинет affiliates.writesonic.com |
| Synthesia | AI видео | ❌ нужен доменный email | — | анкета |
| ElevenLabs | AI аудио | ❌ блок IP | — | нужен резидентный VPN |
| Crypto.com | биржа | ❌ через Impact | — | нужен Impact |

## 3. Формат ссылок

```
https://<реф-ссылка>?utm_source=tg_<channel>&utm_medium=telegram&utm_campaign=partners
```
Примеры: `utm_source=tg_crypto_en`, `tg_ai_en`, `tg_sport_en`, `tg_crypto_es`,
`tg_ai_es`, `tg_sport_es`.

## 4. План «в каналы» (после получения ссылок)

1. Собрать все реф-ссылки в этом файле (таблица выше, колонка «Реф-ссылка»).
2. Сделать 6 закрепов «Полезное / Партнёры» (EN/ES) — 3–5 ссылок в каждом,
   формат: короткое описание + ссылка; маркировка «реклама».
3. Встроить по 1 партнёрской ссылке в обычные посты: не чаще 1 на 5 постов,
   чередуя программы.
4. Добавить кнопки/ссылки в лендинг (`docs/index.html`).
5. Считать клики: UTM → GA4 (уже подключён) + статистика партнёрок.

## 5. Блокеры

- Для входа в кабинеты нужен **Google-логин** (окно открыто) или логины/пароли;
  после этого я вытащу реф-ссылки и заполню таблицу.
- Admitad/MEXC/KuCoin/Bitget/Kraken/Bybit из текущей сети недоступны —
  нужен ваш VPN/резидентный прокси.

## 6. Шаблоны закрепов по каналам (подставить реф-ссылки)

**crypto-news (EN)** — закреп «Tools & Exchanges»:
```
🔧 Tools & Exchanges we use

• MEXC — spot & futures, fast listings → {{MEXC_REF}}
• Bybit — derivatives & copy trading → {{BYBIT_REF}}
• Bitget — copy trading, new listings → {{BITGET_REF}}
• Kraken — regulated US exchange → {{KRAKEN_REF}}

⚠️ Advertising / affiliate links. Crypto is volatile — do your own research.
```

**ai-news (EN)** — закреп «AI Tools»:
```
🤖 AI tools we cover & recommend

• Writesonic — AI writing & GEO → {{WRITESONIC_REF}}
• Synthesia — AI video avatars → {{SYNTHESIA_REF}}
• ElevenLabs — AI voice → {{ELEVENLABS_REF}}
• NordVPN — privacy for AI tools → {{NORDVPN_REF}}

⚠️ Advertising / affiliate links.
```

**sport-news (EN)** — закреп «Partners» (18+):
```
🏆 Partners

• 1xBet — live betting & odds → {{ONEXBET_REF}}
• N1 Partners — betting offers → {{N1_REF}}

⚠️ 18+. Advertising / affiliate links. Bet responsibly.
```

**ES-каналы** — аналогично: Hotmart (курсы), Writesonic, Bitget/MEXC, 1xBet/N1;
маркировка «Publicidad / enlace de afiliado».

## 7. Порядок публикации

1. Закрепы (6 шт) — после получения ссылок.
2. Затем реф-посты (1 на 5 обычных), начиная с crypto-news и ai-news.
3. Ссылки в лендинг (footer) — после закрепов.

## 8. Найдено в почте / входы (2026-11-08)

- **collaborator.pro** — ваша партнёрская ссылка из письма:
  `https://collaborator.pro/ru/signup?code=m9Vidx`
- **N1 Partners** — кабинет партнёра: `https://backoffice.n1.partners/partner/login`
- **Travelpayouts** — пароль сброшен агентом (новый сохранён в
  `.local/affiliate/credentials.json`); вход по паролю блокируется reCAPTCHA из РФ,
  Google-SSO доводится до согласия, но сессия не создаётся — нужен VPN.
- Google-сессия в браузере агента активна (`valdislav.n@gmail.com`), Gmail доступен —
  можно делать сбросы паролей остальных сервисов, если не мешает капча/Cloudflare.

### Обновление 2026-11-08 (входы через сессию)

- **MyLead** — вход выполнен (аккаунт `Vald001`), реф-ссылка:
  `https://mylead.global/r/dJ67Qo`
- **N1 Partners** — пропущен по решению (2FA/блок).
- **Travelpayouts**, **1xPartners** — ждут входа в окне браузера
  (капчи/2FA проходятся только вручную).

### Обновление 2026-11-08 (вечер)

  предзаполненными полями; вход выполняет пользователь (капча/антибот).
- **Travelpayouts** — пароль сброшен, окно логина открыто (предзаполнено).
- **collaborator.pro** — реф-ссылка из письма: `https://collaborator.pro/ru/signup?code=m9Vidx`.
- **N1 Partners** — пропущен (2FA/блок).

## 9. Товарные партнёрки (e-commerce) — 08.11.2026

План и контент-шаблоны: `docs/monetization/product-affiliates.md`.
Аккаунты маркетплейсов уже есть в Google-аккаунте (Temu, eBay, Etsy, KLEKT,
Depop, Grailed, China-агенты: CNFans, Hoobuy, CSSBuy, iTaoBuy, AllChinaBuy,
Hipobuy, Pandabuy; плюс Admitad как CPA-сеть).

| Программа | Тип | Аккаунт | Реф-ссылка | Статус |
|---|---|---|---|---|
| **Temu Affiliate** | маркетплейс | ✅ Temu | ⏳ | регистрация в партнёрке |
| **eBay Partner Network** | маркетплейс | ✅ eBay | ⏳ | подать заявку |
| **Admitad** | CPA-сеть (AliExpress/Temu/Shein/LightInTheBox) | ✅ есть | ⏳ | **вход восстановлен 08.11 (Mitgo ID, KZ-резидентство подтверждено); создана площадка «Telegram tech & football channels» (@AINEWS0007, @WORLDNews0007, @SPORTSAnalytics007) — ждёт верификации через @adspace_verification_bot** |
| **Sugargoo** | посредник 1688/Taobao/AliExpress | ✅ есть | **https://www.sugargoo.com/register?memberId=2834487856253302865** | ✅ подключено 09.11: Affiliate Center активен, ставка 4–9% от стоимости доставки, вывод 2–10 числа (CNY) |
| **China-агенты** (CNFans, Hoobuy, CSSBuy, iTaoBuy, AllChinaBuy, Hipobuy) | посредники 1688/AliExpress | ✅ есть | ⏳ | CNFans/AllChinaBuy на обслуживании; Hoobuy/CSSBuy/Pandabuy недоступны из РФ |
| **KLEKT** | кроссовки/стритвир | ✅ KLEKT | ⏳ | партнёрка через Awin |
| **Etsy** | хэндмейд | ✅ Etsy | ⏳ | партнёрка через Awin (низкий приоритет) |
| **Ecwid** | SaaS-магазины (20% recurring) | ✅ Ecwid | ⏳ | регистрация в партнёрке |
| **Banggood** | маркетплейс (гаджеты/RC/FPV) | ✅ есть (dropship) | ⏳ | своя партнёрка до 25% (заявка 3–5 дней; нужен вход в аккаунт — капча) + оффер **Banggood WW** в Admitad (EPC ~$2, hold 40 дней) |
| **AliExpress Portals** | маркетплейс | ✅ есть (аккаунт ae615644) | ⏳ ссылки из Ad Center → Promote now → Copy&Promo | **вход 10.11.2026 по email-коду; комиссия до 9%, ссылки формата aliexpress.com/item/...?affd...** |
| **Amazon Associates** | маркетплейс | ❌ нет | — | отдельная регистрация (нужен сайт) |
| **AliExpress Portals** | маркетплейс | ❌ нет | — | регистрация или через Admitad |

Каналы: `ai-news`/`tech-ai-es` — гаджеты (Temu/AliExpress/Amazon);
`sport-news`/`futbol-es` — экипировка, джерси, кроссовки (eBay/KLEKT/агенты).
Правило: 1 товарный пост на 3–4 новостных, маркировка «партнёрская ссылка/advertising».
UTM: `utm_campaign=deals_<program>`.
## 10. Нейтральный лендинг deals (10.11.2026)

- **https://ofertas-finds.deed.page/** — хаб офферов (34 товара + 4 коллекции AliExpress,
  страница каналов). Публикация: `scripts/deed_publish.py`, токен `.local/keys/deed-page.json`.
- AliExpress-коллекции (трекинг): Ofertas del día, Menos de 5 $, Best sellers, Electrónica.
- GitHub Pages `docs/deals/*` — редиректы на нейтральный домен.
