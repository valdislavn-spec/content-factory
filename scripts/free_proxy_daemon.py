#!/usr/bin/env python3
"""Демон бесплатного SOCKS-прокси: автозапуск + самовосстановление.

Безопасность:
    * слушает только 127.0.0.1 (никакого доступа из LAN);
    * работает от обычного пользователя (не root);
    * НЕ меняет системный прокси — чувствительные сайты (банки) идут напрямую;
    * логи без токенов/паролей, только события соединения/ноды;
    * при 3 подряд неудачных проверках перезапускает Xray и находит новую ноду.

Запускается launchd-агентом com.contentfactory.free-proxy (см.
scripts/install_proxy_schedule.sh).
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT.parent
XRAY_BIN = WORKSPACE / "tools" / "xray" / "xray"
XRAY_CONFIG = WORKSPACE / "tools" / "xray" / "config.json"
LOG_PATH = ROOT / "data" / "logs" / "free_proxy.log"


def log(message: str) -> None:
    line = "{} {}".format(time.strftime("%Y-%m-%d %H:%M:%S"), message)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass
    print(line, flush=True)


def proxy_ok(port: int, timeout: int = 10) -> bool:
    """Проверка, что SOCKS отвечает и x.com доступен."""
    try:
        result = subprocess.run(
            ["curl", "-s", "-x", "socks5h://127.0.0.1:{}".format(port),
             "-m", str(timeout), "-o", "/dev/null", "-w", "%{http_code}", "https://x.com"],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        code = (result.stdout or "").strip()
        return code not in ("", "000")
    except (subprocess.SubprocessError, OSError):
        return False


def ensure_config(port: int) -> bool:
    """Если конфига нет — ищем рабочую ноду (может занять до нескольких минут)."""
    if XRAY_CONFIG.is_file():
        return True
    log("конфига нет — ищу рабочую ноду")
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "free_proxy.py"),
             "--socks-port", str(port), "--max-nodes", "8", "setup"],
            capture_output=True, text=True, timeout=900,
        )
    except subprocess.SubprocessError as exc:
        log("setup не удался: {}".format(exc))
        return False
    for line in (result.stdout or "").strip().splitlines()[-3:]:
        log("setup: " + line)
    return XRAY_CONFIG.is_file()


class Daemon:
    def __init__(self, port: int, check_interval: int, max_failures: int) -> None:
        self.port = port
        self.check_interval = max(60, check_interval)
        self.max_failures = max(1, max_failures)
        self._stop = False

    def request_stop(self, _signum=None, _frame=None) -> None:
        self._stop = True

    def run(self) -> int:
        signal.signal(signal.SIGTERM, self.request_stop)
        signal.signal(signal.SIGINT, self.request_stop)
        log("демон запущен: SOCKS 127.0.0.1:{}".format(self.port))
        while not self._stop:
            if not ensure_config(self.port):
                log("нет конфига, повтор через 60 с")
                time.sleep(60)
                continue
            process = subprocess.Popen(
                [str(XRAY_BIN), "run", "-c", str(XRAY_CONFIG)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            log("Xray запущен pid={}".format(process.pid))
            failures = 0
            while not self._stop and process.poll() is None:
                time.sleep(self.check_interval)
                if proxy_ok(self.port):
                    if failures:
                        log("соединение восстановлено")
                    failures = 0
                    continue
                failures += 1
                log("проверка прокси не прошла ({}/{})".format(failures, self.max_failures))
                if failures >= self.max_failures:
                    log("перезапускаю: ищу новую ноду")
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    XRAY_CONFIG.unlink(missing_ok=True)
                    failures = 0
                    break
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            if not self._stop:
                log("перезапуск через 10 с")
                time.sleep(10)
        log("демон остановлен")
        return 0


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Демон бесплатного SOCKS-прокси")
    parser.add_argument("--socks-port", type=int, default=1080)
    parser.add_argument("--check-interval", type=int, default=120, help="проверка, сек")
    parser.add_argument("--max-failures", type=int, default=3)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    return Daemon(args.socks_port, args.check_interval, args.max_failures).run()


if __name__ == "__main__":
    raise SystemExit(main())
