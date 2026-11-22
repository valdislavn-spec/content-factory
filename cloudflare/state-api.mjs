// Durable state/queue API for content-factory.
export const API_PREFIX = "/api/v1";

function jsonResponse(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

async function readJson(request, limit = 200000) {
  const text = await request.text();
  if (text.length > limit) throw new Error("body too large");
  return text.length > 0 ? JSON.parse(text) : {};
}

function authorized(request, env) {
  const expected = String(env.STATE_API_TOKEN || "");
  if (expected.length === 0) return false;
  const header = String(request.headers.get("authorization") || "");
  const given = header.replace(/^Bearer\s+/i, "").trim();
  return given.length > 0 && given === expected;
}

export async function apiFetch(request, env) {
  if (authorized(request, env) === false) {
    return jsonResponse({ ok: false, error: "unauthorized" }, 401);
  }
  const url = new URL(request.url);
  const parts = url.pathname.split("/").filter(Boolean);
  const method = request.method.toUpperCase();
  try {
    if (parts[2] === "state" && parts[3]) {
      const name = decodeURIComponent(parts[3]);
      if (method === "GET") {
        const row = await env.DB.prepare(
          "SELECT value, updated_at FROM scheduler_state WHERE name = ?"
        ).bind(name).first();
        if (row === null) return jsonResponse({ ok: false, error: "not found" }, 404);
        let state = null;
        try { state = JSON.parse(row.value); } catch (e) { state = null; }
        return jsonResponse({ ok: true, state, updated_at: row.updated_at });
      }
      if (method === "PUT") {
        const body = await readJson(request);
        if (body === null || body === undefined || typeof body.state === "object" === false || body.state === null) {
          return jsonResponse({ ok: false, error: "state object required" }, 400);
        }
        const now = new Date().toISOString();
        await env.DB.prepare(
          "INSERT INTO scheduler_state (name, value, updated_at) VALUES (?, ?, ?) " +
          "ON CONFLICT(name) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at"
        ).bind(name, JSON.stringify(body.state), now).run();
        return jsonResponse({ ok: true, updated_at: now });
      }
      return jsonResponse({ ok: false, error: "method not allowed" }, 405);
    }

    if (parts[2] === "queue" && parts[3] === "due" && method === "GET") {
      const channelId = String(url.searchParams.get("channel_id") || "");
      if (channelId.length === 0) return jsonResponse({ ok: false, error: "channel_id required" }, 400);
      const limit = Math.min(100, Math.max(1, Number(url.searchParams.get("limit") || 20)));
      const now = String(url.searchParams.get("now") || new Date().toISOString());
      const rows = await env.DB.prepare(
        "SELECT * FROM publish_retries WHERE channel_id = ? AND next_attempt_at <= ? " +
        "ORDER BY next_attempt_at ASC LIMIT ?"
      ).bind(channelId, now, limit).all();
      return jsonResponse({ ok: true, rows: rows.results || [] });
    }

    if (parts[2] === "queue" && parts[3] === undefined && method === "POST") {
      const body = await readJson(request);
      const required = ["post_id", "publisher", "channel_id", "post_json", "next_attempt_at"];
      const missing = required.some((key) => body[key] === undefined || body[key] === null || body[key] === "");
      if (missing) return jsonResponse({ ok: false, error: "missing fields" }, 400);
      const now = new Date().toISOString();
      await env.DB.prepare(
        "INSERT INTO publish_retries " +
        "(post_id, publisher, channel_id, post_json, attempts, next_attempt_at, last_error, created_at, updated_at) " +
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) " +
        "ON CONFLICT(post_id, publisher) DO UPDATE SET " +
        "channel_id = excluded.channel_id, post_json = excluded.post_json, " +
        "attempts = excluded.attempts, next_attempt_at = excluded.next_attempt_at, " +
        "last_error = excluded.last_error, updated_at = excluded.updated_at"
      ).bind(
        String(body.post_id), String(body.publisher), String(body.channel_id),
        String(body.post_json), Number(body.attempts || 0),
        String(body.next_attempt_at), String(body.last_error || ""),
        String(body.created_at || now), String(body.updated_at || now)
      ).run();
      return jsonResponse({ ok: true });
    }

    if (parts[2] === "queue" && parts[3] === "done" && method === "POST") {
      const body = await readJson(request);
      await env.DB.prepare(
        "DELETE FROM publish_retries WHERE post_id = ? AND publisher = ?"
      ).bind(String(body.post_id || ""), String(body.publisher || "")).run();
      return jsonResponse({ ok: true });
    }

    if (parts[2] === "health" && parts[3] === "tick" && method === "POST") {
      const body = await readJson(request);
      const channelId = String(body.channel_id || "");
      if (channelId.length === 0) return jsonResponse({ ok: false, error: "channel_id required" }, 400);
      const now = new Date().toISOString();
      await env.DB.prepare(
        "INSERT INTO channel_health (channel_id, last_tick_at, last_post_at, last_error, updated_at) " +
        "VALUES (?, ?, ?, ?, ?) " +
        "ON CONFLICT(channel_id) DO UPDATE SET " +
        "last_tick_at = excluded.last_tick_at, " +
        "last_post_at = COALESCE(excluded.last_post_at, channel_health.last_post_at), " +
        "last_error = excluded.last_error, updated_at = excluded.updated_at"
      ).bind(
        channelId, String(body.last_tick_at || now),
        body.last_post_at ? String(body.last_post_at) : null,
        String(body.last_error || ""), now
      ).run();
      return jsonResponse({ ok: true });
    }

    if (parts[2] === "health" && parts[3] === undefined && method === "GET") {
      const channels = await env.DB.prepare(
        "SELECT * FROM channel_health ORDER BY channel_id"
      ).all();
      const queue = await env.DB.prepare(
        "SELECT COUNT(*) AS total, MIN(next_attempt_at) AS next_attempt_at FROM publish_retries"
      ).first();
      return jsonResponse({ ok: true, channels: channels.results || [], queue: queue || {} });
    }

    return jsonResponse({ ok: false, error: "not found" }, 404);
  } catch (e) {
    console.log("api error", String(e));
    return jsonResponse({ ok: false, error: String(e).slice(0, 300) }, 500);
  }
}
