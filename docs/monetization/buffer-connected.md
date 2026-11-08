# Buffer: подключение по API-ключу (08.11.2026)

Аккаунт: `valdislav.n@gmail.com` (Buffer, Free Plan).
API: GraphQL `https://api.buffer.com/graphql`, авторизация `Authorization: Bearer <key>`.
Ключ: создан в настройках Buffer («Content Factory Agent», Personal Access),
хранится локально: `.local/affiliate/buffer-api-key.txt` (chmod 600, в git не попадает).
Вход в веб-кабинет: пароль сброшен агентом (см. `.local/affiliate/credentials.json`),
вход подтверждён по email; используется NL-прокси.

## Каналы
| Канал | Сервис | Channel ID |
|---|---|---|
| BRAVE | bluesky | `6ae8d9bae29c69a1713c812f` |
| The best offers | facebook | `695c387b457dae6a34e00408` |
| NValdislav | twitter (X) | `6951b346457dae6a34bd5e32` |

Организация: `68d276b0ab330eddbacc2da8`.

## Первые публикации (shareNow, status: sent)
- Bluesky: https://bsky.app/profile/did:plc:p67ksvae6f5gara4vueu7edo/post/3mzsox2xpqy22
- X: https://x.com/1965860408218238976/status/2119447156624936984
- Facebook: https://facebook.com/865322629989875_122148500187054089

Текст: «Crypto digest: BTC holds above $100k as ETF inflows continue; ETH L2 activity
at record; AI tokens rally. Full market roundup → https://valdislavn-spec.github.io/content-factory/»

## Как постить через API (пример)
```bash
KEY=$(cat .local/affiliate/buffer-api-key.txt)
curl -s -X POST https://api.buffer.com/graphql \
  -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d '{"query":"mutation C($i:CreatePostInput!){createPost(input:$i){... on PostActionSuccess{post{id status externalLink}} ... on MutationError{message}}}",
       "variables":{"input":{"channelId":"<id>","text":"...","schedulingType":"automatic","mode":"shareNow","needsApproval":false,"assets":[],"source":"api"}}}'
```
Facebook требует `metadata.facebook.type` = `post` / `story` / `reel`.
Для отложенных: `mode: customScheduled` + `dueAt`.

## Ограничения
- Buffer НЕ поддерживает Telegram — для TG остаётся текущий пайплайн (Bot API).
- Free Plan: 3 канала, лимиты API 150/15 мин, 600/24 ч, 3000/мес (сейчас 190/мес).


## Посты под каждую соцсеть (по лучшим практикам, 08.11.2026)

Во втором прогоне сделаны платформенные версии (первые тестовые посты остались
в каналах; удаление отправленных постов через API возвращает VoidMutationError —
чистить вручную в Buffer UI).

### Bluesky (BRAVE) — 291 символ
Тон разговорный, без спама хештегами, вопрос для вовлечения, ссылка с UTM.
> Quietly, BTC is holding above $100k while ETF inflows keep grinding higher — and ETH L2 activity just hit a record. Is this the calm before the next leg up? 📈
> Daily crypto digest: https://valdislavn-spec.github.io/content-factory/?utm_source=bsky&utm_medium=social&utm_campaign=crypto_digest

https://bsky.app/profile/did:plc:p67ksvae6f5gara4vueu7edo/post/3mzsoz747us22

### X (NValdislav) — 250 символов
Хук + 3 буллета, один эмодзи, без хештегов (чище в ленте), CTA-ссылка.
> 🚨 BTC holds $100k+ as ETF inflows keep coming.
> • ETH L2 activity at an ATH
> • AI tokens waking up
> Calm before the next leg up? 👀
> Full digest → https://valdislavn-spec.github.io/content-factory/?utm_source=x&utm_medium=social&utm_campaign=crypto_digest

https://x.com/1965860408218238976/status/2119447434359128189

### Facebook (The best offers) — 527 символов
Списком 3 пункта, вопрос в комментарии, 3 хештега, ссылка с UTM; metadata facebook.type=post.
> Three things crypto investors should watch this week 👇
> 1️⃣ Bitcoin is holding above $100k while ETF inflows continue — institutions aren't done yet.
> 2️⃣ Ethereum L2 activity just hit an all-time high: fees down, usage up.
> 3️⃣ AI tokens are waking up after weeks of consolidation.
> Is this the calm before the next leg up — or a trap? Tell us in the comments 👇
> Full market roundup (free): https://valdislavn-spec.github.io/content-factory/?utm_source=fb&utm_medium=social&utm_campaign=crypto_digest
> #Crypto #Bitcoin #AITokens

https://facebook.com/865322629989875_122148500211054089

### Почему так
- X: лимит 280, ссылка укорачивается t.co; буллеты читаются с телефона.
- Bluesky: лимит 300, аудитория не любит хештеги, ценит живой тон.
- Facebook: длиннее и вовлекающе, вопросы и нумерованные списки дают комментарии.
- UTM-метки на всех ссылках → клики видны в GA4.


## Посты с короткими ссылками на ТГ-каналы (08.11.2026)

Вместо длинного URL лендинга — короткие ссылки на Telegram-каналы (`t.me/...`).

### Bluesky (142 символа)
> BTC above $100k, ETH L2 at a record, AI tokens waking up — we cover all of it daily in a free Telegram digest. Join us: https://t.me/HOOPY0007

https://bsky.app/profile/did:plc:p67ksvae6f5gara4vueu7edo/post/3mzsp5cnmln2w

### X (139 символов)
> 📊 Crypto digest: BTC holds $100k+, ETH L2 activity at an ATH, AI tokens waking up.
> Daily breakdown in our Telegram → https://t.me/HOOPY0007

https://twitter.com/NValdislav/status/2119448027458900414

### Facebook (364 символа)
> Crypto markets are moving again 👇
> • Bitcoin is holding above $100k
> • ETH L2 activity is at an all-time high
> • AI tokens are waking up after consolidation
> We publish the full daily digest in Telegram — join free: https://t.me/HOOPY0007
> AI & tech news: https://t.me/AINEWS0007
> What are you watching this week? Tell us in the comments 👇
> #Crypto #Bitcoin #AITokens

https://facebook.com/865322629989875_122148500589054089

Короткие ссылки ТГ-каналов:
- crypto: https://t.me/HOOPY0007
- AI: https://t.me/AINEWS0007
- US Sports: https://t.me/SPORTNews0007
- ES: https://t.me/TechnologiesNews01, https://t.me/WORLDNews0007, https://t.me/SPORTSAnalytics007


## Очередь на 6 часов (каждые 2 часа, 08.11.2026)

Собраны свежие новости (Decrypt, TechCrunch AI, ESPN — 08.11.2026), ссылки
замаскированы под названия каналов через короткие алиасы is.gd:

| Канал | Алиас | Ведёт на |
|---|---|---|
| Crypto & Blockchain | `https://is.gd/CryptoBlockchain` / `https://is.gd/HOOPY0007` | t.me/HOOPY0007 |
| AI News | `https://is.gd/AINEWS0007` | t.me/AINEWS0007 |
| US Sports | `https://is.gd/SPORTNews0007` | t.me/SPORTNews0007 |
| ES Crypto | `https://is.gd/TechnologiesNews01` | t.me/TechnologiesNews01 |
| ES AI | `https://is.gd/WORLDNews0007` | t.me/WORLDNews0007 |
| ES Sports | `https://is.gd/SPORTSAnalytics007` | t.me/SPORTSAnalytics007 |

Расписание (UTC): **17:16, 19:16, 21:16** — по 3 соцсети (Bluesky, X, Facebook),
всего 9 постов (status: scheduled). Контент:
- Bluesky (≤300): 2 крипто-заголовка + «Crypto & Blockchain» алиас.
- X (≤280): короткий дайджест + алиас.
- Facebook (≤500): 2 крипто + 1 AI + 1 спорт, 3 ссылки на ТГ-каналы, хештеги.

Лимиты Free Plan: Bluesky 100/день, X 100/день, Facebook 35/день (использовано
по 3 отправленных + 3 запланированных на канал) — в лимит укладываемся.

Чтобы новости были свежими к каждому слоту, можно за 10 минут до публикации
обновлять текст запланированного поста (editPost) — поставить напоминания.


## Старт цикла (08.11.2026, 15:26 UTC)

Опубликованы стартовые посты (shareNow), дальше очередь каждые 2 часа:
- Bluesky: https://bsky.app/profile/did:plc:p67ksvae6f5gara4vueu7edo/post/3mzspiukywt23
- X: https://twitter.com/NValdislav/status/2119449640181395745
- Facebook: https://facebook.com/865322629989875_122148501663054089

Тематика: Bitcoin quantum-resistance, US Treasury/MEXC, OpenAI $11B, NFL refs;
ссылки — короткие is.gd-алиасы каналов. Запланированы 9 постов на 17:16/19:16/21:16 UTC
(3 сети × 3 слота) + напоминания 17:05/19:05/21:05 для обновления новостей.


### Обновление слота 17:16 UTC (17:05)
Перед публикацией тексты обновлены свежими новостями через `editPost`:
- Bluesky `6af09261562f2e6de9c6efd1` — 245 зн., status scheduled
- X `6af0926151492b796e46154b` — 130 зн., status scheduled
- Facebook `6af09262d6bbae6fa1f6f5d8` — 408 зн., status scheduled (потребовался metadata.facebook.type=post)

Темы: Bitcoin quantum-resistance, AI chip stocks/bubble, OpenAI $11B, Cowboys inactives.
Следующее обновление — 19:05 UTC (слот 19:16).
