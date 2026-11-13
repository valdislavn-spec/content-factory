# invest-bot — MOEX intraday paper bot

Long-only intraday bot for liquid MOEX shares. Default mode is **paper trading**:
market data comes from the public MOEX ISS API and orders are simulated in SQLite.
No broker token is needed.

## Modes

| MODE | Data | Orders | Requirements |
|---|---|---|---|
| `paper` (default) | MOEX ISS 10-min candles | simulated locally | none |
| `sandbox` | Tinkoff Invest candles | Tinkoff sandbox orders | `TINKOFF_TOKEN` |
| `prod` | Tinkoff Invest candles | real Tinkoff orders | `TINKOFF_TOKEN`, `TINKOFF_ALLOW_LIVE=1` |

`prod` is blocked unless `TINKOFF_ALLOW_LIVE=1` is set explicitly. Start with `sandbox`.

## Strategy

- Universe: `SBER,GAZP,LKOH,YDEX,ROSN,VTBR,TATN,MTSS` (override with `TICKERS`).
- 10-minute candles; EMA(9)/EMA(21) bullish crossover + RSI(14) 45..72.
- Long-only, **max 1 position**, **max 3000 RUB total exposure** and max 3000 RUB per entry.
- Exit: take-profit +2.0%, or profit-taking on an opposite EMA cross.
- **No loss exits by default:** stop-loss is disabled and end-of-day does not sell a losing position; it is held until it turns profitable. Set `ALLOW_LOSS_EXIT=1` to enable stop-loss/loss exits again.
- This is an educational strategy, not investment advice. Holding losers can be riskier than taking a small stop.

## Run locally

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python main.py --once            # print signals/status, no orders
python main.py                   # serve /health on :8000 + run engine
python main.py --once --execute  # paper orders once (for testing)
```

## Env

```
MODE=paper
TICKERS=SBER,GAZP,LKOH,YDEX,ROSN,VTBR,TATN,MTSS
START_EQUITY=100000
RISK_PER_TRADE=0.10
MAX_POSITION_RUB=3000          # cap per entry
MAX_TOTAL_EXPOSURE_RUB=3000    # cap for all open positions
ALLOW_LOSS_EXIT=0              # 0 = never sell at a loss
MAX_POSITIONS=1
DAILY_LOSS_LIMIT=0.02
TAKE_PROFIT=0.02
STOP_LOSS=0.012
POLL_SECONDS=60
PORT=8000
STATE_PATH=/app/data/state.db
STATUS_TOKEN=                      # optional: protect /status and /trades
TINKOFF_TOKEN=                     # sandbox/prod only
TINKOFF_CLASS_CODE=TQBR
TINKOFF_SANDBOX_TOPUP=100000
TINKOFF_ALLOW_LIVE=0
TELEGRAM_BOT_TOKEN=                # optional notifications
TELEGRAM_CHAT_ID=
```

## API

- `GET /health` — liveness (no auth).
- `GET /status` — mode, equity, positions, prices, signals.
- `GET /trades?limit=50` — paper/broker trade log.

If `STATUS_TOKEN` is set, pass `X-Api-Token: ...` or `?token=...`.

## Tests

```bash
python -m pytest -q tests
```

## Deployed

- Northflank service: `invest-bot` (project `default`), public URL:
  `https://http--invest-bot--sm4j47bvw78l.code.run`
- Health: `/health`; status: `/status`; trades: `/trades`.
- Default deployed mode is `paper` with MOEX ISS data. No Tinkoff token is stored in
  the repo or deployed yet.

To enable Tinkoff sandbox: add `TINKOFF_TOKEN` to the Northflank service env
(secret), set `MODE=sandbox`, redeploy/restart. Start with paper results first.
For live `prod`: additionally set `TINKOFF_ALLOW_LIVE=1`; do not do this casually.

## Current deployment status

- Mode: **sandbox** (Tinkoff Invest sandbox, virtual money), max exposure 3000 RUB, no loss exits.
- Tinkoff sandbox account: created and funded with 100 000 RUB.
- Public URL: `https://http--invest-bot--sm4j47bvw78l.code.run`
- `/status` now reports Tinkoff portfolio equity and live Tinkoff 10-min candles.
- The MOEX session is closed at deploy time; trading starts in the next session
  (10:00–17:30 MSK entries, forced close 17:45 MSK).
- Tinkoff endpoint uses certificates from the Russian Trusted Root/Sub CA. They are
  bundled under `certs/` (source: https://github.com/koenrh/russian-trusted-root-ca)
  so Python `requests` can verify the T-Bank chain normally; `TINKOFF_VERIFY_TLS=0`
  exists only as an emergency escape hatch.
- The API token is stored only as a Northflank secret and in the local, git-ignored
  `.local/tinkoff/` directory. Rotate/revoke it after testing.

## Sandbox order test (already performed)

- Opened sandbox account, paid in 100 000 RUB.
- Resolved `SBER` FIGI, fetched last price.
- Sent a market BUY for 1 lot, status `EXECUTION_REPORT_STATUS_FILL`.
- Sent a market SELL to flatten the position; no open SBER position remains.

## ORB strategy (experimental)

`STRATEGY=orb` selects the Opening Range Breakout module. It uses Tinkoff 5-minute
candles in sandbox/prod mode (MOEX 10-minute candles in paper mode), a 15-minute
opening range, VWAP, relative volume, ATR filters and the same 3000 RUB exposure
limits. A signal is evaluated on completed candles only.

Recommended experimental config:

```env
STRATEGY=orb
CANDLE_INTERVAL=CANDLE_INTERVAL_5_MIN
OR_MINUTES=15
ENTRY_CUTOFF=16:30
REL_VOL_MIN=1.4
ATR_PERIOD=14
ATR_MIN_PCT=0.0015
ATR_MAX_PCT=0.015
MAX_TRADES_PER_DAY=2
ALLOW_LOSS_EXIT=1        # required for the ORB stop; 0 = hold losers
STOP_LOSS=0.01
TAKE_PROFIT=0.02
```

Backtest on Tinkoff 5-minute history:

```bash
TINKOFF_TOKEN=... python -m bot.backtest --days 90 --out backtest_results_90d.json
```

The default deployed strategy remains `ema_rsi` until the ORB results are reviewed.
