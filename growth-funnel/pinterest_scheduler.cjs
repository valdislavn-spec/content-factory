/* Lightweight local scheduler for the Playwright Pinterest fallback.
 * Runs one publish attempt at startup and then every 6 hours.
 * Keep this process alive with: nohup node growth-funnel/pinterest_scheduler.cjs > growth-funnel/pinterest-scheduler.log 2>&1 &
 */
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const PUBLISHER = path.join(__dirname, 'pinterest_playwright_publish.cjs');
const NODE = process.execPath;
const INTERVAL_MS = 6 * 60 * 60 * 1000;
let running = false;

function stamp() {
  return new Date().toISOString();
}

function runOnce() {
  if (running) {
    console.log(stamp(), 'skip: previous run still active');
    return;
  }
  running = true;
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

runOnce();
setInterval(runOnce, INTERVAL_MS);
console.log(stamp(), 'scheduler started, interval_ms', INTERVAL_MS);
