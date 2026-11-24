"""Start the local Pinterest scheduler in a detached session.

macOS launchctl bootstrap is blocked in some sandboxes, so this launcher uses
start_new_session=True and writes a PID file. It survives the parent shell.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "growth-funnel" / "pinterest-scheduler.log"
NODE = os.environ.get("NODE_BIN") or "/Users/vd/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/node/bin/node"
BROWSERS = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or "/Users/vd/Documents/deepseek-harness/default-workspace/tools/playwright-mcp/ms-playwright"


def main() -> int:
    env = dict(os.environ)
    env["PLAYWRIGHT_BROWSERS_PATH"] = BROWSERS
    with LOG.open("ab", buffering=0) as log:
        process = subprocess.Popen(
            [NODE, "growth-funnel/pinterest_scheduler.cjs"],
            cwd=str(ROOT),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
            close_fds=True,
        )
    (ROOT.parent / "growth-funnel").mkdir(exist_ok=True)
    (ROOT.parent / "growth-funnel" / ".pinterest_scheduler.pid").write_text(str(process.pid))
    print("pinterest scheduler pid", process.pid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
