/* ==========================================================================
   Партнёрские ID/ссылки для сайта (site/) — non-RU (EN/ES).
   Основная страница: site/en.html (seo_en-ссылки), site/es.html (seo_es).
   RU-страница site/index.html переведена в архив (noindex, не деплоится).
   Ссылки взяты из config/links.generated.json (website project 597672,
   seo_en / seo_es; могут отдавать 403 до заполнения формы ad law — тогда
   пользователь откладывает партнёрские кнопки; замените urls на новые).
   API-токен на сайте НЕ НУЖЕН и НЕ ДОЛЖЕН попадать в репозиторий.
   ========================================================================== */
// TravelPayouts project 24664 has showHotels=true. On this landing the
// "Search flights" button must run a flight search, not open Booking.com.
window.TPWL_CONFIGURATION = Object.assign({}, window.TPWL_CONFIGURATION, {
  showHotels: false,
});

window.TRAVEL_CONFIG = {
  marker: "674170",
  market: "non_ru",
  widget: {
    // White Label Web (новый формат, 2026): идентификатор проекта wl_id.
    // Скрипт: https://tpwdg.com/wl_web/main.js?wl_id=<wlId>
    // Рендерится в контейнеры #tpwl-tickets / #tpwl-search / #tpwl-modals.
    wlId: "24664",
    // Старый формат tp.media/content?promo_id=... — оставлен как резерв.
    promoId: "",
    campaignId: "",
    poweredBy: "true",
    // Дополнительные WL-проекты (отели, календарь цен). Пустой wlId = блок скрыт.
    // Заводится в кабинете TravelPayouts: White Label → новый проект → тип виджета.
    extra: [
      { name: "hotels", wlId: "", container: "tpwl-hotels", section: "hotels" },
      { name: "calendar", wlId: "", container: "tpwl-calendar", section: "cheap-dates" },
    ],
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
    booking: {
      // Ожидает Join Booking.com в кабинете Travelpayouts; кнопка появится после ссылки.
      status: "pending",
      url: "",
      urls: { en: "", es: "" },
      landing: "https://www.booking.com/",
      label: "Booking.com",
    },
    hotellook: {
      status: "pending",
      url: "",
      urls: { en: "", es: "" },
      landing: "https://www.hotellook.com/",
      label: "Hotellook",
    },
    getyourguide: {
      status: "pending",
      url: "",
      urls: { en: "", es: "" },
      landing: "https://www.getyourguide.com/",
      label: "GetYourGuide",
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
