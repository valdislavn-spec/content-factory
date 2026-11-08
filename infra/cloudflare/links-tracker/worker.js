const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json" } });

const slug = (s) =>
  String(s || "").toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 64);

async function num(env, key) {
  return Number((await env.LINKS.get(key)) || 0) || 0;
}

async function putNum(env, key, value) {
  await env.LINKS.put(key, String(value));
}

async function listLinks(env) {
  const out = [];
  let cursor = undefined;
  do {
    const page = await env.LINKS.list({ prefix: "link:", cursor });
    for (const k of page.keys) {
      const raw = await env.LINKS.get(k.name);
      if (raw) out.push(JSON.parse(raw));
    }
    cursor = page.cursor;
  } while (cursor);
  return out;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    const token = url.searchParams.get("token") || request.headers.get("x-token") || "";

    if (path === "/" || path === "") {
      return json({ ok: true, service: "cf-links", endpoints: ["/r/{code}", "/stats", "/admin/links"] });
    }

    if (path === "/admin/links") {
      if (token !== env.ADMIN_TOKEN) return json({ ok: false, error: "forbidden" }, 403);
      if (request.method === "GET") {
        return json({ ok: true, links: await listLinks(env) });
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
      const record = {
        code,
        target,
        channel: slug(body.channel || ""),
        network: String(body.network || "").slice(0, 40),
        label: String(body.label || "").slice(0, 80),
        active: body.active !== false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      await env.LINKS.put("link:" + code, JSON.stringify(record));
      return json({ ok: true, record });
    }

    if (path.startsWith("/r/")) {
      const code = slug(path.slice(3));
      const raw = await env.LINKS.get("link:" + code);
      if (!raw) return new Response("Link not found", { status: 404 });
      const record = JSON.parse(raw);
      if (record.active === false) return new Response("Link disabled", { status: 404 });

      const now = new Date();
      const day = now.toISOString().slice(0, 10);
      const statsKey = "stats:" + code;
      const statsRaw = await env.LINKS.get(statsKey);
      const stats = statsRaw ? JSON.parse(statsRaw) : { total: 0, days: {}, channels: {} };
      stats.total += 1;
      stats.days[day] = (stats.days[day] || 0) + 1;
      if (record.channel) stats.channels[record.channel] = (stats.channels[record.channel] || 0) + 1;
      stats.last_click = now.toISOString();
      const days = Object.keys(stats.days).sort();
      if (days.length > 60) {
        for (const d of days.slice(0, days.length - 60)) delete stats.days[d];
      }
      await env.LINKS.put(statsKey, JSON.stringify(stats));

      return Response.redirect(record.target, 302);
    }

    if (path === "/stats") {
      if (token !== env.STATS_TOKEN && token !== env.ADMIN_TOKEN) {
        return json({ ok: false, error: "forbidden" }, 403);
      }
      const code = slug(url.searchParams.get("code") || "");
      if (code) {
        const rawLink = await env.LINKS.get("link:" + code);
        const rawStats = await env.LINKS.get(statsKeyFor(code));
        return json({
          ok: true,
          code,
          link: rawLink ? JSON.parse(rawLink) : null,
          stats: rawStats ? JSON.parse(rawStats) : { total: 0, days: {}, channels: {} },
        });
      }
      const links = [];
      for (const record of await listLinks(env)) {
        const rawStats = await env.LINKS.get(statsKeyFor(record.code));
        const stats = rawStats ? JSON.parse(rawStats) : { total: 0, days: {}, channels: {} };
        links.push({
          code: record.code,
          channel: record.channel || "",
          network: record.network || "",
          label: record.label || "",
          target: record.target || "",
          total: stats.total || 0,
          days: stats.days || {},
          channels: stats.channels || {},
          last_click: stats.last_click || null,
        });
      }
      links.sort((a, b) => b.total - a.total);
      return json({ ok: true, count: links.length, links });
    }

    return json({ ok: false, error: "not found" }, 404);
  },
};

function statsKeyFor(code) {
  return "stats:" + code;
}
