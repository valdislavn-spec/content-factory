#!/usr/bin/env node
/**
 * Publish Travel Finds pins through the Pinterest web UI (pin-builder),
 * because API pin creation is blocked while the app has Trial access
 * (POST /v5/pins -> 403 code 29).
 *
 * Keeps its own idempotency: pins whose tracking link is already on the
 * target board are skipped, so re-runs never create duplicates.
 *
 * Usage:
 *   node scripts/pinterest_publish_browser.cjs future-01-lisbon-48h future-02-bali-budget
 *   node scripts/pinterest_publish_browser.cjs --dry future-01-lisbon-48h
 *
 * Env:
 *   PINTEREST_PROFILE  persistent Chromium profile (default: tools/playwright-mcp/profile-tp2)
 *   PW_MODULE          path to the playwright module (default: tools/playwright-mcp/node_modules/...)
 *   PW_BROWSERS        PLAYWRIGHT_BROWSERS_PATH (default: tools/playwright-mcp/ms-playwright)
 */
const fs = require('fs');
const path = require('path');

const WS = '/Users/vd/Documents/deepseek-harness/default-workspace';
const REPO = path.join(WS, 'content-factory');
const PINS_JSON = path.join(REPO, 'docs/travel-finds/pins/future-pins.json');
const PROFILE = process.env.PINTEREST_PROFILE || path.join(WS, 'tools/playwright-mcp/profile-tp2');
const PW_MODULE = process.env.PW_MODULE ||
  path.join(WS, 'tools/playwright-mcp/node_modules/.pnpm/playwright@1.65.0-alpha-2026-10-30/node_modules/playwright');
if (!process.env.PLAYWRIGHT_BROWSERS_PATH && fs.existsSync(path.join(WS, 'tools/playwright-mcp/ms-playwright'))) {
  process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(WS, 'tools/playwright-mcp/ms-playwright');
}
const OUT = path.join(WS, 'tools/playwright-mcp/output/state');
const { chromium } = require(PW_MODULE);

const args = process.argv.slice(2);
const DRY = args.includes('--dry');
const ids = args.filter((a) => !a.startsWith('--'));
if (!ids.length) {
  console.error('usage: node scripts/pinterest_publish_browser.cjs [--dry] <pin-id> [pin-id ...]');
  process.exit(2);
}

const allPins = JSON.parse(fs.readFileSync(PINS_JSON, 'utf8'));
const selected = ids.map((id) => {
  const pin = allPins.find((p) => p.id === id || p.slug === id);
  if (!pin) throw new Error(`pin not found in future-pins.json: ${id}`);
  return pin;
});

function pinterestToken() {
  const tokenPath = path.join(WS, '.local/affiliate/pinterest-oauth-token.json');
  return JSON.parse(fs.readFileSync(tokenPath, 'utf8')).access_token;
}

function api(method, url, token, body) {
  // Node's built-in fetch is unreliable behind the local sandbox proxy here
  // ("terminated" on api.pinterest.com), so use curl for the few read calls.
  const { spawnSync } = require('child_process');
  const args = ['-sS', '-m', '45', '-X', method, url,
    '-H', `Authorization: Bearer ${token}`,
    '-H', 'Content-Type: application/json',
    '-w', '\n%{http_code}'];
  if (body !== undefined) args.push('--data-binary', JSON.stringify(body));
  const res = spawnSync('curl', args, { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 });
  if (res.error) throw res.error;
  const out = (res.stdout || '').trimEnd();
  const nl = out.lastIndexOf('\n');
  const status = parseInt(out.slice(nl + 1), 10) || 0;
  const text = nl >= 0 ? out.slice(0, nl) : '';
  let json = null;
  try { json = JSON.parse(text); } catch (_) {}
  return { status, json, text };
}

async function boardPins(boardId, token) {
  const items = [];
  let bookmark = '';
  for (;;) {
    const q = `?page_size=100${bookmark ? `&bookmark=${encodeURIComponent(bookmark)}` : ''}`;
    const { status, json } = await api('GET', `https://api.pinterest.com/v5/boards/${boardId}/pins${q}`, token);
    if (status !== 200) throw new Error(`board pins failed ${status}: ${JSON.stringify(json)}`);
    items.push(...(json.items || []));
    bookmark = json.bookmark || '';
    if (!bookmark) return items;
  }
}

async function findBoardId(name, token) {
  const { status, json } = await api('GET', 'https://api.pinterest.com/v5/boards?page_size=100', token);
  if (status !== 200) throw new Error(`boards failed ${status}`);
  const hit = (json.items || []).find((b) => (b.name || '').trim().toLowerCase() === name.trim().toLowerCase());
  if (!hit) throw new Error(`board not found: ${name}`);
  return hit.id;
}

async function fillDescription(page, desc) {
  const variants = [
    page.locator('[aria-label*="описание"]').first(),
    page.locator('textarea').nth(2),
    page.locator('[contenteditable="true"]').last(),
  ];
  for (const loc of variants) {
    try {
      if (!(await loc.count())) continue;
      await loc.click({ timeout: 4000 });
      await loc.fill('', { timeout: 4000 }).catch(() => {});
      await loc.type(desc, { delay: 4, timeout: 15000 });
      return true;
    } catch (_) { /* try next */ }
  }
  return false;
}

async function pickBoard(page, boardName, log) {
  const current = await page.locator('[data-test-id="board-dropdown-select-button"]').first().innerText().catch(() => '');
  log.boardBefore = (current || '').trim().slice(0, 60);
  if (current && current.trim().toLowerCase() === boardName.trim().toLowerCase()) {
    log.boardPicked = 'already';
    return true;
  }
  try {
    await page.locator('[data-test-id="board-dropdown-select-button"]').first().click({ timeout: 8000 });
  } catch (e) {
    log.boardOpenErr = e.message.slice(0, 120);
    return false;
  }
  await page.waitForTimeout(2500);
  try {
    const search = page.locator('[data-test-id*="board"] input[type="text"], input[role="searchbox"]').first();
    if (await search.count()) { await search.fill(boardName, { timeout: 6000 }); }
  } catch (e) { log.boardSearchErr = e.message.slice(0, 120); }
  await page.waitForTimeout(2500);
  let picked = false;
  const candidates = [
    page.locator('[data-test-id*="board-dropdown-item"]', { hasText: boardName }).first(),
    page.locator('[role="option"]', { hasText: boardName }).first(),
    page.getByText(boardName, { exact: true }).first(),
  ];
  for (const c of candidates) {
    try {
      if (await c.count()) { await c.click({ timeout: 5000 }); picked = true; break; }
    } catch (_) { /* next */ }
  }
  await page.waitForTimeout(1500);
  try {
    const save = page.locator('[data-test-id="board-dropdown-save-button"]').first();
    if (await save.count()) { await save.click({ timeout: 5000 }); }
  } catch (e) { log.boardSaveErr = e.message.slice(0, 120); }
  await page.waitForTimeout(1500);
  const after = await page.locator('[data-test-id="board-dropdown-select-button"]').first().innerText().catch(() => '');
  log.boardAfter = (after || '').trim().slice(0, 60);
  return picked;
}

async function markAiDisclosure(page, log) {
  // checkbox[0] = "Пин только для рекламы" (must stay OFF),
  // checkbox[1] = "Отметить как измененный с помощью ИИ" (needs ON),
  // checkbox[2] = "содержит человека, созданного с помощью ИИ" (optional).
  const state = () => page.evaluate(() => Array.from(document.querySelectorAll('input[type="checkbox"]')).map((el) => el.checked));
  try {
    let boxes = await state();
    if (boxes[0]) { // ads-only toggle accidentally on -> click it off
      await page.locator('input[type="checkbox"]').nth(0).click({ timeout: 4000 });
      log.adsOnlyFixed = true;
    }
    boxes = await state();
    if (boxes[1] === false) {
      await page.locator('input[type="checkbox"]').nth(1).click({ timeout: 4000 });
      log.aiCheckboxClicked = true;
    }
    const final = await state();
    log.checkboxState = final;
    const adsOnlyAfter = await page.evaluate(() => Array.from(document.querySelectorAll('input[type="checkbox"]')).map((el) => el.checked)[0]);
    if (adsOnlyAfter) log.adsOnlyStillOn = true;
  } catch (e) { log.aiErr = e.message.slice(0, 100); }
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const token = pinterestToken();
  const plan = [];
  for (const pin of selected) {
    const boardName = pin.board || (pin.payload && pin.payload.board) || 'Travel ideas';
    const boardId = await findBoardId(boardName, token);
    const existing = await boardPins(boardId, token);
    const already = existing.find((p) => (p.link || '').trim() === pin.link);
    plan.push({ pin, boardName, boardId, already });
  }
  const todo = plan.filter((p) => !p.already);
  console.log('PLAN', JSON.stringify(plan.map((p) => ({ id: p.pin.id, board: p.boardName, boardId: p.boardId, already: p.already ? p.already.id : null }))));
  for (const p of plan) if (p.already) console.log(`[exists] ${p.pin.id} -> ${p.already.id} (${p.boardName})`);
  if (!todo.length) { console.log('DONE nothing to publish (all already on boards)'); return; }
  if (DRY) console.log('DRY: would publish', todo.map((p) => p.pin.id));

  const context = await chromium.launchPersistentContext(PROFILE, {
    headless: false, viewport: { width: 1280, height: 900 },
    args: ['--no-sandbox', '--password-store=basic', '--use-mock-keychain'], locale: 'en-US',
  });
  const page = context.pages()[0] || (await context.newPage());
  const results = [];
  try {
    for (const item of todo) {
      const { pin, boardName, boardId } = item;
      const r = { id: pin.id, title: pin.title, board: boardName, publishedPinId: null, error: null };
      try {
        console.log('STEP goto', pin.id);
        await page.goto('https://www.pinterest.com/pin-builder/', { waitUntil: 'domcontentloaded', timeout: 90000 });
        await page.waitForTimeout(8000);
        console.log('STEP upload', pin.id, page.url().slice(0, 80));
        await page.locator('input[type="file"]').first().setInputFiles(path.join(REPO, pin.file), { timeout: 30000 });
        await page.waitForTimeout(9000);
        console.log('STEP uploaded', pin.id);
        await page.locator('textarea[placeholder*="название"]').first().fill(pin.title, { timeout: 10000 });
        await page.locator('textarea[placeholder*="ссылк"]').first().fill(pin.link, { timeout: 10000 });
        r.descFilled = await fillDescription(page, pin.description);
        r.boardPicked = await pickBoard(page, boardName, r);
        await markAiDisclosure(page, r);
        await page.waitForTimeout(1500);
        r.titleValue = await page.locator('textarea[placeholder*="название"]').first().inputValue().catch(() => '');
        r.linkValue = await page.locator('textarea[placeholder*="ссылк"]').first().inputValue().catch(() => '');
        r.boardButtonText = await page.locator('[data-test-id="board-dropdown-select-button"]').first().innerText().catch(() => '');
        await page.screenshot({ path: path.join(OUT, `browser-pin-${pin.id}-before.png`) });
        if (DRY) {
          r.dry = true;
        } else {
          const publish = page.locator('button', { hasText: 'Опубликовать' }).first();
          await publish.click({ timeout: 10000 });
          await page.waitForTimeout(12000);
          r.finalUrl = page.url().slice(0, 120);
          r.finalText = (await page.evaluate(() => document.body.innerText || '')).slice(0, 400);
          await page.screenshot({ path: path.join(OUT, `browser-pin-${pin.id}-after.png`) });
          const pins = await boardPins(boardId, token);
          const found = pins.find((p) => (p.link || '').trim() === pin.link);
          if (found) r.publishedPinId = found.id;
          else r.error = 'not found on board after publish';
        }
      } catch (e) {
        r.error = e.message.slice(0, 300);
        try { await page.screenshot({ path: path.join(OUT, `browser-pin-${pin.id}-error.png`) }); } catch (_) {}
      }
      results.push(r);
      console.log('RESULT', JSON.stringify(r));
    }
  } finally {
    fs.writeFileSync(path.join(OUT, 'browser-publish-run.json'), JSON.stringify(results, null, 2));
    await context.close().catch(() => {});
  }
  const failed = results.filter((r) => !r.publishedPinId && !r.dry);
  if (failed.length) { console.error('FAILED', failed.length, 'pin(s)'); process.exit(1); }
  console.log('DONE published', results.filter((r) => r.publishedPinId).length, 'pin(s)');
})().catch((e) => { console.error('SCRIPT_ERROR', e.message); process.exit(1); });
