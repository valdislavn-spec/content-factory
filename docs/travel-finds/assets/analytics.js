(function () {
  var key = "cf_consent_v1";
  var stored = "";
  try { stored = localStorage.getItem(key) || ""; } catch (error) { stored = ""; }
  if (stored !== "granted") return;
  var id = "G-LC39S1FD7B";
  window.dataLayer = window.dataLayer || [];
  window.gtag = function () { window.dataLayer.push(arguments); };
  window.gtag("js", new Date());
  window.gtag("config", id, { anonymize_ip: true });
  var s = document.createElement("script");
  s.async = true;
  s.src = "https://www.googletagmanager.com/gtag/js?id=" + id;
  document.head.appendChild(s);
})();
