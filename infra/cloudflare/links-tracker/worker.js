const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json" } });

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

async function all(env, sql, params = []) {
  const res = await env.DB.prepare(sql).bind(...params).all();
  return res.results || [];
}

async function run(env, sql, params = []) {
  return env.DB.prepare(sql).bind(...params).run();
}

export default {
  async fetch(request, env) {
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

    if (path === "/" || path === "") {
      return json({ ok: true, service: "cf-links", storage: "d1",
        endpoints: ["/r/{code}", "/c/{code}", "/stats", "/admin/links", "/subscribe", "/admin/subscribers"] });
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
      const target = JSON.stringify(String(record.target || ""));
      const html = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="robots" content="noindex,nofollow"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Opening partner…</title>
<style>body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#0f1420;color:#eef3f8;
display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0;padding:24px;text-align:center}
a{color:#f7931a;font-weight:600;word-break:break-all}p{opacity:.8;font-size:14px}</style></head>
<body><div><p>Redirecting to our travel partner…</p><p><a id="go" href="#">Continue →</a></p></div>
<script>
(async()=>{try{await fetch("/c/${code}",{method:"POST",keepalive:true});}catch(e){}
const u=${target};document.getElementById("go").href=u;location.replace(u);})();
</script></body></html>`;
      return new Response(html, {
        status: 200,
        headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" },
      });
    }

    // --- учёт клика ---
    if (path.startsWith("/c/")) {
      if (request.method !== "POST") return json({ ok: false, error: "method not allowed" }, 405);
      const code = slug(path.slice(3));
      const rows = await all(env, "SELECT code FROM links WHERE code = ?", [code]);
      if (!rows.length) return new Response("", { status: 404 });
      const now = new Date().toISOString();
      const day = now.slice(0, 10);
      await run(env, `INSERT INTO clicks (code, day, count, last_click) VALUES (?,?,1,?)
        ON CONFLICT(code, day) DO UPDATE SET count = clicks.count + 1, last_click = excluded.last_click`,
        [code, day, now]);
      return new Response(null, { status: 204 });
    }

    // --- статистика ---
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
      const out = [];
      for (const link of links) {
        const a = byCode[link.code] || {};
        const days = await all(env, "SELECT day, count FROM clicks WHERE code = ? ORDER BY day", [link.code]);
        out.push({
          code: link.code, channel: link.channel || "", network: link.network || "",
          label: link.label || "", target: link.target || "",
          total: Number(a.total || 0),
          days: Object.fromEntries(days.map((d) => [d.day, d.count])),
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
