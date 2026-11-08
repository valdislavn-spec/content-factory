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
