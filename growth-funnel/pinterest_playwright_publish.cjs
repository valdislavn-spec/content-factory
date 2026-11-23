/* Publish due Pinterest pins through the logged-in Playwright profile.
 * Fallback for the Pinterest API Trial restriction.
 * Uses the same durable D1 queue as auto_publish.py.
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const PROFILE = process.env.PINTEREST_PROFILE || '/Users/vd/Documents/deepseek-harness/default-workspace/tools/playwright-mcp/profile-tp2';
const PLAYWRIGHT = '/Users/vd/Documents/deepseek-harness/default-workspace/tools/playwright-mcp/node_modules/.pnpm/playwright@1.65.0-alpha-2026-10-30/node_modules/playwright';
const { chromium } = require(PLAYWRIGHT);

function loadEnv(file) {
  const out = {};
  if (fs.existsSync(file) === false) return out;
  for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const trimmed = line.trim();
    if (trimmed === '' || trimmed.startsWith('#')) continue;
    const eq = trimmed.indexOf('=');
    if (eq < 0) continue;
    const key = trimmed.slice(0, eq).trim();
    let value = trimmed.slice(eq + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    out[key] = value;
  }
  return out;
}

const env = Object.assign({}, loadEnv(path.join(ROOT, '.env')), process.env);
const BASE = String(env.LINK_TRACKER_BASE || 'https://links-tracker.valdislav-n.workers.dev').replace(/\/+$/, '');
const QUEUE_URL = String(env.GROWTH_QUEUE_URL || (BASE + '/admin/queue')).replace(/\/+$/, '');
const TOKEN = String(env.LINK_TRACKER_ADMIN_TOKEN || '').trim();
const TODAY = new Date().toISOString().slice(0, 10);

function log(obj) {
  console.log(JSON.stringify(obj, null, 2));
}

async function queueGet() {
  const url = QUEUE_URL + '?platform=pinterest&status=queued&due_before=' + encodeURIComponent(TODAY);
  const res = await fetch(url, { headers: { 'x-token': TOKEN } });
  const data = await res.json();
  if (res.ok === false || data.ok === false) throw new Error('queue read failed: ' + JSON.stringify(data).slice(0, 300));
  return data.items || [];
}

async function queueUpdate(id, fields) {
  const res = await fetch(QUEUE_URL + '/update', {
    method: 'POST',
    headers: { 'x-token': TOKEN, 'content-type': 'application/json' },
    body: JSON.stringify(Object.assign({ id: id }, fields)),
  });
  const data = await res.json();
  if (res.ok === false || data.ok === false) throw new Error('queue update failed: ' + JSON.stringify(data).slice(0, 300));
  return data;
}

function escapeRe(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

async function fillFirst(page, selectors, value) {
  for (const selector of selectors) {
    const loc = page.locator(selector).first();
    const count = await loc.count().catch(function () { return 0; });
    if (count === 0) continue;
    try {
      await loc.fill(value, { timeout: 8000 });
      return true;
    } catch (e) {
      try {
        await loc.click({ timeout: 4000 });
        await page.keyboard.type(value, { delay: 5 });
        return true;
      } catch (e2) {}
    }
  }
  return false;
}

async function verifyPin(page, title) {
  await page.goto('https://www.pinterest.com/VladislavPint/_created/', { waitUntil: 'domcontentloaded', timeout: 90000 }).catch(function () {});
  await page.waitForTimeout(8000);
  for (let i = 0; i < 4; i += 1) {
    await page.mouse.wheel(0, 1200);
    await page.waitForTimeout(1200);
  }
  return page.evaluate(function (wanted) {
    const links = Array.from(document.querySelectorAll('a[href*="/pin/"]'));
    for (const link of links) {
      const label = String(link.getAttribute('aria-label') || link.innerText || '');
      if (label.indexOf(wanted) >= 0 && /\/pin\/\d+/.test(link.href)) {
        return { ok: true, url: link.href };
      }
    }
    return { ok: false, url: '' };
  }, title);
}

async function publishOne(page, item) {
  const imagePath = path.isAbsolute(item.image) ? item.image : path.join(ROOT, item.image);
  if (fs.existsSync(imagePath) === false) throw new Error('image missing: ' + imagePath);
  await page.goto('https://www.pinterest.com/pin-builder/', { waitUntil: 'domcontentloaded', timeout: 90000 });
  await page.waitForTimeout(6000);
  await page.locator('input[type=file]').first().setInputFiles(imagePath, { timeout: 20000 });
  await page.waitForTimeout(6000);

  const titleOk = await fillFirst(page, ['textarea[placeholder*="название"]', 'input[placeholder*="название"]'], item.title);
  const descOk = await fillFirst(page, ['textarea[placeholder*="описание"]', '[aria-label*="описание"]', 'div[contenteditable="true"]'], item.description);
  const linkOk = await fillFirst(page, ['input[placeholder*="ссылк"]', 'textarea[placeholder*="ссылк"]'], item.link);
  await page.waitForTimeout(1500);

  await page.locator('[data-test-id="board-dropdown-select-button"]').first().click({ timeout: 12000 });
  await page.waitForTimeout(1500);
  let boardOk = false;
  const row = page.locator('[data-test-id="board-row-' + item.board + '"]').first();
  if (await row.count().catch(function () { return 0; })) {
    await row.scrollIntoViewIfNeeded().catch(function () {});
    await row.click({ timeout: 6000 });
    boardOk = true;
  }
  if (boardOk === false) {
    const byText = page.getByText(item.board, { exact: true }).first();
    if (await byText.count().catch(function () { return 0; })) {
      await byText.scrollIntoViewIfNeeded().catch(function () {});
      await byText.click({ timeout: 6000 });
      boardOk = true;
    }
  }
  await page.waitForTimeout(1500);
  await page.locator('[data-test-id="board-dropdown-save-button"]').first().evaluate(function (node) { node.click(); });
  await page.waitForTimeout(9000);
  const body = await page.evaluate(function () { return document.body.innerText || ''; });
  const success = body.indexOf('Вы создали пин') >= 0 || body.indexOf('Открыть пин') >= 0;
  const links = await page.evaluate(function () {
    return Array.from(document.querySelectorAll('a[href*="/pin/"]')).map(function (a) { return a.href; });
  });
  let pinUrl = '';
  for (const link of links) {
    if (/\/pin\/\d+/.test(link)) { pinUrl = link; break; }
  }
  let verified = { ok: false, url: '' };
  if (success === false) verified = await verifyPin(page, item.title);
  return { ok: success || verified.ok, pin_url: pinUrl || verified.url, verified: verified.ok, titleOk: titleOk, descOk: descOk, linkOk: linkOk, boardOk: boardOk, bodyTail: body.slice(-500) };
}

async function main() {
  const dryRun = process.argv.includes('--dry-run');
  const items = await queueGet();
  if (dryRun) {
    log({ mode: 'dry-run', today: TODAY, count: items.length, items: items.slice(0, 3).map(function (x) { return { id: x.id, due: x.due, board: x.board, title: x.title }; }) });
    return;
  }
  if (items.length === 0) {
    log({ ok: true, skipped: 'no due pinterest items', today: TODAY });
    return;
  }
  const item = items[0];
  const lock = '/tmp/goodtravel-pinterest.lock';
  let fd;
  try {
    fd = fs.openSync(lock, 'wx');
  } catch (e) {
    log({ ok: true, skipped: 'another pinterest publisher is active', id: item.id });
    return;
  }
  let context;
  let debugPage = null;
  try {
    context = await chromium.launchPersistentContext(PROFILE, {
      headless: false,
      viewport: { width: 1280, height: 900 },
      args: ['--no-sandbox', '--password-store=basic', '--use-mock-keychain'],
      locale: 'ru-RU',
    });
    const page = context.pages()[0] || await context.newPage();
    debugPage = page;
    const result = await publishOne(page, item);
    const attempts = (Number(item.attempts) || 0) + 1;
    const updated = Object.assign({}, item, {
      status: result.ok ? 'published' : 'queued',
      published_at: result.ok ? TODAY : item.published_at,
      published_url: result.ok ? (result.pin_url || '') : item.published_url,
      attempts: attempts,
      last_error: result.ok ? null : 'playwright: ' + String(result.bodyTail || 'publish not confirmed').slice(0, 240),
    });
    await queueUpdate(item.id, {
      status: updated.status,
      attempts: attempts,
      published_at: updated.published_at,
      published_url: updated.published_url,
      last_error: updated.last_error,
      payload: updated,
    });
    log({ ok: result.ok, id: item.id, title: item.title, board: item.board, pin_url: result.pin_url, verified: result.verified, titleOk: result.titleOk, descOk: result.descOk, linkOk: result.linkOk, boardOk: result.boardOk });
    process.exitCode = result.ok ? 0 : 1;
  } catch (e) {
    if (debugPage) {
      await debugPage.screenshot({ path: path.join(ROOT, 'growth-funnel', 'pinterest-failure.png'), fullPage: false }).catch(function () {});
      const debugText = await debugPage.evaluate(function () { return document.body.innerText || ''; }).catch(function () { return ''; });
      console.error('DEBUG_URL', debugPage.url());
      console.error('DEBUG_TEXT', debugText.replace(/\n+/g, ' | ').slice(0, 1200));
      const debugNodes = await debugPage.evaluate(function () {
        const out = [];
        const nodes = document.querySelectorAll('button, [role="button"], [role="option"], [data-test-id]');
        for (const node of nodes) {
          const text = String(node.innerText || node.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ');
          if (text.length === 0) continue;
          out.push({ tag: node.tagName, role: node.getAttribute('role'), testid: node.getAttribute('data-test-id'), text: text.slice(0, 120) });
        }
        return out.slice(0, 120);
      }).catch(function () { return []; });
      console.error('DEBUG_NODES', JSON.stringify(debugNodes));
    }
    const attempts = (Number(item.attempts) || 0) + 1;
    const message = String(e && e.message ? e.message : e).slice(0, 300);
    await queueUpdate(item.id, {
      status: 'queued',
      attempts: attempts,
      last_error: 'playwright: ' + message,
      payload: Object.assign({}, item, { status: 'queued', attempts: attempts, last_error: 'playwright: ' + message }),
    }).catch(function () {});
    log({ ok: false, id: item.id, error: message });
    process.exitCode = 1;
  } finally {
    if (context) await context.close().catch(function () {});
    if (fd !== undefined) {
      try { fs.closeSync(fd); } catch (e) {}
      try { fs.unlinkSync(lock); } catch (e) {}
    }
  }
}

main().catch(function (e) {
  console.error('FATAL', e && e.message ? e.message : e);
  process.exit(1);
});
