/* Lightweight local scheduler for the Playwright Pinterest fallback.
 * Checks wall-clock every minute and runs one publish attempt per 6 hours.
 * Keep alive with: nohup node growth-funnel/pinterest_scheduler.cjs >> log 2>&1 &
 */
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const PUBLISHER = path.join(__dirname, 'pinterest_playwright_publish.cjs');
const NODE = process.execPath;
const INTERVAL_MS = 6 * 60 * 60 * 1000;
const CHECK_MS = 60 * 1000;
let running = false;
let lastRun = 0;

function stamp() {
  return new Date().toISOString();
}

function runOnce() {
  if (running) {
    console.log(stamp(), 'skip: previous run still active');
    return;
  }
  running = true;
  lastRun = Date.now();
  try { fs.rmSync('/tmp/goodtravel-pinterest.lock', { force: true }); } catch (err) {}
  console.log(stamp(), 'start pinterest publish');
  const child = spawn(NODE, [PUBLISHER], {
    cwd: ROOT,
    env: Object.assign({}, process.env, {
      PLAYWRIGHT_BROWSERS_PATH: '/Users/vd/Documents/deepseek-harness/default-workspace/tools/playwright-mcp/ms-playwright',
    }),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  child.stdout.on('data', function (data) { process.stdout.write(data); });
  child.stderr.on('data', function (data) { process.stderr.write(data); });
  child.on('exit', function (code) {
    running = false;
    console.log(stamp(), 'pinterest publish exit', code);
  });
}

function tick() {
  if (Date.now() - lastRun >= INTERVAL_MS) runOnce();
}

runOnce();
setInterval(tick, CHECK_MS);
console.log(stamp(), 'scheduler started, interval_ms', INTERVAL_MS, 'check_ms', CHECK_MS);
