"""Fetch sample US fares through theYahia/travelpayouts-mcp."""
from __future__ import annotations

import json
import select
import subprocess
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "scripts" / "run_tp_mcp.sh"
OUT = ROOT / "docs" / "flight-hotel-us" / "fares.json"
ROUTES = [("NYC", "MIA"), ("NYC", "LAX"), ("NYC", "CUN"),
          ("NYC", "FCO"), ("NYC", "LHR"), ("LAX", "NRT")]
DEPARTURE = "2026-12-10"


def rpc(proc, obj):
    proc.stdin.write(json.dumps(obj) + "\n")
    proc.stdin.flush()


def read(proc, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        ready, _, _ = select.select([proc.stdout], [], [], 0.5)
        if ready:
            line = proc.stdout.readline()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def main() -> int:
    proc = subprocess.Popen(
        ["/bin/bash", str(MCP)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, bufsize=1,
    )
    rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2024-11-05", "capabilities": {},
        "clientInfo": {"name": "us-fares", "version": "1.0"},
    }})
    read(proc)
    rpc(proc, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
    fares = []
    for idx, (origin, destination) in enumerate(ROUTES, 2):
        rpc(proc, {"jsonrpc": "2.0", "id": idx, "method": "tools/call", "params": {
            "name": "search_flights_prices",
            "arguments": {"origin": origin, "destination": destination,
                          "departure_at": DEPARTURE, "one_way": True, "currency": "usd"},
        }})
        response = read(proc)
        if not response or "result" not in response:
            continue
        text = response["result"]["content"][0]["text"]
        try:
            row = (json.loads(text).get("data") or [{}])[0]
        except (json.JSONDecodeError, IndexError):
            continue
        if not row.get("price"):
            continue
        fares.append({
            "origin": origin, "destination": destination,
            "origin_airport": row.get("origin_airport", ""),
            "destination_airport": row.get("destination_airport", ""),
            "airline": row.get("airline", ""), "price": int(row["price"]),
            "transfers": int(row.get("transfers", 0)),
            "duration_min": int(row.get("duration", 0)),
            "gate": row.get("gate", ""),
        })
        time.sleep(1.5)
    proc.terminate()
    payload = {
        "checked_at": date.today().isoformat(), "source": "theYahia/travelpayouts-mcp",
        "departure_date": DEPARTURE, "currency": "USD", "fares": fares,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"written {OUT} ({len(fares)} fares)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
