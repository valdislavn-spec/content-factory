from __future__ import annotations

import argparse
import json
import logging
import signal
import sys

from bot.config import Config
from bot.engine import Engine
from bot.server import start_server


def main() -> int:
    parser = argparse.ArgumentParser(description="MOEX intraday bot (paper / Tinkoff sandbox)")
    parser.add_argument("--once", action="store_true", help="evaluate signals once and exit")
    parser.add_argument("--execute", action="store_true", help="with --once: execute paper orders")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = Config.from_env()
    cfg.validate()
    engine = Engine(cfg)

    if args.once:
        print(json.dumps(engine.run_once(execute=args.execute), ensure_ascii=False, indent=2, default=str))
        return 0

    server = start_server(engine, cfg.port, cfg.status_token)
    def _stop(signum, frame):
        logging.getLogger("main").info("signal %s: stopping", signum)
        engine.stop()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    try:
        engine.run_forever()
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
