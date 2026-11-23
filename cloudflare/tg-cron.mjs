import { API_PREFIX, apiFetch } from "./state-api.mjs";
// Планировщик публикаций + мониторинг content-factory.
// Cloudflare cron (*/15) дёргает GitHub Actions через workflow_dispatch с
// антидублем. Сбои диспатча, «протухшее» состояние и пропуски самого cron
// уходят алертом в Telegram (KV хранит антиспам-состояние).
const GH_REPO = 'valdislavn-spec/content-factory';
const GH_WORKFLOW = 'content-factory.yml';
const RUN_NAME = 'content-factory-cloud-en-es';
const STALE_MIN = 8;            // не дублируем запуск, если он был < N минут назад
const HEALTH_MAX_AGE_MIN = 120; // health: запуск старше 2 часов = проблема
const ALERT_COOLDOWN_MIN = 180; // один и тот же алерт не чаще раза в 3 часа
const SCHEDULE_GAP_MAX_MIN = 45; // cron */15 не должен «молчать» дольше 45 минут
const RETRY_STUCK_MIN = 30;      // очередь ретраев не должна стоять дольше 30 минут

function api(path) {
  return `https://api.github.com/repos/${GH_REPO}${path}`;
}

function ghHeaders(env) {
  return {
    Authorization: 'Bearer ' + env.GITHUB_TOKEN,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'cf-cron',
    'Content-Type': 'application/json',
  };
}

async function latestRun(env) {
  const res = await fetch(api('/actions/workflows/' + GH_WORKFLOW + '/runs?per_page=8'), { headers: ghHeaders(env) });
  if (!res.ok) return { error: res.status, text: (await res.text()).slice(0, 200) };
  const data = await res.json();
  const runs = data.workflow_runs || [];
  const last = runs[0];
  if (!last) return { none: true };
  return {
    id: last.id,
    number: last.run_number,
    event: last.event,
    status: last.status,
    conclusion: last.conclusion,
    created_at: last.created_at,
    html_url: last.html_url,
  };
}

async function dispatch(env) {
  const res = await fetch(api(`/actions/workflows/${GH_WORKFLOW}/dispatches`), {
    method: 'POST',
    headers: ghHeaders(env),
    body: JSON.stringify({ ref: 'main', inputs: { publish: 'live' } }),
  });
  return { status: res.status, body: (await res.text()).slice(0, 200), at: new Date().toISOString() };
}

async function tgAlert(env, text) {
  const token = env.TELEGRAM_BOT_TOKEN;
  const chat = env.TELEGRAM_ALERT_CHAT_ID;
  if (!token || !chat) {
    console.log('tgAlert skipped: secrets not set');
    return;
  }
  const base = (env.TELEGRAM_API_BASE || 'https://api.telegram.org').replace(/\/+$/, '');
  const body = new URLSearchParams({ chat_id: chat, text: String(text).slice(0, 3900) });
  try {
    const res = await fetch(`${base}/bot${token}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
    });
    console.log('tgAlert', res.status);
  } catch (e) {
    console.log('tgAlert error', String(e));
  }
}

async function getState(env) {
  try {
    return (await env.STATE.get('monitor', 'json')) || {};
  } catch (e) {
    console.log('kv get error', String(e));
    return {};
  }
}

async function putState(env, state) {
  try {
    await env.STATE.put('monitor', JSON.stringify(state));
  } catch (e) {
    console.log('kv put error', String(e));
  }
}

function ageMinutes(last) {
  if (!last || !last.created_at) return null;
  return (Date.now() - Date.parse(last.created_at)) / 60000;
}

function healthOf(last) {
  const age = ageMinutes(last);
  const known = last && !last.error && !last.none;
  // Свежий run может быть ещё in_progress — мы сами только что его запустили,
  // это не проблема. Алертим только по завершённым run'ам или по долгой тишине.
  const finished = Boolean(last && last.status === 'completed');
  const healthy =
    known &&
    age !== null &&
    age <= HEALTH_MAX_AGE_MIN &&
    (!finished || last.conclusion !== 'failure');
  return { healthy, age, known };
}

async function queueSummary(env) {
  if (env.DB === undefined || env.DB === null) return null;
  try {
    const row = await env.DB.prepare(
      "SELECT COUNT(*) AS total, " +
      "SUM(CASE WHEN attempts >= 5 THEN 1 ELSE 0 END) AS exhausted, " +
      "MIN(next_attempt_at) AS oldest FROM publish_retries"
    ).first();
    const total = Number((row && row.total) || 0);
    const exhausted = Number((row && row.exhausted) || 0);
    const oldest = row && row.oldest ? String(row.oldest) : null;
    const oldestMs = oldest ? Date.parse(oldest) : null;
    const stuck = total > 0 && oldestMs !== null &&
      oldestMs < Date.now() - RETRY_STUCK_MIN * 60000;
    return { total, exhausted, oldest, stuck };
  } catch (e) {
    console.log("queue summary error", String(e));
    return { error: String(e).slice(0, 200) };
  }
}

async function healthPayload(last, env) {
  const { healthy, age } = healthOf(last);
  const queue = await queueSummary(env);
  const queueOk = queue === null || queue.stuck === false || queue.stuck === undefined;
  return {
    ok: healthy && queueOk,
    worker: 'tg-cron',
    mode: 'scheduled-only',
    last_run: last || null,
    age_min: age === null ? null : Math.round(age),
    queue,
    checked_at: new Date().toISOString(),
  };
}

function cooldownPassed(state) {
  if (!state.last_alert_at) return true;
  return (Date.now() - Date.parse(state.last_alert_at)) / 60000 >= ALERT_COOLDOWN_MIN;
}

export default {
  // Публичный HTTP: только health-check, запуск публикации снаружи невозможен.
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith(API_PREFIX + "/")) {
      return apiFetch(request, env);
    }
    const last = await latestRun(env);
    const payload = await healthPayload(last, env);
    return new Response(JSON.stringify(payload), {
      status: payload.ok ? 200 : 503,
      headers: { 'content-type': 'application/json', 'cache-control': 'no-store' },
    });
  },
  async scheduled(event, env, ctx) {
    ctx.waitUntil(
      (async () => {
        const state = await getState(env);
        const now = Date.now();
        try {

        // 1) сам cron не запускался дольше ожидаемого → алерт
        if (state.last_scheduled_at) {
          const gap = (now - Date.parse(state.last_scheduled_at)) / 60000;
          if (gap > SCHEDULE_GAP_MAX_MIN && cooldownPassed(state)) {
            await tgAlert(
              env,
              `⚠️ Cloudflare cron content-factory молчал ${Math.round(gap)} мин (ожидается каждые 15). Проверь Worker tg-cron и триггеры.`
            );
            state.last_alert_at = new Date().toISOString();
          }
        }

        // 2) диспатч в GitHub Actions (с антидублем)
        const last = await latestRun(env);
        const age = ageMinutes(last);
        if (age !== null && age < STALE_MIN) {
          console.log('dispatch skipped: recent run', last.id, last.status, last.conclusion, 'age_min=', age);
        } else {
          let result = await dispatch(env);
          if (result.status !== 204) result = await dispatch(env);
          console.log('dispatch', JSON.stringify({ last, age_min: age, result }));
          if (result.status !== 204) {
            await tgAlert(
              env,
              `❌ content-factory: Cloudflare не смог запустить GitHub Actions (status ${result.status}). Проверь GITHUB_TOKEN/репозиторий.\n${result.body || ''}`
            );
            state.last_alert_at = new Date().toISOString();
            state.alert_active = true;
          }
        }

        // 3) health: последний запуск слишком старый/упал → алерт (антиспам 3ч)
        const latest = await latestRun(env);
        const health = healthOf(latest);
        if (!health.healthy) {
          if (cooldownPassed(state) && !state.alert_active) {
            const details = latest && latest.error ? `GitHub API error ${latest.error}` : `последний run: ${latest && latest.created_at} · ${latest && latest.conclusion}`;
            await tgAlert(
              env,
              `⚠️ content-factory health: ${details} (возраст ${health.age === null ? '?' : Math.round(health.age)} мин). Проверь Actions и планировщик.`
            );
            state.last_alert_at = new Date().toISOString();
            state.alert_active = true;
          }
        } else if (state.alert_active) {
          // Сбрасываем флаг ДО отправки: если Telegram недоступен, алерты не
          // должны навсегда заглушиться «залипшим» alert_active.
          state.alert_active = false;
          await tgAlert(env, '✅ content-factory восстановился: публикации снова идут.');
        }

        // 4) health D1-очереди ретраев: застрявшие due-записи → алерт.
        const queue = await queueSummary(env);
        if (queue && queue.stuck && cooldownPassed(state) && state.queue_alert_active !== true) {
          await tgAlert(
            env,
            `⚠️ content-factory: очередь ретраев стоит ${queue.total} шт., самая старая с ${queue.oldest}. Проверь последние запуски и D1.`
          );
          state.last_alert_at = new Date().toISOString();
          state.queue_alert_active = true;
        } else if (queue && queue.stuck === false && state.queue_alert_active === true) {
          state.queue_alert_active = false;
          await tgAlert(env, '✅ content-factory: очередь ретраев разобрана.');
        }
        } finally {
          // Состояние сохраняем всегда — иначе падение шага оставляет
          // last_scheduled_at старым и провоцирует ложный алерт о простое.
          state.last_scheduled_at = new Date().toISOString();
          await putState(env, state);
        }
      })()
    );
  },
};
