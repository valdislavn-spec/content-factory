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
| KMA → KissMyAds | CPA-сеть | ✅ есть | ⏳ | вход на kissmyads.pro |
| MyLead | CPA-сеть (VPN) | ✅ есть | ⏳ | вход `pub.mylead.global` |
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
