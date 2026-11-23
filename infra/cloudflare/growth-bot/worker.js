/** GrowthBot — legal subscriber growth for a network of Telegram channels.
 *
 * Features: content locker (subscribe to all channels -> get materials),
 * referral links, giveaways, channel catalog, admin stats/draw.
 *
 * Deployed as a Cloudflare Worker (free plan). State lives in Workers KV.
 * No mass messages, no invites, no fake engagement.
 */

import {
  dedupeAppend,
  detectLang,
  formatUserLabel,
  isSubscribed,
  parseRefPayload,
  pickWinner,
  referralLink,
} from "./logic.js";

const KV_USER = (id) => "user:" + id;
const KV_STATS = "stats";
const KV_PARTICIPANTS = "giveaway:participants";
const KV_ACTIVE = "giveaway:active";

const EMPTY_STATS = { users: 0, verified: 0, referrals: 0, giveaway_entries: 0 };

const I18N = {
  en: {
    start: "👋 Welcome! Here you can get materials, join giveaways and invite friends.",
    menu_materials: "📦 Materials",
    menu_giveaway: "🎁 Giveaway",
    menu_referral: "👥 Invite a friend",
    menu_catalog: "📚 Channels",
    menu_rules: "📜 Rules",
    giveaway_join: "🎁 Join",
    giveaway_post: "🎁 Giveaway is live! Subscribe to all our channels and press the button to join. Winners are picked at random.",
    check: "✅ Check subscription",
    not_subscribed: "First subscribe to all our channels:",
    subscribed: "✅ Subscription confirmed!",
    reward: "🎁 Your materials: ",
    reward_empty: "🎁 You are subscribed! Materials will appear here soon.",
    referrals_none: "You have not invited anyone yet.\nYour link: ",
    referrals_count: "Invited: {n}. Your link: ",
    referral_bonus: "🔥 You invited {n} friends — bonus unlocked: ",
    giveaway_closed: "The giveaway is not running right now. Stay tuned!",
    giveaway_joined: "🎉 You are in the giveaway! Good luck!",
    giveaway_already: "You are already participating.",
    giveaway_need_sub: "To join, subscribe to all channels first.",
    catalog_title: "Our channels:",
    rules: "📜 Rules\n\nGiveaways: no purchase necessary; 18+; void where prohibited; winners are picked at random among subscribers; taxes are the winner's responsibility. Referrals: invite real people only, fake/bulk accounts are removed from the count. The bot is not affiliated with Telegram.",
    help: "Commands: /start, /rules, /stats (admin), /draw (admin), /giveaway on|off (admin).",
    error: "Something went wrong, please try again later.",
  },
  es: {
    start: "👋 ¡Bienvenido! Aquí puedes recibir materiales, participar en sorteos e invitar amigos.",
    menu_materials: "📦 Materiales",
    menu_giveaway: "🎁 Sorteo",
    menu_referral: "👥 Invitar amigo",
    menu_catalog: "📚 Canales",
    menu_rules: "📜 Reglas",
    giveaway_join: "🎁 Participar",
    giveaway_post: "🎁 ¡Sorteo activo! Suscríbete a todos nuestros canales y pulsa el botón para participar. Los ganadores se eligen al azar.",
    check: "✅ Verificar suscripción",
    not_subscribed: "Primero suscríbete a todos nuestros canales:",
    subscribed: "✅ ¡Suscripción confirmada!",
    reward: "🎁 Tus materiales: ",
    reward_empty: "🎁 ¡Estás suscrito! Los materiales aparecerán pronto.",
    referrals_none: "Aún no invitaste a nadie.\nTu enlace: ",
    referrals_count: "Invitados: {n}. Tu enlace: ",
    referral_bonus: "🔥 Invitaste a {n} amigos — bonus desbloqueado: ",
    giveaway_closed: "El sorteo no está activo ahora. ¡Atento!",
    giveaway_joined: "🎉 ¡Estás participando! ¡Suerte!",
    giveaway_already: "Ya participas.",
    giveaway_need_sub: "Para participar, suscríbete primero a todos los canales.",
    catalog_title: "Nuestros canales:",
    rules: "📜 Reglas\n\nSorteos: no es necesario comprar; 18+; válido donde no esté prohibido; los ganadores se eligen al azar entre los suscriptores; los impuestos son responsabilidad del ganador. Referidos: invita solo personas reales, las cuentas falsas se eliminan. El bot no está afiliado a Telegram.",
    help: "Comandos: /start, /rules, /stats (admin), /draw (admin), /giveaway on|off (admin).",
    error: "Algo salió mal, inténtalo de nuevo más tarde.",
  },
  ru: {
    start: "👋 Привет! Здесь можно получить материалы, поучаствовать в розыгрышах и пригласить друзей.",
    menu_materials: "📦 Материалы",
    menu_giveaway: "🎁 Розыгрыш",
    menu_referral: "👥 Пригласить друга",
    menu_catalog: "📚 Каналы",
    menu_rules: "📜 Правила",
    giveaway_join: "🎁 Участвовать",
    giveaway_post: "🎁 Розыгрыш запущен! Подпишитесь на все наши каналы и нажмите кнопку, чтобы участвовать. Победители выбираются случайно.",
    check: "✅ Проверить подписку",
    not_subscribed: "Сначала подпишитесь на все наши каналы:",
    subscribed: "✅ Подписка подтверждена!",
    reward: "🎁 Ваши материалы: ",
    reward_empty: "🎁 Вы подписаны! Материалы появятся здесь скоро.",
    referrals_none: "Вы пока никого не пригласили.\nВаша ссылка: ",
    referrals_count: "Приглашено: {n}. Ваша ссылка: ",
    referral_bonus: "🔥 Вы пригласили {n} друзей — бонус открыт: ",
    giveaway_closed: "Розыгрыш сейчас не проводится. Следите за анонсами!",
    giveaway_joined: "🎉 Вы участвуете в розыгрыше! Удачи!",
    giveaway_already: "Вы уже участвуете.",
    giveaway_need_sub: "Чтобы участвовать, сначала подпишитесь на все каналы.",
    catalog_title: "Наши каналы:",
    rules: "📜 Правила\n\nРозыгрыши: без необходимости покупки; 18+; только там, где не запрещено; победители выбираются случайно среди подписчиков; налоги — ответственность победителя. Рефералы: приглашайте только реальных людей, фейковые аккаунты удаляются из подсчёта. Бот не связан с Telegram.",
    help: "Команды: /start, /rules, /stats (админ), /draw (админ), /giveaway on|off (админ).",
    error: "Что-то пошло не так, попробуйте позже.",
  },
};

const OFFERS = [
  {
    "id": "02-bali-on-a-budget",
    "title": "Бали на бюджете",
    "title_en": "Bali on a budget: what 7 days actually cost",
    "description": "Реальный бюджет на 7 дней: жильё, еда, байк, пляжи и сезон, когда нет пиковых цен.",
    "description_en": "A realistic 7-day Bali budget: accommodation, food, scooter rental, beaches and when to go to avoid peak prices.",
    "category": "flights",
    "category_label": "Перелёты",
    "emoji": "🏝️",
    "guide_url": "https://valdislavn-spec.github.io/content-factory/travel/bali-budget.html",
    "affiliate_url": "https://aviasales.tpk.ro/rYaenwKl"
  },
  {
    "id": "01-europe-for-under-300",
    "title": "Европа дешевле $300",
    "title_en": "Europe for under $300: real cheap city breaks",
    "description": "Дешёвый city break: лучшие месяцы, ручная кладь и окно бронирования, которое обыгрывает пакетные туры.",
    "description_en": "How to plan a 3-night European city break under $300: cheapest months, carry-on tips and booking windows.",
    "category": "flights",
    "category_label": "Перелёты",
    "emoji": "✈️",
    "guide_url": "https://valdislavn-spec.github.io/content-factory/travel/europe-under-300.html",
    "affiliate_url": "https://aviasales.tpk.ro/b3PI8GVN"
  },
  {
    "id": "03-48-hours-in-rome",
    "title": "48 часов в Риме",
    "title_en": "48 hours in Rome: a first-timer itinerary",
    "description": "Маршрут на два дня: Колизей, Ватикан, Трастевере и билеты без очередей.",
    "description_en": "Two-day Rome itinerary: skip the queues at the Colosseum and Vatican, where to eat in Trastevere, and a realistic walking route.",
    "category": "experiences",
    "category_label": "Впечатления",
    "emoji": "🎟️",
    "guide_url": "https://valdislavn-spec.github.io/content-factory/travel/rome-48-hours.html",
    "affiliate_url": "https://tiqets.tpk.ro/ufgJDVmO"
  },
  {
    "id": "11-skip-the-line",
    "title": "Билеты без очереди",
    "title_en": "Skip-the-line tickets: what's worth it (and what's not)",
    "description": "Когда skip-the-line реально экономит часы, а когда это просто переплата.",
    "description_en": "Timed entry vs city passes: where skip-the-line actually saves hours, and where it is a waste of money.",
    "category": "experiences",
    "category_label": "Впечатления",
    "emoji": "🎫",
    "guide_url": "https://valdislavn-spec.github.io/content-factory/travel/skip-the-line-tickets-guide.html",
    "affiliate_url": "https://klook.tpk.ro/xqUojI5K"
  },
  {
    "id": "12-tours-and-experiences",
    "title": "Туры и впечатления",
    "title_en": "Туры и впечатления",
    "description": "Экскурсии, активности и билеты через партнёрскую программу Klook.",
    "description_en": "Экскурсии, активности и билеты через партнёрскую программу Klook.",
    "category": "experiences",
    "category_label": "Впечатления",
    "emoji": "🎡",
    "guide_url": "https://valdislavn-spec.github.io/content-factory/travel/",
    "affiliate_url": "https://klook.tpk.ro/xqUojI5K"
  },
  {
    "id": "08-travel-esim",
    "title": "Travel eSIM",
    "title_en": "Travel eSIM: stay online abroad without roaming bills",
    "description": "Как оставаться онлайн за границей без роуминга: установка до вылета и сравнение с SIM в аэропорту.",
    "description_en": "How travel eSIMs work, how to install one before flying, and when they beat airport SIM cards.",
    "category": "esim",
    "category_label": "Связь",
    "emoji": "📶",
    "guide_url": "https://valdislavn-spec.github.io/content-factory/travel/travel-esim.html",
    "affiliate_url": "https://saily.tpk.ro/r5oQ96LR"
  },
  {
    "id": "09-car-rental-no-surprises",
    "title": "Аренда авто в Европе",
    "title_en": "Car rental in Europe: when to book and how to avoid fees",
    "description": "Когда бронировать, что с топливом и страховкой, как не платить за скрытые доплаты.",
    "description_en": "Booking windows, fuel policy and excess cover: how to rent a car in Europe without hidden fees.",
    "category": "car",
    "category_label": "Авто",
    "emoji": "🚗",
    "guide_url": "https://valdislavn-spec.github.io/content-factory/travel/car-rental-europe.html",
    "affiliate_url": "https://localrent.tpk.ro/ZZ36vFV4"
  },
  {
    "id": "13-car-rental-booking-window",
    "title": "Окно бронирования авто",
    "title_en": "Car rental in Europe: when to book and how to avoid fees",
    "description": "Как поймать цену на аренду машины и не переплатить за позднее бронирование.",
    "description_en": "Booking windows, fuel policy and excess cover: how to rent a car in Europe without hidden fees.",
    "category": "car",
    "category_label": "Авто",
    "emoji": "🚙",
    "guide_url": "https://valdislavn-spec.github.io/content-factory/travel/car-rental-europe.html",
    "affiliate_url": "https://economybookings.tpk.ro/FI2DAtBO"
  },
  {
    "id": "10-airport-transfer",
    "title": "Трансфер из аэропорта",
    "title_en": "Airport transfers: fixed price, no taxi roulette",
    "description": "Фиксированная цена, встреча с табличкой, багаж и ночной прилёт без такси-рулетки.",
    "description_en": "How to book a reliable airport transfer: fixed prices, meet-and-greet, luggage and late-flight cover.",
    "category": "transfer",
    "category_label": "Трансферы",
    "emoji": "🚕",
    "guide_url": "https://valdislavn-spec.github.io/content-factory/travel/airport-transfer-guide.html",
    "affiliate_url": "https://kiwitaxi.tpk.ro/xmQYmqIl"
  },
  {
    "id": "14-luggage-storage",
    "title": "Хранение багажа",
    "title_en": "Luggage storage: explore the city hands-free",
    "description": "Где оставить вещи между выездом из отеля и самолётом: цены, вокзалы и бронирование.",
    "description_en": "Where to leave bags between check-out and your flight: prices, stations and booking tips.",
    "category": "luggage",
    "category_label": "Багаж",
    "emoji": "🧳",
    "guide_url": "https://valdislavn-spec.github.io/content-factory/travel/luggage-storage-guide.html",
    "affiliate_url": "https://radicalstorage.tpk.ro/XilIfuay"
  },
  {
    "id": "04-travel-insurance-mistakes",
    "title": "Страховка и компенсации",
    "title_en": "Страховка и компенсации",
    "description": "Типичные ошибки при покупке страховки и как получить компенсацию за задержку рейса.",
    "description_en": "Типичные ошибки при покупке страховки и как получить компенсацию за задержку рейса.",
    "category": "insurance",
    "category_label": "Страховка",
    "emoji": "🛡️",
    "guide_url": "https://valdislavn-spec.github.io/content-factory/travel/",
    "affiliate_url": "https://compensair.tpk.ro/4klXfGpD"
  }
];

const OFFER_I18N = {
  en: {
    menu: "✈️ Travel offers",
    title: "Travel offers:",
    not_found: "Offer not found. Open /offers.",
    ad: "Advertising: partner links. We may earn a commission at no extra cost to you.",
    guide: "Read guide",
    book: "Book with partner",
    back: "All offers",
  },
  es: {
    menu: "✈️ Ofertas de viaje",
    title: "Ofertas de viaje:",
    not_found: "Oferta no encontrada. Abre /offers.",
    ad: "Publicidad: enlaces de socios. Podemos recibir una comisión sin coste extra para ti.",
    guide: "Leer guía",
    book: "Reservar",
    back: "Todas las ofertas",
  },
  ru: {
    menu: "✈️ Travel-предложения",
    title: "Travel-предложения:",
    not_found: "Предложение не найдено. Откройте /offers.",
    ad: "Реклама: партнёрские ссылки. Мы можем получить комиссию, цена для вас не меняется.",
    guide: "Открыть гид",
    book: "Забронировать",
    back: "Все предложения",
  },
};


const LEGAL_I18N = {
  en: {
    privacy: "Privacy policy: https://valdislavn-spec.github.io/content-factory/privacy.html\n\nWe store your Telegram user id, username, display name, language and timestamps to run the bot and show aggregate stats. /delete removes your stored bot data.",
    privacy_hint: "Privacy: https://valdislavn-spec.github.io/content-factory/privacy.html — /delete removes your bot data.",
    deleted: "Your stored bot data has been deleted. You can start again with /start.",
  },
  es: {
    privacy: "Política de privacidad: https://valdislavn-spec.github.io/content-factory/privacy.html\n\nGuardamos tu id de Telegram, nombre de usuario, nombre visible, idioma y fechas para operar el bot y mostrar estadísticas agregadas. /delete borra tus datos guardados.",
    privacy_hint: "Privacidad: https://valdislavn-spec.github.io/content-factory/privacy.html — /delete borra tus datos.",
    deleted: "Tus datos guardados han sido eliminados. Puedes empezar de nuevo con /start.",
  },
  ru: {
    privacy: "Политика конфиденциальности: https://valdislavn-spec.github.io/content-factory/privacy.html\n\nМы храним Telegram id, username, отображаемое имя, язык и время действий, чтобы работать боту и показывать агрегированную статистику. /delete удаляет сохранённые данные.",
    privacy_hint: "Конфиденциальность: https://valdislavn-spec.github.io/content-factory/privacy.html — /delete удаляет данные.",
    deleted: "Сохранённые данные бота удалены. Можно начать заново командой /start.",
  },
};

function legalLabel(lang, key) {
  return (LEGAL_I18N[lang] || LEGAL_I18N.en)[key] || LEGAL_I18N.en[key] || key;
}

function offerLabel(lang, key) {
  return (OFFER_I18N[lang] || OFFER_I18N.en)[key] || OFFER_I18N.en[key] || key;
}

function findOffer(id) {
  const needle = String(id || "").toLowerCase();
  if (needle.length === 0) return null;
  return OFFERS.find((offer) => offer.id.toLowerCase() === needle)
    || OFFERS.find((offer) => offer.id.toLowerCase().startsWith(needle))
    || null;
}

function offerTitle(offer, lang) {
  return lang === "ru" ? offer.title : (offer.title_en || offer.title);
}

function offerDescription(offer, lang) {
  return lang === "ru" ? offer.description : (offer.description_en || offer.description);
}

function offerCategory(offer, lang) {
  return lang === "ru" ? offer.category_label : offer.category;
}

function offerText(offer, lang) {
  return offer.emoji + " " + offerTitle(offer, lang) + "\n\n"
    + offerDescription(offer, lang) + "\n\n"
    + offerCategory(offer, lang) + "\n\n"
    + offerLabel(lang, "guide") + ": " + offer.guide_url + "\n"
    + offerLabel(lang, "book") + ": " + offer.affiliate_url + "\n\n"
    + offerLabel(lang, "ad");
}

function offerKeyboard(offer, lang) {
  return [
    [
      { text: offerLabel(lang, "guide"), url: offer.guide_url },
      { text: offerLabel(lang, "book"), url: offer.affiliate_url },
    ],
    [{ text: offerLabel(lang, "back"), callback_data: "offers" }],
  ];
}

function offersKeyboard(offers, lang) {
  const rows = offers.slice(0, 20).map((offer) => [
    { text: offer.emoji + " " + offerTitle(offer, lang), callback_data: "offer:" + offer.id },
  ]);
  rows.push([{ text: offerLabel(lang, "back"), callback_data: "catalog" }]);
  return rows;
}

function offersListText(offers, lang) {
  const lines = [offerLabel(lang, "title"), ""];
  for (const offer of offers.slice(0, 20)) {
    lines.push(offer.emoji + " " + offerTitle(offer, lang) + " — " + offerCategory(offer, lang));
  }
  lines.push("", offerLabel(lang, "ad"));
  return lines.join("\n");
}

async function sendOffers(env, chatId, lang) {
  return send(env, chatId, offersListText(OFFERS, lang), offersKeyboard(OFFERS, lang));
}

async function sendOffer(env, chatId, lang, id) {
  const offer = findOffer(id);
  if (offer === null || offer === undefined) return send(env, chatId, offerLabel(lang, "not_found"));
  return send(env, chatId, offerText(offer, lang), offerKeyboard(offer, lang));
}


function text(lang, key, vars = {}) {
  let value = (I18N[lang] || I18N.en)[key] || I18N.en[key] || key;
  for (const [name, replacement] of Object.entries(vars)) {
    value = value.replace("{" + name + "}", String(replacement));
  }
  return value;
}

async function redis(env, command) {
  if (env.REDIS === undefined && env.REDIS_URL === undefined) {
    throw new Error("REDIS service binding or REDIS_URL is not configured");
  }
  if (env.REDIS_TOKEN === undefined) {
    throw new Error("REDIS_TOKEN is not configured");
  }
  const requestInit = {
    method: "POST",
    headers: {
      "Authorization": "Bearer " + env.REDIS_TOKEN,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(command),
  };
  const response = env.REDIS
    ? await env.REDIS.fetch("https://do-redis-growth.internal/", requestInit)
    : await fetch(env.REDIS_URL, requestInit);
  const bodyText = await response.text();
  let data = {};
  try {
    data = JSON.parse(bodyText);
  } catch {
    data = {};
  }
  if (response.ok === false || data.error) {
    throw new Error("redis " + response.status + " " + bodyText.slice(0, 300));
  }
  return data.result;
}

async function getRaw(env, key) {
  const value = await redis(env, ["GET", key]);
  return value === null || value === undefined ? null : String(value);
}

async function putRaw(env, key, value) {
  await redis(env, ["SET", key, value]);
}

async function deleteRaw(env, key) {
  await redis(env, ["DEL", key]);
}

async function getJSON(env, key, fallback) {
  const raw = await getRaw(env, key);
  if (raw === null || raw === "") return fallback;
  try {
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

async function putJSON(env, key, value) {
  await putRaw(env, key, JSON.stringify(value));
}

async function bot(env, method, payload = {}) {
  const response = await fetch("https://api.telegram.org/bot" + env.BOT_TOKEN + "/" + method, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return response.json().catch(() => ({ ok: false }));
}

async function send(env, chatId, message, keyboard) {
  const payload = { chat_id: chatId, text: message, disable_web_page_preview: true };
  if (keyboard) payload.reply_markup = { inline_keyboard: keyboard };
  return bot(env, "sendMessage", payload);
}

async function answerCallback(env, id, message, alert = false) {
  return bot(env, "answerCallbackQuery", {
    callback_query_id: id,
    text: message || "",
    show_alert: alert,
  });
}

function channels(env) {
  return String(env.CHANNELS || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}

function mainKeyboard(env, lang) {
  const rows = [
    [{ text: offerLabel(lang, "menu"), callback_data: "offers" }],
    [{ text: text(lang, "menu_materials"), callback_data: "verify" }],
    [
      { text: text(lang, "menu_giveaway"), callback_data: "giveaway" },
      { text: text(lang, "menu_referral"), callback_data: "referral" },
    ],
    [
      { text: text(lang, "menu_catalog"), callback_data: "catalog" },
      { text: text(lang, "menu_rules"), callback_data: "rules" },
    ],
  ];
  return rows;
}


async function updateStats(env, patch) {
  const stats = await getJSON(env, KV_STATS, { ...EMPTY_STATS });
  for (const [key, delta] of Object.entries(patch)) {
    stats[key] = (Number(stats[key]) || 0) + delta;
  }
  await putJSON(env, KV_STATS, stats);
  return stats;
}

async function getUser(env, userId) {
  return getJSON(env, KV_USER(userId), null);
}

async function saveUser(env, user) {
  await putJSON(env, KV_USER(user.id), user);
}

async function checkSubscription(env, userId) {
  const details = [];
  for (const channel of channels(env)) {
    try {
      const response = await bot(env, "getChatMember", { chat_id: channel, user_id: userId });
      details.push({ channel, ok: response.ok ? isSubscribed(response.result) : false });
    } catch (error) {
      console.error("getChatMember failed for " + channel, String(error));
      details.push({ channel, ok: false });
    }
  }
  return details;
}

async function handleStart(env, message) {
  const from = message.from || {};
  const lang = detectLang(from.language_code);
  const userId = String(from.id);
  const startPayload = String(message.text || "").trim().split(/\s+/)[1] || "";
  const sourcePayload = /^src_[A-Za-z0-9_-]{1,60}$/.test(startPayload) ? startPayload : "";
  const refPayload = sourcePayload ? null : parseRefPayload(message.text);
  let user = await getUser(env, userId);
  if (!user) {
    user = {
      id: userId,
      chat_id: message.chat.id,
      username: from.username || "",
      language: lang,
      ref_by: refPayload && refPayload !== userId ? refPayload : null,
      source: sourcePayload || null,
      ref_credited: false,
      subscribed: false,
      invites: 0,
      bonus_given: false,
      created_at: new Date().toISOString(),
    };
    await saveUser(env, user);
    await updateStats(env, { users: 1 });
  } else {
    user.language = lang;
    user.chat_id = message.chat.id;
    if (sourcePayload && user.source !== sourcePayload) user.source = sourcePayload;
    await saveUser(env, user);
  }
  if (startPayload.startsWith("src_")) {
    const kit = "✈️ Your free Travel Kit\n\n" +
      "• Cheap-flight checklist: https://links-tracker.valdislav-n.workers.dev/r/kit-flights\n" +
      "• City-break budgets: https://links-tracker.valdislav-n.workers.dev/r/kit-city-breaks\n" +
      "• eSIM picks: https://links-tracker.valdislav-n.workers.dev/r/kit-esim\n" +
      "• Insurance checklist: https://links-tracker.valdislav-n.workers.dev/r/kit-insurance\n\n" +
      "Daily finds: https://t.me/GOODTRAVEL007";
    await send(env, message.chat.id, kit + "\n\n" + legalLabel(lang, "privacy_hint"), mainKeyboard(env, lang));
    return;
  }
  if (startPayload.startsWith("offer_")) {
    await sendOffer(env, message.chat.id, lang, startPayload.slice(6));
    return;
  }
  await send(env, message.chat.id, text(lang, "start") + "\n\n" + legalLabel(lang, "privacy_hint"), mainKeyboard(env, lang));
}


async function handleDelete(env, message) {
  const userId = String(message.from.id);
  const lang = detectLang(message.from.language_code);
  await deleteRaw(env, KV_USER(userId));
  const keys = await redis(env, ["KEYS", "user:*"]);
  for (const key of keys || []) {
    const other = await getJSON(env, key, null);
    if (other !== null && String(other.ref_by) === userId) {
      other.ref_by = null;
      await putJSON(env, key, other);
    }
  }
  const participants = await getJSON(env, KV_PARTICIPANTS, []);
  await putJSON(env, KV_PARTICIPANTS, participants.filter((id) => String(id) === userId ? false : true));
  return send(env, message.chat.id, legalLabel(lang, "deleted"));
}

async function handleVerify(env, callback) {
  const userId = String(callback.from.id);
  const lang = callback.from.language_code ? detectLang(callback.from.language_code) : "en";
  const user = await getUser(env, userId);
  if (!user) {
    await answerCallback(env, callback.id, text(lang, "error"));
    return;
  }
  const details = await checkSubscription(env, userId);
  const missing = details.filter((item) => !item.ok);
  if (missing.length > 0) {
    const keyboard = missing.map((item) => [
      { text: item.channel, url: "https://t.me/" + item.channel.replace(/^@/, "") },
    ]);
    keyboard.push([{ text: text(lang, "check"), callback_data: "verify" }]);
    await send(env, user.chat_id, text(lang, "not_subscribed"), keyboard);
    await answerCallback(env, callback.id, "");
    return;
  }
  const wasSubscribed = user.subscribed;
  user.subscribed = true;
  let bonusLine = "";
  if (!wasSubscribed) {
    await updateStats(env, { verified: 1 });
    if (user.ref_by && !user.ref_credited) {
      user.ref_credited = true;
      const inviter = await getUser(env, user.ref_by);
      if (inviter) {
        inviter.invites = (Number(inviter.invites) || 0) + 1;
        const target = Number(env.REFERRAL_TARGET) || 0;
        if (target > 0 && inviter.invites >= target && !inviter.bonus_given && env.BONUS_URL) {
          inviter.bonus_given = true;
          await send(inviter.chat_id, text(inviter.language || "en", "referral_bonus", {
            n: inviter.invites,
          }) + env.BONUS_URL);
        } else if (target > 0) {
          await send(inviter.chat_id, text(inviter.language || "en", "referrals_count", {
            n: inviter.invites,
          }) + referralLink(env.BOT_USERNAME, inviter.id));
        }
        await saveUser(env, inviter);
        await updateStats(env, { referrals: 1 });
      }
    }
  }
  await saveUser(env, user);
  const reward = env.REWARD_URL ? text(lang, "reward") + env.REWARD_URL : text(lang, "reward_empty");
  await send(env, user.chat_id, text(lang, "subscribed") + "\n\n" + reward + bonusLine);
  await answerCallback(env, callback.id, text(lang, "subscribed"));
}

async function handleGiveaway(env, callback) {
  const userId = String(callback.from.id);
  const lang = callback.from.language_code ? detectLang(callback.from.language_code) : "en";
  const user = await getUser(env, userId);
  if (!user) {
    await answerCallback(env, callback.id, text(lang, "error"), true);
    return;
  }
  const active = await getRaw(env, KV_ACTIVE);
  if (active !== "1") {
    await answerCallback(env, callback.id, text(lang, "giveaway_closed"), true);
    return;
  }
  if (!user.subscribed) {
    const details = await checkSubscription(env, userId);
    if (details.some((item) => !item.ok)) {
      await answerCallback(env, callback.id, text(lang, "giveaway_need_sub"), true);
      return;
    }
    user.subscribed = true;
    await saveUser(env, user);
  }
  const participants = await getJSON(env, KV_PARTICIPANTS, []);
  if (participants.includes(userId)) {
    await answerCallback(env, callback.id, text(lang, "giveaway_already"), true);
    return;
  }
  participants.push(userId);
  await putJSON(env, KV_PARTICIPANTS, participants);
  await updateStats(env, { giveaway_entries: 1 });
  await answerCallback(env, callback.id, text(lang, "giveaway_joined"), true);
}

async function handleReferral(env, callback) {
  const userId = String(callback.from.id);
  const lang = callback.from.language_code ? detectLang(callback.from.language_code) : "en";
  const user = await getUser(env, userId);
  const invites = user ? Number(user.invites) || 0 : 0;
  const link = referralLink(env.BOT_USERNAME, userId);
  const message = invites > 0
    ? text(lang, "referrals_count", { n: invites }) + link
    : text(lang, "referrals_none") + link;
  await answerCallback(env, callback.id, message, true);
}

async function handleCatalog(env, callback) {
  const lang = callback.from.language_code ? detectLang(callback.from.language_code) : "en";
  const items = channels(env).map((channel) => [
    { text: channel, url: "https://t.me/" + channel.replace(/^@/, "") },
  ]);
  await answerCallback(env, callback.id, text(lang, "catalog_title"), true);
  await send(env, callback.message.chat.id, text(lang, "catalog_title"), items);
}

async function handleAdmin(env, message, command) {
  const userId = String(message.from.id);
  if (String(env.ADMIN_ID) !== userId) {
    await send(env, message.chat.id, "Admin only.");
    return true;
  }
  if (command === "/stats") {
    const stats = await getJSON(env, KV_STATS, { ...EMPTY_STATS });
    const participants = await getJSON(env, KV_PARTICIPANTS, []);
    await send(env, message.chat.id,
      "📊 users=" + (stats.users || 0) +
      " verified=" + (stats.verified || 0) +
      " referrals=" + (stats.referrals || 0) +
      " giveaway_entries=" + participants.length +
      " active=" + ((await getRaw(env, KV_ACTIVE)) === "1" ? "on" : "off"));
    return true;
  }
  if (command === "/sources") {
    const keys = await redis(env, ["KEYS", "user:*"]);
    const counts = {};
    for (const key of keys || []) {
      const user = await getJSON(env, key, null);
      if (user === null) continue;
      const source = String(user.source || "unknown").slice(0, 80);
      counts[source] = (counts[source] || 0) + 1;
    }
    const lines = Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([source, n]) => source + "=" + n);
    await send(env, message.chat.id, "📈 sources: " + (lines.join(" ") || "none"));
    return true;
  }
  if (command === "/draw") {
    const participants = await getJSON(env, KV_PARTICIPANTS, []);
    const winnerId = pickWinner(participants, () => crypto.getRandomValues(new Uint32Array(1))[0] / 2 ** 32);
    if (!winnerId) {
      await send(env, message.chat.id, "No participants yet.");
      return true;
    }
    const winner = await getUser(env, winnerId);
    const label = formatUserLabel(winner || { id: winnerId });
    await send(env, message.chat.id, "🎉 Winner: " + label + " (id " + winnerId + ")");
    if (env.ANNOUNCE_CHANNEL) {
      await send(env, env.ANNOUNCE_CHANNEL, "🎉 Розыгрыш завершён! Победитель: " + label);
    }
    await putJSON(env, KV_PARTICIPANTS, []);
    return true;
  }
  if (command === "/giveaway") {
    const arg = (message.text || "").split(/\s+/)[1];
    if (arg === "on") {
      await putRaw(env, KV_ACTIVE, "1");
      await send(env, message.chat.id, "Giveaway: ON");
      if (env.ANNOUNCE_CHANNEL) {
        const lang = detectLang(env.GIVEAWAY_LANG || "en");
        await send(env, env.ANNOUNCE_CHANNEL, text(lang, "giveaway_post"), [
          [{ text: text(lang, "giveaway_join"), callback_data: "giveaway" }],
        ]);
        await send(env, message.chat.id, "Giveaway post sent to " + env.ANNOUNCE_CHANNEL);
      }
    } else if (arg === "off") {
      await putRaw(env, KV_ACTIVE, "0");
      await send(env, message.chat.id, "Giveaway: OFF");
    } else {
      await send(env, message.chat.id, "Usage: /giveaway on|off");
    }
    return true;
  }
  return false;
}

async function handleCallback(env, callback) {
  const data = callback.data || "";
  const lang = callback.from.language_code ? detectLang(callback.from.language_code) : "en";
  if (data === "verify") return handleVerify(env, callback);
  if (data === "giveaway") return handleGiveaway(env, callback);
  if (data === "referral") return handleReferral(env, callback);
  if (data === "catalog") return handleCatalog(env, callback);
  if (data === "rules") return answerCallback(env, callback.id, text(lang, "rules"), true);
  if (data === "offers") {
    await answerCallback(env, callback.id, "");
    return sendOffers(env, callback.message.chat.id, lang);
  }
  if (data.startsWith("offer:")) {
    await answerCallback(env, callback.id, "");
    return sendOffer(env, callback.message.chat.id, lang, data.slice(6));
  }
  return answerCallback(env, callback.id, "");
}


async function handleUpdate(env, update) {
  if (update.callback_query) return handleCallback(env, update.callback_query);
  const message = update.message;
  if (message === undefined || message === null) return;
  if (message.from === undefined || message.from === null) return;
  if (message.text === undefined || message.text === null) return;
  const lang = detectLang(message.from.language_code);
  const parts = message.text.trim().split(/\s+/);
  const command = parts[0].split("@")[0];
  if (command === "/start") return handleStart(env, message);
  if (command === "/help") return send(env, message.chat.id, text(lang, "help") + "\n\n" + legalLabel(lang, "privacy_hint"));
  if (command === "/rules") return send(env, message.chat.id, text(lang, "rules"));
  if (command === "/privacy") return send(env, message.chat.id, legalLabel(lang, "privacy"));
  if (command === "/delete") return handleDelete(env, message);
  if (command === "/offers") return sendOffers(env, message.chat.id, lang);
  if (command === "/offer") return sendOffer(env, message.chat.id, lang, parts[1] || "");
  if (command === "/search") {
    const query = parts.slice(1).join(" ").toLowerCase();
    const found = query.length === 0 ? OFFERS : OFFERS.filter((offer) => {
      const haystack = [offer.title, offer.title_en, offer.description, offer.description_en, offer.category].join(" ").toLowerCase();
      return haystack.includes(query);
    });
    if (found.length === 0) return send(env, message.chat.id, offerLabel(lang, "not_found"));
    return send(env, message.chat.id, offersListText(found, lang), offersKeyboard(found, lang));
  }
  if (["/stats", "/draw", "/giveaway"].includes(command)) {
    return handleAdmin(env, message, command);
  }
}


export default {
  async fetch(request, env) {
    if (request.method === "GET") {
      const url = new URL(request.url);
      if (url.pathname === "/admin/stats") {
        const token = url.searchParams.get("token") || request.headers.get("x-token") || "";
        if (token !== env.STATS_TOKEN) return new Response("forbidden", { status: 403 });
        const stats = await getJSON(env, KV_STATS, { ...EMPTY_STATS });
        const keys = await redis(env, ["KEYS", "user:*"]);
        const sources = {};
        let users = 0;
        let verified = 0;
        for (const key of keys || []) {
          const user = await getJSON(env, key, null);
          if (user === null) continue;
          users += 1;
          if (user.subscribed === true) verified += 1;
          const source = String(user.source || "unknown").slice(0, 80);
          sources[source] = (sources[source] || 0) + 1;
        }
        return Response.json({ ok: true, stats, users, verified, sources });
      }
      return new Response("growth-bot ok");
    }
    if (env.WEBHOOK_SECRET) {
      const secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token");
      if (secret !== env.WEBHOOK_SECRET) {
        return new Response("forbidden", { status: 403 });
      }
    }
    let update;
    try {
      update = await request.json();
    } catch {
      return new Response("bad request", { status: 400 });
    }
    try {
      await handleUpdate(env, update);
    } catch (error) {
      console.error("update failed", String(error));
    }
    return new Response("ok");
  },
};
