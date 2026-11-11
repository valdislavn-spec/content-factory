const OLD_WEBHOOK = 'https://backend-git-production-cb93.up.railway.app/webhook/9273924219';
const TIERS = { 50: '50 ⭐', 100: '100 ⭐', 250: '250 ⭐' };

function apiBase() {
  return typeof TG_API_BASE !== 'undefined' && TG_API_BASE ? TG_API_BASE : 'https://api.telegram.org';
}

async function tg(method, payload) {
  const res = await fetch(`${apiBase()}/bot${BOT_TOKEN}/${method}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return res;
}

async function forward(raw) {
  try {
    await fetch(OLD_WEBHOOK, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: raw,
    });
  } catch (e) {
    // keep payment handling independent from the legacy webhook
  }
}

function keyboard() {
  return {
    inline_keyboard: [
      [
        { text: 'Поддержать 50 ⭐', callback_data: 'donate_50' },
        { text: 'Поддержать 100 ⭐', callback_data: 'donate_100' },
      ],
      [{ text: 'Поддержать 250 ⭐', callback_data: 'donate_250' }],
    ],
  };
}

async function handleRequest(request) {
  if (request.method === 'GET') {
    return new Response('cf-stars online', { status: 200 });
  }
  const secret = request.headers.get('x-telegram-bot-api-secret-token');
  if (typeof WEBHOOK_SECRET !== 'undefined' && WEBHOOK_SECRET && secret !== WEBHOOK_SECRET) {
    return new Response('forbidden', { status: 403 });
  }
  const raw = await request.text();
  let update;
  try { update = JSON.parse(raw); } catch { return new Response('ok'); }

  try {
    if (update.pre_checkout_query) {
      await tg('answerPreCheckoutQuery', {
        pre_checkout_query_id: update.pre_checkout_query.id,
        ok: true,
      });
      return new Response('ok');
    }
    if (update.callback_query) {
      const q = update.callback_query;
      const data = q.data || '';
      await tg('answerCallbackQuery', { callback_query_id: q.id });
      if (data.startsWith('donate_')) {
        const amount = parseInt(data.slice('donate_'.length), 10);
        if (TIERS[amount] && q.message) {
          await tg('sendInvoice', {
            chat_id: q.message.chat.id,
            title: 'Поддержать Content Factory',
            description: 'Добровольная поддержка проекта: 6 Telegram-каналов, AI-бот и открытые инструменты. Спасибо!',
            payload: `support_${amount}_${q.from?.id || 0}`,
            currency: 'XTR',
            prices: [{ label: 'Поддержка проекта', amount }],
          });
        }
      }
      return new Response('ok');
    }
    if (update.message && update.message.successful_payment) {
      const p = update.message.successful_payment;
      await tg('sendMessage', {
        chat_id: update.message.chat.id,
        text: `Спасибо за поддержку на ${p.total_amount} ⭐!\n\nЭто помогает держать каналы и AI-бота онлайн.`,
        reply_markup: keyboard(),
      });
      return new Response('ok');
    }
    const text = update.message?.text || '';
    if (/^\/donate(@\w+)?(\s|$)/.test(text)) {
      await tg('sendMessage', {
        chat_id: update.message.chat.id,
        text: 'Поддержать Content Factory звёздами Telegram ⭐\n\nВыберите сумму — оплата проходит через Telegram Stars, без карты и внешних сайтов.',
        reply_markup: keyboard(),
      });
      return new Response('ok');
    }
  } catch (e) {
    // fall through to forwarding so legacy bot keeps working
  }

  await forward(raw);
  return new Response('ok');
}

addEventListener('fetch', (event) => {
  event.respondWith(handleRequest(event.request));
});
