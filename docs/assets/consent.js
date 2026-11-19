(function () {
  var script = document.currentScript;
  if (script === null) return;
  var gaId = script.getAttribute("data-ga") || "";
  var affiliate = script.getAttribute("data-affiliate") === "1";
  var key = "cf_consent_v1";
  var stored = "";
  try { stored = localStorage.getItem(key) || ""; } catch (error) { stored = ""; }

  function loadGA() {
    if (gaId.length === 0) return;
    var s = document.createElement("script");
    s.async = true;
    s.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(gaId);
    document.head.appendChild(s);
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag("js", new Date());
    window.gtag("config", gaId);
  }

  function loadAffiliate() {
    if (affiliate === false) return;
    var s = document.createElement("script");
    s.async = true;
    s.src = "https://emrld.ltd/NTk3Njcy.js?t=597672";
    document.head.appendChild(s);
  }

  function loadAll() {
    loadGA();
    loadAffiliate();
  }

  function resetLink() {
    var b = document.createElement("button");
    b.type = "button";
    b.textContent = document.documentElement.lang === "ru" ? "Cookies" : "Cookies";
    b.setAttribute("aria-label", "Cookie settings");
    b.style.cssText = "position:fixed;left:10px;bottom:10px;z-index:2147483000;background:#111827;color:#e5e7eb;border:1px solid #374151;border-radius:999px;padding:6px 10px;font:12px/1.2 system-ui,sans-serif;opacity:.75;cursor:pointer";
    b.addEventListener("click", function () {
      try { localStorage.removeItem(key); } catch (error) {}
      window.location.reload();
    });
    document.body.appendChild(b);
  }

  function choose(value) {
    try { localStorage.setItem(key, value); } catch (error) {}
    if (value === "granted") loadAll();
    var box = document.getElementById("cf-consent");
    if (box !== null) box.remove();
    resetLink();
  }

  if (stored === "granted") { loadAll(); resetLink(); return; }
  if (stored === "denied") { resetLink(); return; }

  var ru = document.documentElement.lang === "ru";
  var box = document.createElement("div");
  box.id = "cf-consent";
  box.setAttribute("role", "dialog");
  box.setAttribute("aria-label", ru ? "Согласие на cookies" : "Cookie consent");
  box.style.cssText = "position:fixed;left:16px;right:16px;bottom:16px;z-index:2147483000;max-width:760px;margin:0 auto;background:#0f172a;color:#e5e7eb;border:1px solid #334155;border-radius:14px;padding:16px 18px;box-shadow:0 18px 50px rgba(0,0,0,.35);font:14px/1.45 system-ui,sans-serif";
  box.innerHTML = "<div style='margin-bottom:10px'>" + (ru
    ? "Мы используем аналитику и партнёрские cookies, чтобы понимать трафик и получать комиссию за бронирования. Цена для вас не меняется. Подробнее — в <a href='/content-factory/privacy.html' style='color:#93c5fd'>политике конфиденциальности</a>."
    : "We use analytics and affiliate cookies to understand traffic and earn a commission on bookings. The price you pay does not change. Read our <a href='/content-factory/privacy.html' style='color:#93c5fd'>Privacy Policy</a>.") + "</div><div style='display:flex;gap:8px;flex-wrap:wrap'><button type='button' id='cf-accept' style='background:#2563eb;color:#fff;border:0;border-radius:8px;padding:9px 12px;font:600 13px system-ui,sans-serif;cursor:pointer'>" + (ru ? "Принять" : "Accept") + "</button><button type='button' id='cf-deny' style='background:transparent;color:#e5e7eb;border:1px solid #475569;border-radius:8px;padding:9px 12px;font:600 13px system-ui,sans-serif;cursor:pointer'>" + (ru ? "Только необходимые" : "Essential only") + "</button></div>";
  document.body.appendChild(box);
  document.getElementById("cf-accept").addEventListener("click", function () { choose("granted"); });
  document.getElementById("cf-deny").addEventListener("click", function () { choose("denied"); });
})();
