#!/usr/bin/env python3
"""Бесплатный VPN-путь через GitHub: Xray + публичные VLESS/SS-ноды.

Блокировки этой сети: t.me, x.com, instagram, facebook, youtube, WARP API.
Решение: клиент Xray-core (GitHub releases) + бесплатные подписки из GitHub
(freefq-подобные репозитории). Скрипт скачивает список нод, тестирует их через
локальный SOCKS и сохраняет рабочий конфиг. Дальше любой клиент (curl, Chrome)
ходит через `socks5://127.0.0.1:1080` и открывает заблокированные сайты.

Команды:
    python scripts/free_proxy.py setup    # скачать Xray (если нет), найти ноду
    python scripts/free_proxy.py start    # запустить Xray (SOCKS 127.0.0.1:1080)
    python scripts/free_proxy.py test     # проверить доступ к соцсетям
    python scripts/free_proxy.py chrome   # открыть Chrome с Google-профилем через SOCKS

Внимание: публичные ноды — чужие серверы. TLS защищает содержимое, но оператор
ноды видит домены/время. Не вводите банковские пароли; для боевого автопостинга
лучше свой VPN/VPS.
"""
from __future__ import annotations

import argparse
import base64
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from typing import Any, Dict, List, Optional

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKSPACE = ROOT.parent
XRAY_BIN = WORKSPACE / "tools" / "xray" / "xray"
XRAY_CONFIG = WORKSPACE / "tools" / "xray" / "config.json"
XRAY_URL = "https://github.com/XTLS/Xray-core/releases/latest/download/Xray-macos-arm64-v8a.zip"
SUBSCRIPTIONS = (
    "https://raw.githubusercontent.com/ripaojiedian/freenode/main/sub",
    "https://raw.githubusercontent.com/Pawdroid/Free-servers/main/sub",
)
SOCKS_PORT = 1080
TEST_PORT = 1082


def log(message: str) -> None:
    print(message, flush=True)


def ensure_xray() -> bool:
    if XRAY_BIN.is_file():
        return True
    log("скачиваю Xray-core...")
    tmp = pathlib.Path(tempfile.mkdtemp()) / "xray.zip"
    try:
        urllib.request.urlretrieve(XRAY_URL, tmp)
        (XRAY_BIN.parent).mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(tmp) as archive:
            for name in archive.namelist():
                if name.endswith("/xray") or name == "xray":
                    with archive.open(name) as source, open(XRAY_BIN, "wb") as target:
                        shutil.copyfileobj(source, target)
                    XRAY_BIN.chmod(0o755)
                    break
    except Exception as exc:  # noqa: BLE001
        log("не удалось скачать Xray: {}".format(exc))
        return False
    return XRAY_BIN.is_file()


def fetch_links() -> List[str]:
    links: List[str] = []
    for url in SUBSCRIPTIONS:
        try:
            raw = urllib.request.urlopen(url, timeout=30).read().decode("utf-8", "replace").strip()
        except Exception as exc:  # noqa: BLE001
            log("подписка недоступна {}: {}".format(url, exc))
            continue
        found = re.findall(r"(?:vless|ss|vmess)://[^\s\"']+", raw)
        if not found:
            try:
                decoded = base64.b64decode(raw + "==").decode("utf-8", "replace")
                found = re.findall(r"(?:vless|ss|vmess)://[^\s\"']+", decoded)
            except Exception:  # noqa: BLE001
                pass
        links += found
    return list(dict.fromkeys(links))


def parse(link: str) -> Optional[Dict[str, Any]]:
    try:
        if link.startswith("vless://"):
            body = link[8:]
            name = ""
            if "#" in body:
                body, name = body.split("#", 1)
            uuid, _, rest = body.partition("@")
            hostport, _, query = rest.partition("?")
            host, _, port = hostport.rpartition(":")
            params = dict(urllib.parse.parse_qsl(query))
            return {"proto": "vless", "uuid": uuid, "host": host, "port": int(port),
                    "params": params, "name": urllib.parse.unquote(name)}
        if link.startswith("ss://"):
            body = link[5:]
            name = ""
            if "#" in body:
                body, name = body.split("#", 1)
            if "@" in body:
                userinfo, hostport = body.rsplit("@", 1)
                try:
                    decoded = base64.b64decode(userinfo + "==").decode()
                except Exception:  # noqa: BLE001
                    decoded = urllib.parse.unquote(userinfo)
                method, _, password = decoded.partition(":")
                host, _, port = hostport.rpartition(":")
                return {"proto": "ss", "host": host, "port": int(port), "method": method,
                        "password": password, "name": urllib.parse.unquote(name)}
    except Exception:  # noqa: BLE001
        return None
    return None


def outbound(node: Dict[str, Any]) -> Dict[str, Any]:
    if node["proto"] == "vless":
        params = node["params"]
        user = {"id": node["uuid"], "encryption": "none"}
        if params.get("flow"):
            user["flow"] = params["flow"]
        stream: Dict[str, Any] = {"network": params.get("type", "tcp")}
        security = params.get("security", "none")
        if security == "tls":
            stream["security"] = "tls"
            stream["tlsSettings"] = {
                "serverName": params.get("sni") or node["host"],
                "fingerprint": "chrome",
            }
        elif security == "reality":
            stream["security"] = "reality"
            stream["realitySettings"] = {
                "serverName": params.get("sni", ""),
                "fingerprint": params.get("fp", "chrome"),
                "publicKey": params.get("pbk", ""),
                "shortId": params.get("sid", ""),
            }
        transport = params.get("type", "tcp")
        if transport == "ws":
            stream["wsSettings"] = {
                "path": params.get("path", "/") or "/",
                "headers": {"Host": params.get("host") or params.get("sni") or ""},
            }
        elif transport == "grpc":
            stream["grpcSettings"] = {"serviceName": params.get("serviceName", "")}
        return {"protocol": "vless",
                "settings": {"vnext": [{"address": node["host"], "port": node["port"], "users": [user]}]},
                "streamSettings": stream}
    if node["proto"] == "ss":
        return {"protocol": "shadowsocks",
                "settings": {"servers": [{"address": node["host"], "port": node["port"],
                                          "method": node["method"], "password": node["password"]}]}}
    raise ValueError("неизвестный протокол")


def build_config(node: Dict[str, Any], socks_port: int) -> Dict[str, Any]:
    return {
        "log": {"loglevel": "error"},
        "inbounds": [{"listen": "127.0.0.1", "port": socks_port, "protocol": "socks",
                      "settings": {"udp": False}}],
        "outbounds": [outbound(node)],
    }


def curl(url: str, socks_port: int, timeout: int = 5) -> str:
    result = subprocess.run(
        ["curl", "-s", "-x", "socks5h://127.0.0.1:{}".format(socks_port),
         "-m", str(timeout), "-o", "/dev/null", "-w", "%{http_code}", url],
        capture_output=True, text=True,
    )
    return (result.stdout or "").strip() or "000"


def candidate_nodes(max_nodes: int) -> List[Dict[str, Any]]:
    nodes = [parse(link) for link in fetch_links()]
    parsed = [n for n in nodes if n]
    def priority(node: Dict[str, Any]) -> int:
        params = node.get("params") or {}
        score = 0
        if node["proto"] == "vless" and params.get("security") == "tls" and params.get("type") == "ws":
            score += 20
        if node["port"] == 443:
            score += 10
        if node["proto"] == "vless" and params.get("security") == "reality":
            score += 5
        return -score
    parsed.sort(key=priority)
    return parsed[:max_nodes]


def command_setup(args: argparse.Namespace) -> int:
    if not ensure_xray():
        return 1
    nodes = candidate_nodes(args.max_nodes)
    if not nodes:
        log("не удалось получить список нод")
        return 1
    log("проверяю {} нод...".format(len(nodes)))
    best = None
    for index, node in enumerate(nodes):
        config = build_config(node, TEST_PORT)
        path = pathlib.Path(tempfile.mktemp(suffix=".json"))
        path.write_text(json.dumps(config), encoding="utf-8")
        process = subprocess.Popen(
            [str(XRAY_BIN), "run", "-c", str(path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        try:
            time.sleep(1.0)
            if process.poll() is not None:
                continue
            x_code = curl("https://x.com", TEST_PORT)
            t_code = curl("https://t.me", TEST_PORT)
            log("[{}] {}:{} x={} t={}".format(index, node["host"], node["port"], x_code, t_code))
            if x_code not in ("000", "") and t_code not in ("000", ""):
                best = node
                break
        finally:
            process.terminate()
            try:
                process.wait(timeout=2)
            except Exception:  # noqa: BLE001
                process.kill()
            path.unlink(missing_ok=True)
    if best is None:
        log("рабочих нод не найдено — попробуйте позже (списки обновляются)")
        return 1
    XRAY_CONFIG.write_text(
        json.dumps(build_config(best, args.socks_port), ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    log("рабочая нода: {} {}:{}".format(best["proto"], best["host"], best["port"]))
    log("конфиг: {}".format(XRAY_CONFIG))
    return 0


def command_start(args: argparse.Namespace) -> int:
    if not XRAY_CONFIG.is_file():
        log("нет конфига, сначала: python scripts/free_proxy.py setup")
        return 1
    log("SOCKS5 на 127.0.0.1:{}; Ctrl+C для остановки".format(args.socks_port))
    return subprocess.call([str(XRAY_BIN), "run", "-c", str(XRAY_CONFIG)])


def command_test(_args: argparse.Namespace) -> int:
    targets = ["https://x.com", "https://www.instagram.com", "https://www.facebook.com",
               "https://www.youtube.com", "https://t.me", "https://www.reddit.com"]
    ok = 0
    for url in targets:
        code = curl(url, SOCKS_PORT, timeout=15)
        log("{}  {}".format(code, url))
        ok += 1 if code not in ("000", "") else 0
    log("доступно: {}/{}".format(ok, len(targets)))
    return 0 if ok else 1


def command_chrome(args: argparse.Namespace) -> int:
    chrome = WORKSPACE / "tools/playwright-mcp/ms-playwright/chromium-1252/chrome-mac-arm64" \
        / "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
    profile = pathlib.Path("/tmp/chrome-vpn")
    if not profile.is_dir():
        source = WORKSPACE / ".local" / "chrome-google"
        if source.is_dir():
            shutil.copytree(source, profile)
        else:
            profile.mkdir(parents=True, exist_ok=True)
    for lock in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        (profile / lock).unlink(missing_ok=True)
    command = [
        str(chrome),
        "--user-data-dir={}".format(profile),
        "--proxy-server=socks5://127.0.0.1:{}".format(args.socks_port),
        "--remote-debugging-port=9350", "--no-first-run", "--no-default-browser-check",
        "--no-sandbox", "--disable-breakpad", "--disable-crash-reporter",
        "--disable-extensions", "--disable-quic", "--window-size=1440,900",
        "https://x.com", "https://www.instagram.com", "https://www.facebook.com",
        "https://www.youtube.com", "https://www.tiktok.com", "https://www.reddit.com",
    ]
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log("Chrome запущен через SOCKS; вкладки соцсетей открыты")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Бесплатный VPN через Xray + GitHub-ноды")
    parser.add_argument("--socks-port", type=int, default=SOCKS_PORT)
    parser.add_argument("--max-nodes", type=int, default=10)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="скачать Xray и найти рабочую ноду")
    sub.add_parser("start", help="запустить SOCKS-прокси")
    sub.add_parser("test", help="проверить доступ к соцсетям")
    sub.add_parser("chrome", help="открыть Chrome через SOCKS")
    args = parser.parse_args(argv)
    commands = {"setup": command_setup, "start": command_start,
                "test": command_test, "chrome": command_chrome}
    return commands[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
