import math
from scipy.stats import norm

RISK_FREE_RATE = 0.04
SLIPPAGE = 0.05
COMMISSION = 0.65
SHARES_PER_CONTRACT = 100


def black_scholes_call(S: float, K: float, T: float, sigma: float, r: float = RISK_FREE_RATE) -> float:
    """Theoretical Black-Scholes European call price. Returns 0 if T <= 0 or sigma <= 0."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return max(0.0, S - K)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return float(S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2))


def round_strike(price: float) -> float:
    return round(price * 2) / 2


def sell_premium(theoretical: float) -> float:
    return theoretical * (1 - SLIPPAGE)


def buy_premium(theoretical: float) -> float:
    return theoretical * (1 + SLIPPAGE)
