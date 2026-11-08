# kalshi-mcp-proxy

Cloudflare Worker that relays the Kalshi MCP endpoint for machines blocked by
Kalshi's CloudFront geo policy (this Mac gets HTTP 403 from
`api.elections.kalshi.com/mcp`).

```
assistant (DSH)  →  kalshi-mcp-proxy.valdislav-n.workers.dev/mcp
                 →  https://api.elections.kalshi.com/mcp
```

- Health check: `GET /health` → `{"ok":true}`
- Everything else is proxied as-is (method, headers, body, streaming response),
  so Streamable HTTP/SSE sessions work.
- No secrets are stored in the Worker; Kalshi's public market tools need no
  authentication. Portfolio / price-alert tools require Kalshi OAuth, which the
  DSH MCP client does not support — use
  `content_factory/integrations/kalshi.py` with a Kalshi API key instead.

## Deploy

```bash
cd infra/kalshi-mcp-proxy
CLOUDFLARE_API_TOKEN=... CLOUDFLARE_ACCOUNT_ID=... npx wrangler deploy
```

The script is deployed via the Cloudflare API from the same credentials that
maintain `tg-cron` and `telegram-proxy`.
