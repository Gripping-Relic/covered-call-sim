import numpy as np
import pandas as pd
import yfinance as yf
from datetime import date, timedelta

HV_WARMUP_DAYS = 45  # calendar days prepended before sim window (~30 trading days)


def fetch_prices(ticker: str, history_years: int, expiration_days: int) -> tuple[pd.Series, int]:
    """Return (full_closes, sim_start_idx) where sim_start_idx is the first day
    of the requested history_years window. The series includes HV_WARMUP_DAYS of
    prior data so HV20 is meaningful from the first simulation day."""
    end = date.today()
    sim_start = end - timedelta(days=int(history_years * 365.25))
    fetch_start = sim_start - timedelta(days=HV_WARMUP_DAYS)

    raw = yf.download(ticker, start=fetch_start.isoformat(), end=end.isoformat(),
                      auto_adjust=True, progress=False)
    if raw.empty:
        raise ValueError(f"No price data returned for {ticker}")
    closes = raw["Close"].squeeze().dropna()

    sim_start_idx = int(closes.index.searchsorted(pd.Timestamp(sim_start)))
    sim_days = len(closes) - sim_start_idx
    if sim_days < expiration_days:
        raise ValueError(
            f"Insufficient data: need at least {expiration_days} trading days "
            f"in the {history_years}-year window, got {sim_days}"
        )
    return closes, sim_start_idx


def hv20(closes: pd.Series, as_of_idx: int) -> tuple[float, bool]:
    """Return (annualized HV, hv_warning) using up to 20 prior log-returns."""
    start = max(0, as_of_idx - 20)
    window = closes.iloc[start : as_of_idx + 1]
    if len(window) < 2:
        return 0.0, True
    log_returns = np.log(window.values[1:] / window.values[:-1])
    warned = len(log_returns) < 20
    vol = float(np.std(log_returns, ddof=1) * np.sqrt(252))
    return vol, warned
