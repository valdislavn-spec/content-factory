// Kalshi MCP relay for machines geo-blocked from api.elections.kalshi.com.
// Cloudflare egress is not blocked, so this Worker proxies Streamable HTTP
// (including SSE) to the public Kalshi MCP endpoint.
//
// Deployed as Worker "kalshi-mcp-proxy" in account valdislav-n:
//   https://kalshi-mcp-proxy.valdislav-n.workers.dev/mcp
// DSH connects to it via @deepseek-ai/dsh-mcp-client (profile patch, id
// kalshi-mcp). Public market tools need no account; portfolio/price-alert
// tools need Kalshi OAuth, which dsh-mcp-client does not implement — use the
// REST client in content_factory/integrations/kalshi.py with an API key.

const ORIGIN = "https://api.elections.kalshi.com";

function proxyHeaders(headers) {
  const out = new Headers(headers);
  for (const header of [
    "host",
    "connection",
    "keep-alive",
    "transfer-encoding",
    "upgrade",
    "cf-connecting-ip",
  ]) {
    out.delete(header);
  }
  return out;
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname === "/health") {
      return new Response(JSON.stringify({ ok: true, proxy: "kalshi-mcp" }), {
        headers: { "content-type": "application/json" },
      });
    }
    const target = ORIGIN + url.pathname + url.search;
    const init = {
      method: request.method,
      headers: proxyHeaders(request.headers),
      redirect: "manual",
    };
    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = request.body;
    }
    let response;
    try {
      response = await fetch(target, init);
    } catch (error) {
      return new Response(JSON.stringify({ proxy_error: String(error) }), {
        status: 502,
        headers: { "content-type": "application/json" },
      });
    }
    const out = new Headers(response.headers);
    for (const header of ["content-encoding", "content-length", "transfer-encoding", "connection"]) {
      out.delete(header);
    }
    out.set("access-control-allow-origin", "*");
    return new Response(response.body, { status: response.status, headers: out });
  },
};
