const CORS = { "access-control-allow-origin": "*" };
const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json", ...CORS } });

const slug = (s) =>
  String(s || "").toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 64);

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[a-z]{2,}$/i;


async function hmacHex(secret, message) {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(message));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function unsubToken(email, secret) {
  const data = new TextEncoder().encode(String(email).toLowerCase() + "|" + String(secret));
  const buf = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 32);
}

const PINTEREST_EVENTS = new Set(["add_to_cart", "checkout", "custom", "lead", "page_visit", "search", "signup", "view_category", "watch_video"]);

async function sha256Hex(value) {
  const data = new TextEncoder().encode(String(value));
  const buf = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Server-side Pinterest Conversions API event. No-op unless both secrets are set.
async function sendPinterestEvent(env, body, request, allowTest) {
  const token = String(env.PINTEREST_CAPI_TOKEN || "");
  const adAccount = String(env.PINTEREST_AD_ACCOUNT_ID || "");
  if (token.length === 0 || adAccount.length === 0) return { skipped: true, reason: "not configured" };
  const email = String(body.email || "").trim().toLowerCase();
  const epik = String(body.epik || body.click_id || "").trim();
  if (email.length === 0 && epik.length === 0) return { skipped: true, reason: "email or click_id required" };
  const eventName = PINTEREST_EVENTS.has(String(body.event_name || "lead")) ? String(body.event_name || "lead") : "lead";
  const userData = {};
  if (email.length > 0) {
    userData.em = [await sha256Hex(email)];
    userData.external_id = [await sha256Hex(String(body.external_id || ("email:" + email)))];
  } else if (body.external_id) {
    userData.external_id = [await sha256Hex(String(body.external_id))];
  }
  if (epik.length > 0) userData.click_id = epik;
  const clientIp = String(request.headers.get("cf-connecting-ip") || "").trim();
  const userAgent = String(request.headers.get("user-agent") || "").trim();
  if (clientIp.length > 0) userData.client_ip_address = clientIp;
  if (userAgent.length > 0) userData.client_user_agent = userAgent.slice(0, 500);
  const event = {
    event_name: eventName,
    action_source: "web",
    event_time: Math.floor(Date.now() / 1000),
    event_id: (await sha256Hex(email.length > 0 ? (eventName + "|" + email) : (eventName + "|" + epik))).slice(0, 32),
    user_data: userData,
  };
  const sourceUrl = String(body.url || request.headers.get("referer") || env.PINTEREST_EVENT_SOURCE_URL || "https://valdislavn-spec.github.io/content-factory/").trim();
  if (sourceUrl.length > 0) event.event_source_url = sourceUrl.slice(0, 1000);
  const custom = {};
  if (body.source) custom.source = String(body.source).slice(0, 60);
  if (body.lang) custom.lang = String(body.lang).slice(0, 10);
  if (body.value) {
    custom.value = Number(body.value).toFixed(2);
    custom.currency = String(body.currency || "USD").toUpperCase();
  }
  if (Object.keys(custom).length > 0) event.custom_data = custom;
  const base = String(env.PINTEREST_CAPI_API_BASE || "https://api.pinterest.com/v5").replace(/\/+$/, "");
  let url = base + "/ad_accounts/" + encodeURIComponent(adAccount) + "/events";
  if (allowTest === true && body.test === true) url = url + "?test=true";
  const response = await fetch(url, {
    method: "POST",
    headers: { "authorization": "Bearer " + token, "content-type": "application/json" },
    body: JSON.stringify({ data: [event] }),
  });
  const text = await response.text();
  return { skipped: false, ok: response.ok, status: response.status, response: text.slice(0, 500) };
}

async function all(env, sql, params = []) {
  const res = await env.DB.prepare(sql).bind(...params).all();
  return res.results || [];
}

async function run(env, sql, params = []) {
  return env.DB.prepare(sql).bind(...params).run();
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;
    const token = url.searchParams.get("token") || request.headers.get("x-token") || "";

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: {
        "access-control-allow-origin": "*",
        "access-control-allow-methods": "GET,POST,OPTIONS",
        "access-control-allow-headers": "content-type,x-token",
      } });
    }

    // Гео-блок: все запросы из Украины (UA) запрещены.
    const country = (request.cf && request.cf.country) || "";
    if (country === "UA") {
      return new Response("Forbidden", { status: 403, headers: { "content-type": "text/plain; charset=utf-8" } });
    }

    if (path === "/" || path === "") {
      return json({ ok: true, service: "cf-links", storage: "d1",
        endpoints: ["/r/{code}", "/c/{code}", "/stats", "/admin/links", "/subscribe", "/admin/subscribers", "/admin/conversion", "/admin/pinterest-status", "/admin/queue", "/admin/funnel"] });
    }

    // --- durable growth queue (travel funnel) ---
    if (path === "/admin/queue" || path === "/admin/queue/seed" || path === "/admin/queue/update") {
      if (token !== env.ADMIN_TOKEN) return json({ ok: false, error: "forbidden" }, 403);
      const now = new Date().toISOString();
      if (path === "/admin/queue" && request.method === "GET") {
        const platform = url.searchParams.get("platform") || "";
        const status = url.searchParams.get("status") || "";
        const dueBefore = url.searchParams.get("due_before") || "";
        const clauses = [];
        const params = [];
        if (platform) { clauses.push("platform = ?"); params.push(platform); }
        if (status) { clauses.push("status = ?"); params.push(status); }
        if (dueBefore) { clauses.push("due <= ?"); params.push(dueBefore); }
        const where = clauses.length ? " WHERE " + clauses.join(" AND ") : "";
        const rows = await all(env, "SELECT * FROM growth_queue" + where + " ORDER BY due, id", params);
        const items = rows.map((r) => {
          let payload = {};
          try { payload = JSON.parse(r.payload || "{}"); } catch (e) { payload = {}; }
          return { ...payload, id: r.id, platform: r.platform, due: r.due, status: r.status,
            attempts: r.attempts, last_error: r.last_error, published_at: r.published_at,
            published_url: r.published_url, message_id: r.message_id, updated_at: r.updated_at };
        });
        return json({ ok: true, count: items.length, items });
      }
      if (path === "/admin/queue/seed" && request.method === "POST") {
        let body;
        try { body = await request.json(); } catch (e) { return json({ ok: false, error: "bad json" }, 400); }
        const items = Array.isArray(body) ? body : (Array.isArray(body.items) ? body.items : []);
        let count = 0;
        const sql = "INSERT INTO growth_queue (id,platform,due,status,payload,attempts,updated_at) VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET platform=excluded.platform, due=excluded.due, payload=excluded.payload, updated_at=excluded.updated_at";
        for (const item of items) {
          const id = slug(item.id);
          const platform = slug(item.platform || "");
          const due = String(item.due || "").slice(0, 10);
          if (id === "" || platform === "" || due === "") continue;
          await run(env, sql, [id, platform, due, String(item.status || "queued"), JSON.stringify(item), Number(item.attempts) || 0, now]);
          count += 1;
        }
        return json({ ok: true, count });
      }
      if (path === "/admin/queue/update" && request.method === "POST") {
        let body;
        try { body = await request.json(); } catch (e) { return json({ ok: false, error: "bad json" }, 400); }
        const id = slug(body.id || "");
        if (id === "") return json({ ok: false, error: "id required" }, 400);
        const allowed = ["status", "attempts", "last_error", "published_at", "published_url", "message_id", "payload"];
        const sets = [];
        const params = [];
        for (const key of allowed) {
          if (Object.prototype.hasOwnProperty.call(body, key)) {
            sets.push(key + " = ?");
            params.push(key === "payload" ? JSON.stringify(body[key]) : body[key]);
          }
        }
        if (sets.length === 0) return json({ ok: false, error: "no fields" }, 400);
        sets.push("updated_at = ?");
        params.push(now);
        params.push(id);
        await run(env, "UPDATE growth_queue SET " + sets.join(", ") + " WHERE id = ?", params);
        return json({ ok: true, id });
      }
      return json({ ok: false, error: "method not allowed" }, 405);
    }

    // --- ссылки ---
    if (path === "/admin/links") {
      if (token !== env.ADMIN_TOKEN) return json({ ok: false, error: "forbidden" }, 403);
      if (request.method === "GET") {
        const links = await all(env, "SELECT * FROM links ORDER BY created_at DESC");
        return json({ ok: true, links });
      }
      if (request.method !== "POST") return json({ ok: false, error: "method not allowed" }, 405);
      let body;
      try {
        body = await request.json();
      } catch (e) {
        return json({ ok: false, error: "bad json" }, 400);
      }
      const code = slug(body.code);
      const target = String(body.target || "").trim();
      if (!code) return json({ ok: false, error: "code required" }, 400);
      if (!/^https?:\/\//.test(target)) return json({ ok: false, error: "target must be http(s)" }, 400);
      const now = new Date().toISOString();
      const record = {
        code, target,
        channel: slug(body.channel || ""),
        network: String(body.network || "").slice(0, 40),
        label: String(body.label || "").slice(0, 80),
        active: body.active !== false ? 1 : 0,
        created_at: now, updated_at: now,
      };
      await run(env, `INSERT INTO links (code,target,channel,network,label,active,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(code) DO UPDATE SET target=excluded.target, channel=excluded.channel,
          network=excluded.network, label=excluded.label, active=excluded.active, updated_at=excluded.updated_at`,
        [record.code, record.target, record.channel, record.network, record.label,
         record.active, record.created_at, record.updated_at]);
      return json({ ok: true, record });
    }


    // --- вебхуки Kit: подписчики, открытия, клики ---
    if (path === "/kit/webhook") {
      if (request.method !== "POST") return json({ ok: false, error: "method not allowed" }, 405);
      const raw = await request.text();
      const header = request.headers.get("X-Kit-Signature") || "";
      const secret = env.KIT_WEBHOOK_SECRET || "";
      if (!secret) return json({ ok: false, error: "no webhook secret" }, 500);
      const parts = Object.fromEntries(header.split(",").map((p) => p.trim().split("="))
        .filter((p) => p.length === 2).map(([k, v]) => [k, v]));
      if (!parts.t || !parts.v1) return json({ ok: false, error: "bad signature header" }, 401);
      const expected = await hmacHex(secret, `${parts.t}.${raw}`);
      const valid = header.split(",").some((p) => {
        const [k, v] = p.trim().split("=");
        return k === "v1" && v === expected;
      });
      if (!valid) return json({ ok: false, error: "bad signature" }, 401);
      let envelope = {};
      try { envelope = JSON.parse(raw); } catch (e) { envelope = {}; }
      const events = Array.isArray(envelope.events) ? envelope.events
        : (envelope.type ? [envelope] : []);
      const now = new Date().toISOString();
      for (const evt of events) {
        const type = String(evt.type || "");
        const data = evt.data || {};
        const subscriber = data.subscriber || {};
        const email = String(subscriber.email_address || data.email_address || "").toLowerCase();
        await run(env, "INSERT INTO kit_events (event, email, payload, received_at) VALUES (?,?,?,?)",
          [type, email, JSON.stringify(evt).slice(0, 20000), now]);
        if (email && (type === "subscriber.created" || type === "subscriber.activated"
          || type === "subscriber.subscribed_to_form" || type === "subscriber.tag_added")) {
          await run(env, `INSERT INTO subscribers (email, source, lang, created_at, unsubscribed)
            VALUES (?,?,?,?,0) ON CONFLICT(email) DO UPDATE SET unsubscribed = 0`,
            [email, "kit", "ru", now]);
        }
        if (email && (type === "subscriber.unsubscribed" || type === "subscriber.bounced"
          || type === "subscriber.complained")) {
          await run(env, "UPDATE subscribers SET unsubscribed = 1 WHERE email = ?", [email]);
        }
      }
      return json({ ok: true });
    }

    // --- подписка (свой лист, без Brevo) ---
    if (path === "/subscribe") {
      if (request.method !== "POST") return json({ ok: false, error: "method not allowed" }, 405);
      let body;
      try {
        body = await request.json();
      } catch (e) {
        return json({ ok: false, error: "bad json" }, 400);
      }
      const email = String(body.email || "").trim().toLowerCase();
      if (!EMAIL_RE.test(email) || email.length > 160) {
        return json({ ok: false, error: "valid email required" }, 400);
      }
      const lang = ["ru", "en", "es"].includes(String(body.lang)) ? String(body.lang) : "ru";
      const source = slug(body.source || "page").slice(0, 60);
      await run(env, `INSERT INTO subscribers (email, source, lang, created_at, unsubscribed)
        VALUES (?,?,?,?,0)
        ON CONFLICT(email) DO UPDATE SET unsubscribed = 0, source = excluded.source, lang = excluded.lang`,
        [email, source, lang, new Date().toISOString()]);
      if (ctx && typeof ctx.waitUntil === "function") {
        ctx.waitUntil(sendPinterestEvent(env, body, request, false).catch(function () {}));
      }
      return json({ ok: true }, 200);
    }

    if (path === "/unsubscribe") {
      const email = String(url.searchParams.get("e") || "").trim().toLowerCase();
      const token = String(url.searchParams.get("t") || "");
      if (!email || !token) return json({ ok: false, error: "e and t required" }, 400);
      const expected = await unsubToken(email, env.ADMIN_TOKEN);
      if (token !== expected) return json({ ok: false, error: "bad token" }, 403);
      await run(env, "UPDATE subscribers SET unsubscribed = 1 WHERE email = ?", [email]);
      return new Response(`<!doctype html><meta charset="utf-8"><title>Отписка</title>
<body style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#0b1226;color:#eef3f8;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0;padding:24px;text-align:center">
<div><h1 style="font-size:24px">Вы отписаны</h1><p style="opacity:.75">Больше писем на ${email} не будет. Передумаете — подпишитесь снова на сайте.</p></div></body>`,
        { status: 200, headers: { "content-type": "text/html; charset=utf-8" } });
    }

    if (path === "/admin/subscribers") {
      if (token !== env.ADMIN_TOKEN) return json({ ok: false, error: "forbidden" }, 403);
      const onlyActive = url.searchParams.get("all") !== "1";
      const rows = await all(env,
        "SELECT email, source, lang, created_at, unsubscribed FROM subscribers" +
        (onlyActive ? " WHERE COALESCE(unsubscribed,0) = 0" : "") + " ORDER BY created_at DESC");
      const byLang = {};
      for (const r of rows) byLang[r.lang] = (byLang[r.lang] || 0) + 1;
      return json({ ok: true, count: rows.length, by_lang: byLang, subscribers: rows });
    }


    if (path === "/admin/conversion") {
      if (token === env.ADMIN_TOKEN) {
        if (request.method === "POST") {
          let body;
          try {
            body = await request.json();
          } catch (e) {
            return json({ ok: false, error: "bad json" }, 400);
          }
          const result = await sendPinterestEvent(env, body, request, true);
          return json({ ok: result.skipped === false && result.ok === true, result });
        }
        return json({ ok: false, error: "method not allowed" }, 405);
      }
      return json({ ok: false, error: "forbidden" }, 403);
    }

    if (path === "/admin/pinterest-status") {
      if (token === env.ADMIN_TOKEN) {
        const tokenSet = String(env.PINTEREST_CAPI_TOKEN || "").length > 0;
        const accountSet = String(env.PINTEREST_AD_ACCOUNT_ID || "").length > 0;
        return json({ ok: true, configured: tokenSet && accountSet, token_set: tokenSet, ad_account_set: accountSet });
      }
      return json({ ok: false, error: "forbidden" }, 403);
    }

    // --- редирект ---
    if (path.startsWith("/r/")) {
      const code = slug(path.slice(3));
      const rows = await all(env, "SELECT target, active FROM links WHERE code = ?", [code]);
      const record = rows[0];
      if (!record) return new Response("Link not found", { status: 404 });
      if (!record.active) return new Response("Link disabled", { status: 404 });

      if (request.method === "HEAD") {
        return new Response("", { status: 200, headers: { "content-type": "text/html; charset=utf-8" } });
      }
      await recordClick(env, request, code);
      const dest = String(record.target || "");
      let location = dest;
      try {
        const destUrl = new URL(dest);
        for (const key of ["epik", "click_id", "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"]) {
          const value = url.searchParams.get(key);
          if (value && destUrl.searchParams.has(key) === false) destUrl.searchParams.set(key, value);
        }
        location = destUrl.toString();
      } catch (e) {}
      return new Response(null, { status: 302, headers: { location, "cache-control": "no-store" } });
    }

    // --- учёт клика ---
    if (path.startsWith("/c/")) {
      if (request.method !== "POST") return json({ ok: false, error: "method not allowed" }, 405);
      const code = slug(path.slice(3));
      const rows = await all(env, "SELECT code FROM links WHERE code = ?", [code]);
      if (!rows.length) return new Response("", { status: 404 });
      await recordClick(env, request, code);
      return new Response(null, { status: 204 });
    }

    // --- статистика ---
    if (path === "/admin/funnel") {
      if (token !== env.ADMIN_TOKEN && token !== env.STATS_TOKEN) {
        return json({ ok: false, error: "forbidden" }, 403);
      }
      const rows = await all(env, "SELECT code, SUM(count) AS total, MAX(last_click) AS last_click FROM clicks GROUP BY code ORDER BY total DESC");
      const links = rows.map((r) => ({ code: r.code, total: Number(r.total || 0), last_click: r.last_click || null }));
      return json({ ok: true, count: links.length, links });
    }

    if (path === "/stats") {
      if (token !== env.STATS_TOKEN && token !== env.ADMIN_TOKEN) {
        return json({ ok: false, error: "forbidden" }, 403);
      }
      const code = slug(url.searchParams.get("code") || "");
      if (code) {
        const link = (await all(env, "SELECT * FROM links WHERE code = ?", [code]))[0] || null;
        const rows = await all(env, "SELECT day, count, last_click FROM clicks WHERE code = ? ORDER BY day", [code]);
        const stats = { total: 0, days: {}, channels: {}, last_click: null };
        for (const r of rows) {
          stats.days[r.day] = r.count;
          stats.total += r.count;
          if (!stats.last_click || (r.last_click && r.last_click > stats.last_click)) stats.last_click = r.last_click;
        }
        if (link && link.channel) stats.channels[link.channel] = stats.total;
        return json({ ok: true, code, link, stats });
      }
      const links = await all(env, "SELECT * FROM links ORDER BY created_at DESC");
      const agg = await all(env, "SELECT code, SUM(count) AS total, MAX(last_click) AS last_click FROM clicks GROUP BY code");
      const byCode = Object.fromEntries(agg.map((r) => [r.code, r]));
      // Один запрос на все дни вместо отдельного запроса на каждую ссылку:
      // раньше 196 ссылок = 197 обращений к D1 и ответ обрывался по таймауту.
      const dayRows = await all(env, "SELECT code, day, count FROM clicks ORDER BY day");
      const daysByCode = {};
      for (const row of dayRows) {
        (daysByCode[row.code] = daysByCode[row.code] || {})[row.day] = row.count;
      }
      const out = [];
      for (const link of links) {
        const a = byCode[link.code] || {};
        const days = daysByCode[link.code] || {};
        out.push({
          code: link.code, channel: link.channel || "", network: link.network || "",
          label: link.label || "", target: link.target || "",
          total: Number(a.total || 0),
          days,
          channels: link.channel ? { [link.channel]: Number(a.total || 0) } : {},
          last_click: a.last_click || null,
        });
      }
      out.sort((a, b) => b.total - a.total);
      return json({ ok: true, count: out.length, links: out });
    }

    return json({ ok: false, error: "not found" }, 404);
  },
};

// Учёт клика: агрегат по дням + построчный лог в click_log.
async function recordClick(env, request, code) {
  const now = new Date().toISOString();
  const day = now.slice(0, 10);
  const cf = request.cf || {};
  const ua = (request.headers.get("user-agent") || "").slice(0, 300);
  const ref = (request.headers.get("referer") || "").slice(0, 300);
  const u = new URL(request.url);
  try {
    await run(env, "INSERT INTO clicks (code, day, count, last_click) VALUES (?,?,1,?) ON CONFLICT(code, day) DO UPDATE SET count = clicks.count + 1, last_click = excluded.last_click", [code, day, now]);
    await run(env, "INSERT INTO click_log (code, ts, day, country, city, referer, ua, path) VALUES (?,?,?,?,?,?,?,?)", [code, now, day, cf.country || "", cf.city || "", ref, ua, (u.pathname + u.search).slice(0, 300)]);
  } catch (e) {
    // учёт не должен ломать редирект
  }
}
