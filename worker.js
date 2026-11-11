// Cloudflare Worker: signed unsubscribe link -> Brevo contact blacklist.
// URL: /?e=<base64url(email)>&s=<hex HMAC-SHA256>
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const encoded = url.searchParams.get("e") || "";
    const signature = url.searchParams.get("s") || "";
    if (!encoded || !signature) return new Response("Invalid unsubscribe link.", {status: 400});
    let email;
    try {
      const padded = encoded.replace(/-/g, "+").replace(/_/g, "/");
      email = atob(padded + "===".slice((padded.length + 3) % 4));
    } catch (e) { return new Response("Invalid unsubscribe link.", {status: 400}); }
    const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(env.UNSUB_SECRET), {name: "HMAC", hash: "SHA-256"}, false, ["sign"]);
    const sig = [...new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(email)))].map(b => b.toString(16).padStart(2, "0")).join("");
    let ok = sig.length === signature.length;
    for (let i = 0; ok && i < sig.length; i++) ok = sig[i] === signature[i];
    if (!ok) return new Response("Invalid unsubscribe link.", {status: 400});
    const res = await fetch(`https://api.brevo.com/v3/contacts/${encodeURIComponent(email)}`, {
      method: "PUT",
      headers: {"api-key": env.BREVO_API_KEY, "Content-Type": "application/json", "Accept": "application/json"},
      body: JSON.stringify({emailBlacklisted: true})
    });
    const status = res.ok ? "You have been unsubscribed." : "We could not process the unsubscribe automatically. Please reply to any email with STOP.";
    return new Response(`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Unsubscribe — Travel Finds</title></head><body style="font-family:-apple-system,Segoe UI,Arial;background:#f7f9fc;color:#1b2430;display:flex;min-height:100vh;align-items:center;justify-content:center"><div style="max-width:520px;padding:32px;background:#fff;border-radius:14px"><h1 style="font-size:24px">${status}</h1><p>Email: ${email.replace(/</g,"&lt;")}</p><p><a href="https://valdislavn-spec.github.io/travel-finds/us-deals.html">Back to Travel Finds</a></p></div></body></html>`, {headers: {"content-type": "text/html; charset=utf-8"}});
  }
};
