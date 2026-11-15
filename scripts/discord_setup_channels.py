import json, os, sys, urllib.error, urllib.request
API = "https://discord.com/api/v10"
UA = "DiscordBot (https://github.com/valdislavn-spec/content-factory, 1.0)"
NAMES = {
 "sport-news": ("us-sports", "US Sports News"),
 "ai-news": ("ai-news", "AI News"),
 "crypto-news": ("crypto", "Crypto & Blockchain"),
}
EXTRA = ["announcements", "welcome"]
def env(k):
    return (os.environ.get(k, "") or "").strip()
def api(method, path, payload=None):
    token = env("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("Нужен DISCORD_BOT_TOKEN")
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + path, data=body, method=method, headers={
        "Authorization": "Bot " + token,
        "Content-Type": "application/json",
        "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw[:200]}
def ensure_channel(guild_id, channels, name, title, apply):
    for ch in channels:
        if ch.get("type") == 0 and ch.get("name") == name:
            return ch
    if not apply:
        print("DRY", name)
        return {"id": "dry-" + name, "name": name}
    status, data = api("POST", "/guilds/%s/channels" % guild_id, {
        "name": name, "type": 0, "topic": title})
    if status not in (200, 201):
        raise SystemExit("create %s: HTTP %s %s" % (name, status, data))
    print("created", name, data.get("id"))
    return data
def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--guild-id", required=True)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--fix-install", action="store_true")
    p.add_argument("--redirect-uri", default="")
    a = p.parse_args()
    gid = a.guild_id
    ast, app = api("GET", "/oauth2/applications/@me")
    if ast == 200:
        keys = ("name", "bot_public", "bot_require_code_grant", "custom_install_url")
        print("APP_INFO=" + json.dumps({k: app.get(k) for k in keys}, ensure_ascii=False))
    else:
        print("APP_INFO_ERROR=%s %s" % (ast, app))
    app_id = str(app.get("id") or "") if ast == 200 else ""
    target = "/applications/%s" % app_id if app_id else "/applications/@me"
    if a.redirect_uri:
        rs, rupd = api("PATCH", target, {"redirect_uris": [a.redirect_uri]})
        print("SET_REDIRECT=" + json.dumps({"status": rs, "redirect_uris": rupd.get("redirect_uris")}, ensure_ascii=False))
    if a.fix_install:
        fs, upd = api("PATCH", target, {
            "bot_public": True,
            "bot_require_code_grant": False,
            "integration_public": True,
            "integration_require_code_grant": False,
        })
        keys = ("bot_public", "bot_require_code_grant",
                "integration_public", "integration_require_code_grant")
        print("FIX_INSTALL=" + json.dumps({"status": fs, **{k: upd.get(k) for k in keys}}, ensure_ascii=False))
    gs, guilds = api("GET", "/users/@me/guilds")
    if gs == 200:
        print("BOT_GUILDS=" + json.dumps([[g.get("id"), g.get("name")] for g in guilds], ensure_ascii=False))
    else:
        print("BOT_GUILDS_ERROR=%s %s" % (gs, guilds))
    status, channels = api("GET", "/guilds/%s/channels" % gid)
    if status != 200:
        raise SystemExit("GET channels: HTTP %s %s" % (status, channels))
    out = {}
    for key, (name, title) in NAMES.items():
        out[key] = ensure_channel(gid, channels, name, title, a.apply)
    for name in EXTRA:
        ensure_channel(gid, channels, name, name.title(), a.apply)
    invite = ""
    if a.apply:
        status, inv = api("POST", "/channels/%s/invites" % out["ai-news"]["id"], {
            "max_age": 0, "max_uses": 0, "unique": True})
        if status in (200, 201):
            invite = "https://discord.gg/" + str(inv.get("code", ""))
    print(json.dumps({"channels": {k: v.get("id") for k, v in out.items()},
                      "invite": invite}, ensure_ascii=False))
if __name__ == "__main__":
    main()
