# Backtest report: EMA/RSI vs ORB

Data: Tinkoff Invest 5-minute candles, six MOEX TQBR tickers
(`SBER, GAZP, ROSN, VTBR, TATN, MTSS`), period ending 2026-11-13.
Capital 100 000 RUB, max exposure/position 3 000 RUB, commission 0.05% per
side, additional 0.05% slippage, long-only, max 2 trades/day, entries at the
close of a confirmed 5-minute candle. Taxes and exchange fees are not included.
Results are mark-to-market and include fees.

| Scenario | Period | Trades | Net PnL | Return | PF | Max DD | Win rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| EMA(9/21)+RSI, stop | 90d | 173 | -481.27 | -0.481% | 0.63 | 0.585% | 19.65% |
| ORB 15m, stop at OR low, 2R target | 90d | 104 | -389.53 | -0.390% | 0.671 | 0.534% | 32.69% |
| ORB, no loss exits (hold losers) | 90d | 28 | +497.45 | +0.497% | 55.5 | 0.264% | 96.43% |
| EMA(9/21)+RSI, stop | 180d | 347 | -1 736.19 | -1.736% | 0.416 | 1.778% | 16.71% |
| ORB 15m, stop at OR low, 2R target | 180d | 210 | -868.48 | -0.868% | 0.674 | 1.069% | 31.43% |
| ORB, no loss exits (hold losers) | 180d | 2 | -113.31 | -0.113% | 0.187 | 0.923% | 50.00% |

## Parameter search (90 days)

Opening range 5/10/15/30 minutes, target 1.5R/2R/3R, relative-volume filter
1.4x/2.0x, 1–2 trades/day: every ORB-with-stop variant remained negative after
costs. Best of that grid: -165.58 RUB (OR 30m, 3R), PF 0.799.

## Interpretation

- ORB and EMA/RSI both lose after realistic costs on this sample and size.
- The no-loss ORB result in 90 days is not a real edge: it holds losing
  positions and therefore reports a very high win rate. Over 180 days the first
  losing hold blocked new entries and the strategy made only 2 trades.
- Holding losers has unbounded tail risk; a strict "never sell at a loss" rule
  is incompatible with a robust intraday system.
- 3 000 RUB exposure makes profits tiny relative to fixed costs; a larger
  sample and larger size are needed for a meaningful test.
- The backtest is intentionally simple: entries at candle close, no order book,
  no queue modelling, no intraday margin/leverage, no taxes. Treat it as a
  screening tool, not a promise.

## Conclusion

Do not switch the deployed bot to ORB based on this evidence. ORB remains
available behind `STRATEGY=orb` for further research and demo, but the default
stays `ema_rsi`. Next research candidates: intraday momentum after the first
30 minutes, VWAP mean reversion with regime filter, or order-flow-based entry.
