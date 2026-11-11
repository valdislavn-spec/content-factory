// Авто-алерты по цене (BingX) → Telegram-каналы.
// Cron Trigger каждую минуту, state в KV, публикация через Telegram Bot API.
// Полный аналог scripts/price_alerts.py + config/price_alerts.yaml.

const BINGX = "https://open-api.bingx.com/openApi/swap/v2/quote/ticker";
const TG = (token, method) => `https://api.telegram.org/bot${token}/${method}`;

const RULES = [
  { symbol: "BTC/USDT", above: 78000, below: 73500, cooldown: 360 },
  { symbol: "ETH/USDT", above: 2400, below: 2050, cooldown: 360 },
  { symbol: "BTC/USDT", move: 2.5, window: 60, cooldown: 120 },
  { symbol: "ETH/USDT", move: 3.0, window: 60, cooldown: 120 },
];

const CHANNELS = [
  {
    id: "crypto-news",
    chat: "-1003891468537",
    lang: "en",
    everyN: 3,
    affiliateUrl: "https://links-tracker.valdislav-n.workers.dev/r/bingx-crypto-news",
    disclaimer:
      "Ad · affiliate link. Not available in the US, UK, Canada, Singapore, Netherlands and Hong Kong. Crypto is volatile — risk of loss.",
  },
  {
    id: "crypto-es",
    chat: "-1004304574421",
    lang: "es",
    everyN: 3,
    affiliateUrl: "https://links-tracker.valdislav-n.workers.dev/r/bingx-crypto-es",
    disclaimer:
      "Anuncio · enlace de afiliado. No disponible en EE. UU., Reino Unido, Canadá, Singapur, Países Bajos y Hong Kong. Las criptomonedas son volátiles — riesgo de pérdida.",
  },
];

const TEMPLATES = {
  en: {
    above: "🚀 {symbol} broke above ${level} — now ${price} ({change:+.2f}% / 24h).",
    below: "🔻 {symbol} fell below ${level} — now ${price} ({change:+.2f}% / 24h).",
    move: "⚡️ {symbol} moved {pct:+.2f}% in {window} min — now ${price}.",
    footer: "Data: BingX · not financial advice.",
  },
  es: {
    above: "🚀 {symbol} superó los ${level} — ahora ${price} ({change:+.2f}% / 24h).",
    below: "🔻 {symbol} cayó por debajo de ${level} — ahora ${price} ({change:+.2f}% / 24h).",
    move: "⚡️ {symbol} se movió {pct:+.2f}% en {window} min — ahora ${price}.",
    footer: "Datos: BingX · no es asesoramiento financiero.",
  },
};

const HASHTAGS = { BTC: "#Bitcoin #BTC", ETH: "#Ethereum #ETH", SOL: "#Solana #SOL", XRP: "#XRP" };

function json(data, status = 200) {
  return new Response(JSON.stringify(data, null, 1), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

function fmtPrice(v) {
  if (v >= 1000) return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (v >= 1) return v.toFixed(2);
  return v.toFixed(4);
}
function fmtLevel(v) {
  return v.toLocaleString("en-US", { maximumFractionDigits: 0 });
}
function fmtSigned(v) {
  return (v >= 0 ? "+" : "") + v.toFixed(2);
}

async function fetchTicker(symbol) {
  const apiSymbol = symbol.replace("/", "-");
  const res = await fetch(`${BINGX}?symbol=${encodeURIComponent(apiSymbol)}`, {
    headers: { Accept: "application/json", "User-Agent": "price-alerts-worker/1.0" },
  });
  if (!res.ok) throw new Error(`BingX HTTP ${res.status}`);
  const body = await res.json();
  if (body.code !== 0 || !body.data) throw new Error(`BingX error: ${body.msg || "no data"}`);
  return {
    symbol,
    price: Number(body.data.lastPrice),
    change: Number(body.data.priceChangePercent || 0),
  };
}

async function sendTelegram(env, chat, text) {
  const res = await fetch(TG(env.TELEGRAM_BOT_TOKEN, "sendMessage"), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ chat_id: chat, text, disable_web_page_preview: true }),
  });
  const body = await res.json().catch(() => ({}));
  return {
    ok: res.ok && body.ok === true,
    status: res.status,
    description: body.description || "",
    message_id: body && body.result ? body.result.message_id : null,
  };
}

function buildText(channel, kind, data, affiliate) {
  const tpl = TEMPLATES[channel.lang] || TEMPLATES.en;
  let text;
  if (kind === "move") {
    text = tpl.move
      .replace("{symbol}", data.symbol)
      .replace("{pct}", fmtSigned(data.pct))
      .replace("{window}", String(data.window))
      .replace("{price}", fmtPrice(data.price));
  } else {
    text = tpl[kind]
      .replace("{symbol}", data.symbol)
      .replace("{level}", fmtLevel(data.level))
      .replace("{price}", fmtPrice(data.price))
      .replace("{change}", fmtSigned(data.change));
  }
  text += "\n\n" + tpl.footer;
  const base = data.symbol.split("/")[0].toUpperCase();
  if (HASHTAGS[base]) text += "\n" + HASHTAGS[base];
  if (affiliate) {
    text += "\n\n🤝 " + channel.affiliateUrl + "\n" + channel.disclaimer;
  }
  return text;
}

async function check(env, opts = {}) {
  const now = Date.now();
  const dry = !!opts.dry;
  const state = (await env.STATE.get("state", "json")) || {};
  const prices = state.prices || {};
  const history = state.history || {};
  const fired = state.fired || {};
  const counters = state.counters || {};

  const tickers = {};
  for (const symbol of [...new Set(RULES.map((r) => r.symbol))]) {
    try {
      tickers[symbol] = await fetchTicker(symbol);
    } catch (err) {
      tickers[symbol] = { symbol, error: String(err).slice(0, 120) };
    }
  }

  // одна точка истории на символ за прогон (а не на каждое правило)
  const histMap = {};
  for (const symbol of Object.keys(tickers)) {
    const ticker = tickers[symbol];
    if (!ticker || ticker.error || !Number.isFinite(ticker.price)) continue;
    const hist = (history[symbol] || []).filter((p) => now - p.t <= 180 * 60_000 && p.t !== now);
    hist.push({ p: ticker.price, t: now });
    histMap[symbol] = hist.slice(-200);
  }

  const events = [];
  for (const rule of RULES) {
    const ticker = tickers[rule.symbol];
    if (!ticker || ticker.error || !Number.isFinite(ticker.price)) continue;
    const price = ticker.price;
    const prev = prices[rule.symbol];
    const hist = histMap[rule.symbol] || [];

    if (prev && Number.isFinite(prev.p)) {
      if (rule.above != null && prev.p < rule.above && price >= rule.above) {
        events.push({ key: `${rule.symbol}:above`, kind: "above", symbol: rule.symbol, level: rule.above, price, change: ticker.change, cooldown: rule.cooldown });
      }
      if (rule.below != null && prev.p > rule.below && price <= rule.below) {
        events.push({ key: `${rule.symbol}:below`, kind: "below", symbol: rule.symbol, level: rule.below, price, change: ticker.change, cooldown: rule.cooldown });
      }
    }
    if (rule.move != null) {
      const windowMs = rule.window * 60_000;
      const ref = hist.filter((p) => now - p.t >= windowMs).sort((a, b) => b.t - a.t)[0];
      if (ref && ref.p > 0) {
        const pct = ((price - ref.p) / ref.p) * 100;
        if (Math.abs(pct) >= rule.move) {
          events.push({ key: `${rule.symbol}:move:${rule.move}`, kind: "move", symbol: rule.symbol, pct, window: rule.window, price, cooldown: rule.cooldown });
        }
      }
    }
    prices[rule.symbol] = { p: price, t: now };
    history[rule.symbol] = hist.slice(-200);
  }

  const toSend = [];
  for (const ev of events) {
    const last = fired[ev.key];
    if (last && now - last < ev.cooldown * 60_000) continue;
    fired[ev.key] = now;
    for (const channel of CHANNELS) {
      counters[channel.id] = (counters[channel.id] || 0) + 1;
      const affiliate = channel.everyN > 0 && counters[channel.id] % channel.everyN === 0;
      toSend.push({ channel: channel.id, chat: channel.chat, text: buildText(channel, ev.kind, ev, affiliate), kind: ev.kind, symbol: ev.symbol });
    }
  }

  const results = [];
  if (!dry) {
    for (const item of toSend) {
      const r = await sendTelegram(env, item.chat, item.text);
      results.push({ channel: item.channel, ok: r.ok, status: r.status, error: r.ok ? "" : r.description.slice(0, 120) });
    }
    await env.STATE.put("state", JSON.stringify({ prices, history, fired, counters }));
    await env.STATE.put("last_run", JSON.stringify({ at: new Date(now).toISOString(), tickers, sent: results.length }));
  }
  return { ok: true, dry, at: new Date(now).toISOString(), tickers, events: events.map((e) => e.key), sent: results, planned: dry ? toSend.length : undefined };
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(env.STATE.put("last_trigger", JSON.stringify({ at: new Date().toISOString(), cron: event.cron })));
    ctx.waitUntil(
      check(env, { dry: false }).catch(async (err) => {
        await env.STATE.put("last_error", JSON.stringify({ at: new Date().toISOString(), error: String(err).slice(0, 300) }));
      })
    );
  },

  async fetch(request, env) {
    const url = new URL(request.url);
    const token = request.headers.get("x-token") || url.searchParams.get("token") || "";
    if (url.pathname === "/health") {
      let bot = null;
      try {
        const res = await fetch(TG(env.TELEGRAM_BOT_TOKEN, "getMe"));
        const body = await res.json();
        bot = body.ok ? body.result.username : `error ${res.status}`;
      } catch (err) {
        bot = String(err).slice(0, 80);
      }
      return json({
        ok: true,
        bot,
        last_trigger: await env.STATE.get("last_trigger", "json"),
        last_run: await env.STATE.get("last_run", "json"),
        last_error: await env.STATE.get("last_error", "json"),
      });
    }
    if (token !== env.ADMIN_TOKEN) return json({ ok: false, error: "forbidden" }, 403);
    if (url.pathname === "/selftest") {
      const chat = url.searchParams.get("chat") || "-1003891468537";
      const sent = await sendTelegram(env, chat, "🧪 price-alerts worker self-test — ignore this message");
      let deleted = null;
      if (sent.ok && sent.message_id) {
        const res = await fetch(TG(env.TELEGRAM_BOT_TOKEN, "deleteMessage"), {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ chat_id: chat, message_id: sent.message_id }),
        });
        const body = await res.json().catch(() => ({}));
        deleted = { ok: res.ok && body.ok === true, description: body.description || "" };
      }
      return json({ ok: sent.ok, sent, deleted });
    }
    if (url.pathname === "/run") {
      const result = await check(env, { dry: url.searchParams.get("dry") === "1" });
      return json(result);
    }
    return json({ ok: false, error: "unknown route", routes: ["/health", "/run?dry=1", "/run"] }, 404);
  },
};
