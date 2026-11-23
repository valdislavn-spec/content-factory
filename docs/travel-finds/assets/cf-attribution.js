(function () {
  "use strict";
  var KEY = "cf_attr_v1";
  var COOKIE = "cf_attr";
  var MAX_AGE = 30 * 24 * 60 * 60;
  var PARAMS = ["epik", "click_id", "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"];
  var TRACKER_HOST = "links-tracker.valdislav-n.workers.dev";

  function clean(value) {
    return value === null || value === undefined ? "" : String(value).trim();
  }

  function decode(value) {
    try { return decodeURIComponent(value); } catch (e) { return value; }
  }

  function readCookie(name) {
    var parts = String(document.cookie || "").split(";");
    for (var i = 0; i < parts.length; i += 1) {
      var part = parts[i].replace(/^\s+/, "");
      var eq = part.indexOf("=");
      if (eq > -1 && part.slice(0, eq) === name) return decode(part.slice(eq + 1));
    }
    return "";
  }

  function parse(raw) {
    try { return JSON.parse(raw || "{}") || {}; } catch (e) { return {}; }
  }

  function has(value) { return clean(value).length > 0; }

  function currentParams() {
    var out = {};
    var query;
    try { query = new URLSearchParams(location.search); } catch (e) { return out; }
    for (var i = 0; i < PARAMS.length; i += 1) {
      var key = PARAMS[i];
      var value = clean(query.get(key));
      if (has(value)) out[key] = value;
    }
    if (has(out.epik) === false) {
      var cookieEpik = clean(readCookie("_epik"));
      if (has(cookieEpik)) out.epik = cookieEpik;
    }
    return out;
  }

  function storedParams() {
    var stored = parse(sessionStorage.getItem(KEY) || "");
    if (has(stored.epik) === false && has(stored.utm_source) === false && has(stored.click_id) === false) {
      stored = parse(readCookie(COOKIE));
    }
    return stored || {};
  }

  var stored = storedParams();
  var incoming = currentParams();
  var data = {};
  for (var i = 0; i < PARAMS.length; i += 1) {
    var key = PARAMS[i];
    data[key] = has(stored[key]) ? clean(stored[key]) : clean(incoming[key]);
  }

  function persist() {
    var serialized = JSON.stringify(data);
    try { sessionStorage.setItem(KEY, serialized); } catch (e) {}
    var cookie = COOKIE + "=" + encodeURIComponent(serialized) + "; Max-Age=" + MAX_AGE + "; Path=/; SameSite=Lax";
    if (location.protocol === "https:") cookie += "; Secure";
    try { document.cookie = cookie; } catch (e) {}
  }

  function isTracker(parsed) {
    return parsed.hostname === TRACKER_HOST && parsed.pathname.indexOf("/r/") === 0;
  }

  function merge(url) {
    var raw = clean(url);
    if (has(raw) === false || /^(mailto:|tel:|javascript:|data:|#)/i.test(raw)) return raw;
    try {
      var parsed = new URL(raw, location.href);
      if (isTracker(parsed) === false && (parsed.origin === location.origin) === false) return raw;
      for (var i = 0; i < PARAMS.length; i += 1) {
        var key = PARAMS[i];
        if (has(data[key]) && parsed.searchParams.has(key) === false) parsed.searchParams.set(key, data[key]);
      }
      return parsed.toString();
    } catch (e) { return raw; }
  }

  function source(base) {
    var value = clean(base);
    var source = clean(data.utm_source);
    var content = clean(data.utm_content);
    if (source) value += ":" + source + (content ? "-" + content : "");
    return value;
  }

  function hydrate() {
    persist();
    var links = document.querySelectorAll("a[href]");
    for (var i = 0; i < links.length; i += 1) {
      var link = links[i];
      var raw = link.getAttribute("href");
      var next = merge(raw);
      if (next === raw) continue;
      link.setAttribute("href", next);
    }
  }

  function botStart(base) {
    var sourceName = clean(data.utm_source) || (clean(data.epik) ? "pinterest" : "direct");
    var contentName = clean(data.utm_content) || "travelkit";
    var payload = String(base || "src_travelkit") + "_" + sourceName + "_" + contentName;
    payload = payload.replace(/[^A-Za-z0-9_-]/g, "_").slice(0, 64);
    return "https://t.me/Novyi0007Bot?start=" + encodeURIComponent(payload);
  }

  window.CFAttr = {
    get: function () { return Object.assign({}, data); },
    merge: merge,
    source: source,
    botStart: botStart
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", hydrate);
  } else {
    hydrate();
  }
})();
