from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    mode: str = "paper"  # paper | sandbox | prod
    tickers: tuple[str, ...] = ("SBER", "GAZP", "LKOH", "YDEX", "ROSN", "VTBR", "TATN", "MTSS")
    start_equity: float = 100_000.0
    risk_per_trade: float = 0.10
    max_positions: int = 1
    daily_loss_limit: float = 0.02
    take_profit: float = 0.02
    stop_loss: float = 0.012
    fee: float = 0.0005
    poll_seconds: int = 60
    port: int = 8000
    state_path: str = "/tmp/invest-bot/state.db"
    moex_days: int = 7
    status_token: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    tinkoff_token: str = ""
    tinkoff_class_code: str = "TQBR"
    tinkoff_allow_live: bool = False
    tinkoff_sandbox_topup: float = 100_000.0
    tinkoff_verify_tls: bool = True
    max_position_rub: float = 3000.0
    max_total_exposure_rub: float = 3000.0
    allow_loss_exit: bool = False
    strategy: str = "ema_rsi"  # ema_rsi | orb
    candle_interval: str = "CANDLE_INTERVAL_5_MIN"
    or_minutes: int = 15
    entry_cutoff: str = "16:30"
    rel_vol_min: float = 1.4
    rel_vol_lookback: int = 20
    atr_period: int = 14
    atr_min_pct: float = 0.0015
    atr_max_pct: float = 0.015
    breakout_buffer: float = 0.0005
    max_trades_per_day: int = 2
    take_r: float = 2.0

    @property
    def live_broker(self) -> bool:
        return self.mode in {"sandbox", "prod"}

    @classmethod
    def from_env(cls) -> "Config":
        default = cls()
        tickers = tuple(
            t.strip().upper()
            for t in os.getenv("TICKERS", ",".join(default.tickers)).split(",")
            if t.strip()
        )
        return cls(
            mode=os.getenv("MODE", default.mode).strip().lower(),
            tickers=tickers,
            start_equity=float(os.getenv("START_EQUITY", default.start_equity)),
            risk_per_trade=float(os.getenv("RISK_PER_TRADE", default.risk_per_trade)),
            max_positions=int(os.getenv("MAX_POSITIONS", default.max_positions)),
            daily_loss_limit=float(os.getenv("DAILY_LOSS_LIMIT", default.daily_loss_limit)),
            take_profit=float(os.getenv("TAKE_PROFIT", default.take_profit)),
            stop_loss=float(os.getenv("STOP_LOSS", default.stop_loss)),
            fee=float(os.getenv("FEE", default.fee)),
            poll_seconds=int(os.getenv("POLL_SECONDS", default.poll_seconds)),
            port=int(os.getenv("PORT", default.port)),
            state_path=os.getenv("STATE_PATH", default.state_path),
            moex_days=int(os.getenv("MOEX_DAYS", default.moex_days)),
            status_token=os.getenv("STATUS_TOKEN", ""),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            tinkoff_token=os.getenv("TINKOFF_TOKEN", ""),
            tinkoff_class_code=os.getenv("TINKOFF_CLASS_CODE", default.tinkoff_class_code),
            tinkoff_allow_live=_env_bool("TINKOFF_ALLOW_LIVE", False),
            tinkoff_sandbox_topup=float(os.getenv("TINKOFF_SANDBOX_TOPUP", default.tinkoff_sandbox_topup)),
            tinkoff_verify_tls=_env_bool("TINKOFF_VERIFY_TLS", True),
            max_position_rub=float(os.getenv("MAX_POSITION_RUB", default.max_position_rub)),
            max_total_exposure_rub=float(os.getenv("MAX_TOTAL_EXPOSURE_RUB", default.max_total_exposure_rub)),
            allow_loss_exit=_env_bool("ALLOW_LOSS_EXIT", default.allow_loss_exit),
            strategy=os.getenv("STRATEGY", default.strategy).strip().lower(),
            candle_interval=os.getenv("CANDLE_INTERVAL", default.candle_interval),
            or_minutes=int(os.getenv("OR_MINUTES", default.or_minutes)),
            entry_cutoff=os.getenv("ENTRY_CUTOFF", default.entry_cutoff),
            rel_vol_min=float(os.getenv("REL_VOL_MIN", default.rel_vol_min)),
            rel_vol_lookback=int(os.getenv("REL_VOL_LOOKBACK", default.rel_vol_lookback)),
            atr_period=int(os.getenv("ATR_PERIOD", default.atr_period)),
            atr_min_pct=float(os.getenv("ATR_MIN_PCT", default.atr_min_pct)),
            atr_max_pct=float(os.getenv("ATR_MAX_PCT", default.atr_max_pct)),
            breakout_buffer=float(os.getenv("BREAKOUT_BUFFER", default.breakout_buffer)),
            max_trades_per_day=int(os.getenv("MAX_TRADES_PER_DAY", default.max_trades_per_day)),
            take_r=float(os.getenv("TAKE_R", default.take_r)),
        )

    def validate(self) -> None:
        if self.mode not in {"paper", "sandbox", "prod"}:
            raise ValueError(f"unsupported MODE={self.mode!r}; use paper, sandbox or prod")
        if self.mode in {"sandbox", "prod"} and not self.tinkoff_token:
            raise ValueError("TINKOFF_TOKEN is required for sandbox/prod mode")
        if self.mode == "prod" and not self.tinkoff_allow_live:
            raise ValueError("prod mode requires TINKOFF_ALLOW_LIVE=1 (safety guard)")
        if not (0 < self.risk_per_trade <= 1):
            raise ValueError("RISK_PER_TRADE must be in (0, 1]")
        if self.max_position_rub <= 0 or self.max_total_exposure_rub <= 0:
            raise ValueError("position/exposure limits must be positive")
        if self.strategy not in {"ema_rsi", "orb"}:
            raise ValueError("STRATEGY must be ema_rsi or orb")
        if self.strategy == "orb" and not (0 < self.or_minutes <= 60):
            raise ValueError("OR_MINUTES must be in (0, 60]")
