# ES channel promo — automatic X/Twitter posting

Three Spanish Telegram channels are promoted on X (`@NValdislav`) through
Buffer: one channel per post, with the matching channel card and `Publicidad`
disclosure.

## Schedule

- **Mon** — ES AI News (`tech-ai-es`)
- **Wed** — ES Crypto & Blockchain (`crypto-es`)
- **Fri** — ES Sports News (`futbol-es`)
- **19:30 UTC** — 20:30 Spain, 15:30 Argentina, 11:30 US Pacific

Workflow: `.github/workflows/buffer-es-promo.yml`.
It runs `scripts/buffer_es_channels_promo.py --live` with the channel and a
variant chosen from the ISO week. No Buffer scheduled-post slots are used:
each run publishes with `shareNow`.

## Copy and assets

- 3 Spanish variants per channel, rotated by ISO week.
- Direct `t.me` link in every post.
- `Publicidad` at the end of every post.
- Card images from `docs/assets/channel-cards/` via raw GitHub URLs.
- X weighted length is checked before publishing (URL = 23 chars).

## Manual run

```bash
python scripts/buffer_es_channels_promo.py --channel crypto-es --variant 1
python scripts/buffer_es_channels_promo.py --channel crypto-es --variant 1 --live
```

`BUFFER_API_KEY` is required for `--live`; locally the script falls back to
`../.local/affiliate/buffer-api-key.txt`.
