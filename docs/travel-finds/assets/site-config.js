/* ==========================================================================
   Партнёрские ID/ссылки для сайта (site/) — non-RU (EN/ES).
   Основная страница: site/en.html (seo_en-ссылки), site/es.html (seo_es).
   RU-страница site/index.html переведена в архив (noindex, не деплоится).
   Ссылки взяты из config/links.generated.json (website project 597672,
   seo_en / seo_es; могут отдавать 403 до заполнения формы ad law — тогда
   пользователь откладывает партнёрские кнопки; замените urls на новые).
   API-токен на сайте НЕ НУЖЕН и НЕ ДОЛЖЕН попадать в репозиторий.
   ========================================================================== */
window.TRAVEL_CONFIG = {
  marker: "674170",
  market: "non_ru",
  widget: {
    // White Label Web (новый формат, 2026): идентификатор проекта wl_id.
    // Скрипт: https://tpwdg.com/wl_web/main.js?wl_id=<wlId>
    // Рендерится в контейнеры #tpwl-tickets / #tpwl-search / #tpwl-modals.
    wlId: "24664",
    // Старый формат tp.media/content?promo_id=... — оставлен как резерв.
    promoId: "YOUR_WIDGET_PROMO_ID",
    campaignId: "",
    poweredBy: "true",
  },
  // У каждой программы своя короткая ссылка на язык (sub_id seo_en/seo_es
  // зашит при создании). fallback — url для остальных случаев.
  programs: {
    kiwi: {
      url: "",
      urls: {
        en: "https://links-tracker.valdislav-n.workers.dev/r/tf-kiwi-en",
        es: "https://links-tracker.valdislav-n.workers.dev/r/tf-kiwi-es",
      },
      landing: "https://www.kiwi.com/",
      label: "Kiwi.com",
    },
    kiwitaxi: {
      url: "",
      urls: {
        en: "https://links-tracker.valdislav-n.workers.dev/r/tf-kiwitaxi-en",
        es: "https://links-tracker.valdislav-n.workers.dev/r/tf-kiwitaxi-es",
      },
      landing: "https://kiwitaxi.com/",
      label: "Kiwitaxi",
    },
    yesim: {
      url: "",
      urls: {
        en: "https://links-tracker.valdislav-n.workers.dev/r/tf-yesim-en",
        es: "https://links-tracker.valdislav-n.workers.dev/r/tf-yesim-es",
      },
      landing: "https://yesim.app/",
      label: "Yesim",
    },
    klook: {
      url: "",
      urls: {
        en: "https://links-tracker.valdislav-n.workers.dev/r/tf-klook-en",
        es: "https://links-tracker.valdislav-n.workers.dev/r/tf-klook-es",
      },
      landing: "https://www.klook.com/",
      label: "Klook",
    },
    tripcom: {
      // Website-проект пока не подписан на Trip.com → pending (кнопка off).
      url: "",
      urls: { en: "", es: "" },
      landing: "https://www.trip.com/",
      label: "Trip.com",
    },
  },
  siteUrl: "https://travel-finds.surge.sh",
  // Наш живой Telegram-канал (EN/ES-каналов пока нет — ведём один).
  telegram: {
    urlEn: "https://t.me/GOODTRAVEL007",
    urlEs: "https://t.me/GOODTRAVEL007",
    handle: "@GOODTRAVEL007",
  },
};

window.TRAVEL_PLACEHOLDER = !window.TRAVEL_CONFIG.programs.kiwi.urls.en;
