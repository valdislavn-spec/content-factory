/**
 * cf-subscribe — приём email-подписок на еженедельный дайджест.
 *
 * POST /  {email, language: "en"|"es", topics: string[], consent: true}
 * Хранит подписчиков в KV (binding SUBSCRIBERS), при наличии секретов
 * BREVO_API_KEY / BREVO_LIST_ID_EN / BREVO_LIST_ID_ES дублирует контакт в Brevo.
 *
 * Деплой: см. cloudflare/README.md (раздел «Email-подписка»).
 */

const ALLOWED_ORIGINS = [
  "https://valdislavn-spec.github.io",
  "http://localhost:8000",
  "http://127.0.0.1:8000",
];

function corsHeaders(request) {
  const origin = request.headers.get("Origin") || "";
  const allow = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    "Access-Control-Allow-Origin": allow,
    "Access-Control-Allow-Methods": "POST, OPTIONS, GET",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin",
  };
}

function json(request, data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...corsHeaders(request) },
  });
}

function validEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email) && email.length <= 254;
}

async function syncBrevo(env, email, language, topics) {
  if (!env.BREVO_API_KEY) return false;
  const listId = language === "es" ? env.BREVO_LIST_ID_ES : env.BREVO_LIST_ID_EN;
  if (!listId) return false;
  try {
    const response = await fetch("https://api.brevo.com/v3/contacts", {
      method: "POST",
      headers: { "api-key": env.BREVO_API_KEY, "Content-Type": "application/json" },
      body: JSON.stringify({
        email,
        attributes: { LANGUAGE: language, TOPICS: topics.join(",") },
        listIds: [Number(listId)],
        updateEnabled: true,
      }),
    });
    return response.ok || response.status === 204;
  } catch (error) {
    console.error("brevo sync failed", error);
    return false;
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(request) });
    }
    if (request.method === "GET") {
      return json(request, { ok: true, service: "cf-subscribe" });
    }
    if (request.method !== "POST") {
      return json(request, { ok: false, error: "method_not_allowed" }, 405);
    }
    let body;
    try {
      body = await request.json();
    } catch (error) {
      return json(request, { ok: false, error: "invalid_json" }, 400);
    }
    // Honeypot: реальные люди не заполняют скрытое поле.
    if (body.website) return json(request, { ok: true });

    const email = String(body.email || "").trim().toLowerCase();
    const language = body.language === "es" ? "es" : "en";
    const topics = Array.isArray(body.topics)
      ? body.topics.filter((topic) => ["crypto", "ai", "sports"].includes(topic)).slice(0, 3)
      : ["all"];
    const consent = body.consent === true || body.consent === "on" || body.consent === "true";
    if (!validEmail(email)) return json(request, { ok: false, error: "invalid_email" }, 400);
    if (!consent) return json(request, { ok: false, error: "consent_required" }, 400);

    const key = "sub:" + email;
    const existing = await env.SUBSCRIBERS.get(key);
    const record = {
      email,
      language,
      topics,
      consent_at: new Date().toISOString(),
      source: "landing",
      country: (request.cf && request.cf.country) || "",
      user_agent: (request.headers.get("user-agent") || "").slice(0, 160),
    };
    await env.SUBSCRIBERS.put(key, JSON.stringify(record));
    const brevoSynced = await syncBrevo(env, email, language, topics);
    return json(request, { ok: true, duplicate: Boolean(existing), brevo_synced: brevoSynced });
  },
};
