/* ==========================================================================
   travel-affiliate landing helpers (vanilla JS, no external dependencies).
   1) injects the TravelPayouts White Label widget;
   2) builds affiliate links for the deal cards from site-config.js;
   3) shows a graceful fallback when the widget/links are not configured yet.
   ========================================================================== */
(function () {
  "use strict";

  var config = window.TRAVEL_CONFIG || {};

  function isPlaceholderValue(value) {
    return !value || /^YOUR_/.test(String(value));
  }

  function widgetUrl(locale) {
    var params = {
      promo_id: config.widget && config.widget.promoId,
      shmarker: config.marker,
      campaign_id: config.widget && config.widget.campaignId,
      locale: locale,
      powered_by: (config.widget && config.widget.poweredBy) || "true",
    };
    var query = Object.keys(params)
      .filter(function (key) {
        return params[key] !== undefined && params[key] !== "";
      })
      .map(function (key) {
        return encodeURIComponent(key) + "=" + encodeURIComponent(params[key]);
      })
      .join("&");
    return "https://tp.media/content?" + query;
  }

  function appendUtm(target, campaign, content) {
    // UTM contract: source=seo_en|seo_es, medium=seo (used only for long targets).
    // NOTE: for pre-generated branded short links (?tpk.ro) query params are not
    // documented, so UTM is only used when a *long* target URL is wrapped later
    // (Links API converts longURL + UTM into a short partner link server-side).
    var lang = (document.documentElement.lang || "en").toLowerCase();
    var params = {
      utm_source: lang === "es" ? "seo_es" : "seo_en",
      utm_medium: "seo",
      utm_campaign: campaign || "landing",
      utm_content: content || "widget",
    };
    var separator = target.indexOf("?") === -1 ? "?" : "&";
    var query = Object.keys(params)
      .map(function (key) {
        return encodeURIComponent(key) + "=" + encodeURIComponent(params[key]);
      })
      .join("&");
    return target + separator + query;
  }

  function programConfig(program) {
    return (config.programs && config.programs[program]) || null;
  }

  function affiliateUrl(program, target) {
    var programInfo = programConfig(program);
    if (!programInfo) {
      return null;
    }
    // Links API bakes sub_id into a short link, so each language needs its own
    // seo_en / seo_es link (programInfo.urls.{en,es}); fallback — programInfo.url.
    var lang = (document.documentElement.lang || "en").toLowerCase();
    var url = (programInfo.urls && programInfo.urls[lang]) || programInfo.url;
    if (isPlaceholderValue(url)) {
      return null;
    }
    // 2026: no tp.media/r links in the browser; deep links are converted via
    // the TravelPayouts Links API (tools/links_api.py) in the content pipeline.
    if (target && programInfo.deeplinkTemplate) {
      return programInfo.deeplinkTemplate
        .replace("{url}", url)
        .replace("{target_encoded}", encodeURIComponent(appendUtm(target, "site-landing", program)));
    }
    return url;
  }

  function injectWidget() {
    var host = document.getElementById("tp-widget");
    var fallback = document.getElementById("widget-fallback");
    if (!host) {
      return;
    }
    var locale = host.getAttribute("data-locale") || "ru";
    if (isPlaceholderValue(config.widget && config.widget.promoId)) {
      if (fallback) {
        fallback.classList.add("is-visible");
      }
      return;
    }
    var script = document.createElement("script");
    script.charset = "utf-8";
    script.src = widgetUrl(locale);
    script.async = true;
    script.onerror = function () {
      if (fallback) {
        fallback.classList.add("is-visible");
      }
    };
    host.appendChild(script);
  }

  function wireDealCards() {
    var cards = document.querySelectorAll("[data-affiliate-program]");
    Array.prototype.forEach.call(cards, function (card) {
      var program = card.getAttribute("data-affiliate-program");
      var target = card.getAttribute("data-affiliate-target") || "";
      var url = affiliateUrl(program, target);
      if (!url) {
        card.setAttribute("aria-disabled", "true");
        card.setAttribute("title", "Партнёрские ссылки появятся после настройки site/assets/site-config.js");
        card.addEventListener("click", function (event) {
          event.preventDefault();
        });
        return;
      }
      card.setAttribute("href", url);
      card.setAttribute("rel", "sponsored nofollow noopener");
      card.setAttribute("target", "_blank");
      card.removeAttribute("aria-disabled");
    });
  }

  function markYear() {
    var node = document.getElementById("year");
    if (node) {
      node.textContent = String(new Date().getFullYear());
    }
  }

  function init() {
    injectWidget();
    wireDealCards();
    markYear();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
