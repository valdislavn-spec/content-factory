from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

MSK = timezone(timedelta(hours=3))
DEFAULT_URL = "https://http--invest-bot--sm4j47bvw78l.code.run/status"


def fetch_status(url: str = DEFAULT_URL, timeout: int = 30) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = json.load(response)
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("status endpoint returned no data object")
    return data


def _key(data: dict[str, Any]) -> tuple:
    return (
        data.get("equity"),
        data.get("day_pnl"),
        data.get("trades_today"),
        data.get("last_tick"),
        json.dumps(data.get("positions") or [], sort_keys=True),
    )


def append_snapshot(
    automation_dir: str | Path,
    data: dict[str, Any],
    fetched_at: datetime | None = None,
    dedupe: bool = True,
) -> tuple[Path, bool]:
    fetched_at = fetched_at or datetime.now(timezone.utc)
    fetched_at = fetched_at.astimezone(timezone.utc)
    path = Path(automation_dir) / f"status-{fetched_at.strftime('%Y-%m')}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    if dedupe and path.exists():
        lines = path.read_text(encoding="utf-8").strip().splitlines()[-1:]
        if lines:
            try:
                previous = json.loads(lines[0]).get("status") or {}
                if _key(previous) == _key(data):
                    return path, False
            except (ValueError, TypeError):
                pass
    row = {"fetched_at": fetched_at.isoformat(), "status": data}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path, True


def iter_snapshots(automation_dir: str | Path) -> Iterable[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(Path(automation_dir).glob("status-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and isinstance(row.get("status"), dict):
                rows.append(row)
    rows.sort(key=lambda row: str(row.get("fetched_at", "")))
    return rows


def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def daily_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_day: dict[str, dict[str, Any]] = {}
    for row in rows:
        ts = _parse_ts(row.get("fetched_at", ""))
        if not ts:
            continue
        day = ts.astimezone(MSK).date().isoformat()
        by_day[day] = row
    return [by_day[day] for day in sorted(by_day)]


def build_report(
    rows: Iterable[dict[str, Any]], start_equity: float | None = None
) -> str:
    snapshots = list(rows)
    daily = daily_rows(snapshots)
    if not daily:
        return "# invest-bot monitoring\n\nПока нет снимков `/status`.\n"

    statuses = [row.get("status") or {} for row in daily]
    latest_ts = _parse_ts(daily[-1].get("fetched_at", ""))
    updated = latest_ts.astimezone(MSK).strftime("%Y-%m-%d %H:%M MSK") if latest_ts else "—"
    first = statuses[0]
    start = float(start_equity or first.get("start_equity") or first.get("equity") or 0.0)
    previous = start
    lines = [
        "# invest-bot: 30-дневный мониторинг",
        "",
        f"Обновлено: {updated}",
        "",
        "> Это sandbox-бот на MOEX. Не инвестиционная рекомендация и не доказательство доходности.",
        "",
        "| Дата (MSK) | Equity, ₽ | P&L за день, ₽ | Накопленный P&L, ₽ | Позиции | Сделок за день | Ошибка |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    peak = start
    max_dd = 0.0
    total_trades = 0
    errors = 0
    for row, status in zip(daily, statuses):
        equity = float(status.get("equity") or 0.0)
        day_pnl = equity - previous
        cum_pnl = equity - start
        positions = len(status.get("positions") or [])
        trades_today = int((status.get("risk") or {}).get("trades_today") or 0)
        error = str(status.get("last_error") or "").replace("|", "/").replace("\n", " ").strip()
        total_trades += trades_today
        errors += 1 if error else 0
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)
        day = _parse_ts(row.get("fetched_at", ""))
        day_label = day.astimezone(MSK).date().isoformat() if day else "—"
        lines.append(
            f"| {day_label} | {equity:,.2f} | {day_pnl:+,.2f} | {cum_pnl:+,.2f} | "
            f"{positions} | {trades_today} | {error or '—'} |"
        )
        previous = equity

    end = float(statuses[-1].get("equity") or 0.0)
    total_return = (end - start) / start * 100.0 if start else 0.0
    lines += [
        "",
        "## Итог",
        "",
        f"- Наблюдений (дней): **{len(daily)}**",
        f"- Equity: **{start:,.2f} → {end:,.2f} ₽**",
        f"- Доходность: **{total_return:+.3f}%**",
        f"- Максимальная просадка: **{max_dd:.3f}%**",
        f"- Сделок за день (сумма последних снимков): **{total_trades}**",
        f"- Снимков с ошибкой: **{errors}**",
        f"- Режим: **{statuses[-1].get('mode', '—')}**",
        "",
        "## Как читать",
        "",
        "- Сделки и P&L считаются по последнему снимку каждого дня; пропуски не интерполируются.",
        "- Sandbox не доказывает прибыльность: это проверка инфраструктуры и дисциплины.",
        "- Для решения о prod нужно минимум 30 торговых дней без сбоев и положительный P&L после комиссий.",
    ]
    return "\n".join(lines) + "\n"


def write_report(automation_dir: str | Path, out_path: str | Path) -> Path:
    text = build_report(iter_snapshots(automation_dir))
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Archive invest-bot /status and build a daily report")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--automation-dir", default="data/automation")
    parser.add_argument("--out", default="MONITORING.md")
    parser.add_argument("--once", action="store_true", help="fetch one status snapshot")
    parser.add_argument("--append", action="store_true", help="append snapshot to JSONL")
    parser.add_argument(
        "--report",
        nargs="?",
        const="MONITORING.md",
        default="",
        help="rebuild the report (optionally pass the output path)",
    )
    parser.add_argument("--no-dedupe", action="store_true")
    args = parser.parse_args(argv)

    do_fetch = args.once or args.append or not args.report
    if do_fetch:
        data = fetch_status(args.url)
        path, appended = append_snapshot(args.automation_dir, data, dedupe=not args.no_dedupe)
        print(("appended " if appended else "unchanged ") + str(path))
    if args.report or do_fetch:
        report_path = args.report or args.out
        out = write_report(args.automation_dir, report_path)
        print("report " + str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
