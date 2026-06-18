from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

from .data import hv20
from .pricing import (
    black_scholes_call, round_strike, sell_premium, buy_premium,
    COMMISSION, SHARES_PER_CONTRACT,
)

CLOSE_REASONS = {
    "expired": "Expired Worthless",
    "rolled": "Rolled",
    "assigned": "Assigned",
    "gap": "Gap Assignment",
    "forced": "Forced Assignment",
}


@dataclass
class ContractRecord:
    number: int
    open_date: str
    close_date: str
    days_held: int
    stock_price_open: float
    strike: float
    hv20_at_open: float
    hv20_warning: bool
    theoretical_premium: float
    premium_received: float
    close_reason: str
    stock_price_close: float
    cost_to_close: float
    new_premium_received: float
    net_contract_pnl: float
    running_cash: float
    reserve_remaining: float
    rolled: bool


@dataclass
class SimulationResult:
    contracts: list[ContractRecord] = field(default_factory=list)
    end_reason: str = "Data exhausted"
    assignment_date: Optional[str] = None
    assignment_stock_price: Optional[float] = None
    assignment_strike: Optional[float] = None
    cost_basis: float = 0.0
    capital_gain_loss: Optional[float] = None
    total_premium_income: float = 0.0
    sim_start: str = ""
    sim_end: str = ""
    _min_cash: float = 0.0
    _min_reserve: float = 0.0


def _expiry_idx(closes: pd.Series, from_idx: int, expiration_days: int) -> int:
    target = closes.index[from_idx] + pd.Timedelta(days=expiration_days)
    idx = int(closes.index.searchsorted(target))
    if idx >= len(closes):
        return len(closes) - 1
    if closes.index[idx] > target and idx > 0:
        return idx - 1
    return idx


def run(
    closes: pd.Series,
    strike_pct_otm: float,
    expiration_days: int,
    roll_trigger_pct: float,
    cash_reserve: float,
    cost_basis: Optional[float],
    start_idx: int = 0,
) -> SimulationResult:
    result = SimulationResult()
    result.sim_start = closes.index[start_idx].strftime("%Y-%m-%d")
    result._min_reserve = cash_reserve

    if cost_basis is None:
        cost_basis = float(closes.iloc[start_idx])
    result.cost_basis = cost_basis

    cash_balance = 0.0
    reserve = cash_reserve
    min_cash = 0.0
    min_reserve = cash_reserve
    contract_num = 0
    open_idx = start_idx

    def bs_contract(S, K, T, sigma):
        return black_scholes_call(S, K, T, sigma) * SHARES_PER_CONTRACT

    def replenish_reserve(credit: float) -> float:
        nonlocal reserve
        if reserve < cash_reserve and credit > 0:
            add = min(cash_reserve - reserve, credit)
            reserve += add
        return reserve

    while open_idx < len(closes):
        # ── Open contract ──────────────────────────────────────────────
        open_price = float(closes.iloc[open_idx])
        open_date = closes.index[open_idx].strftime("%Y-%m-%d")
        vol, hv_warn = hv20(closes, open_idx)

        strike = round_strike(open_price * (1 + strike_pct_otm / 100))
        T_open = expiration_days / 365
        theo_open = bs_contract(open_price, strike, T_open, vol)
        prem_recv = sell_premium(theo_open)
        net_open = prem_recv - COMMISSION
        cash_balance += net_open
        replenish_reserve(net_open)
        min_cash = min(min_cash, cash_balance)

        exp_idx = _expiry_idx(closes, open_idx, expiration_days)

        # ── Daily monitoring ───────────────────────────────────────────
        close_reason = None
        close_idx = exp_idx
        cost_to_close = 0.0
        new_prem = 0.0

        day_idx = open_idx + 1
        while day_idx <= exp_idx:
            day_price = float(closes.iloc[day_idx])

            # Gap assignment: jumped past strike without hitting roll trigger first
            if day_price > strike:
                roll_thresh = strike * (1 - roll_trigger_pct / 100)
                prev_price = float(closes.iloc[day_idx - 1])
                if prev_price < roll_thresh:
                    close_reason = "gap"
                    close_idx = day_idx
                    break

            # Roll trigger
            roll_thresh = strike * (1 - roll_trigger_pct / 100)
            if day_price >= roll_thresh:
                remaining = (closes.index[exp_idx] - closes.index[day_idx]).days
                T_close = max(remaining / 365, 0.0)
                vol_now, _ = hv20(closes, day_idx)

                theo_close = bs_contract(day_price, strike, T_close, vol_now)
                close_cost = buy_premium(theo_close) + COMMISSION
                cash_balance -= close_cost

                new_strike = round_strike(day_price * (1 + strike_pct_otm / 100))
                theo_new = bs_contract(day_price, new_strike, expiration_days / 365, vol_now)
                new_net = sell_premium(theo_new) - COMMISSION
                cash_balance += new_net

                # Debit roll shortfall
                if cash_balance < 0:
                    if reserve >= -cash_balance:
                        reserve += cash_balance
                        cash_balance = 0.0
                    else:
                        # Can't fund the roll → forced assignment
                        close_reason = "forced"
                        close_idx = day_idx
                        cost_to_close = close_cost
                        # Undo the new contract (it didn't happen)
                        cash_balance -= new_net
                        cash_balance += close_cost
                        break

                replenish_reserve(new_net)
                min_cash = min(min_cash, cash_balance)
                min_reserve = min(min_reserve, reserve)

                # Record the rolled contract and restart from roll date
                days_held = (closes.index[day_idx] - closes.index[open_idx]).days
                net_pnl = net_open - close_cost + new_net
                contract_num += 1
                result.contracts.append(ContractRecord(
                    number=contract_num,
                    open_date=open_date,
                    close_date=closes.index[day_idx].strftime("%Y-%m-%d"),
                    days_held=days_held,
                    stock_price_open=open_price,
                    strike=strike,
                    hv20_at_open=vol,
                    hv20_warning=hv_warn,
                    theoretical_premium=theo_open,
                    premium_received=prem_recv,
                    close_reason=CLOSE_REASONS["rolled"],
                    stock_price_close=day_price,
                    cost_to_close=close_cost,
                    new_premium_received=sell_premium(theo_new),
                    net_contract_pnl=net_pnl,
                    running_cash=cash_balance,
                    reserve_remaining=reserve,
                    rolled=True,
                ))
                result.total_premium_income += prem_recv + sell_premium(theo_new)

                # Restart outer loop from roll date with new contract state
                open_idx = day_idx
                open_price = day_price
                open_date = closes.index[day_idx].strftime("%Y-%m-%d")
                vol = vol_now
                hv_warn = False
                strike = new_strike
                theo_open = theo_new
                prem_recv = sell_premium(theo_new)
                net_open = new_net
                exp_idx = _expiry_idx(closes, day_idx, expiration_days)
                # Continue scanning from next day under new contract
                day_idx += 1
                continue

            day_idx += 1

        # ── End of daily monitoring ────────────────────────────────────
        if close_reason == "forced":
            result.end_reason = CLOSE_REASONS["forced"]
            result.assignment_date = closes.index[close_idx].strftime("%Y-%m-%d")
            result.assignment_stock_price = float(closes.iloc[close_idx])
            result.assignment_strike = strike
            result.capital_gain_loss = (strike - cost_basis) * SHARES_PER_CONTRACT
            days_held = (closes.index[close_idx] - closes.index[open_idx]).days
            contract_num += 1
            result.contracts.append(ContractRecord(
                number=contract_num,
                open_date=open_date,
                close_date=closes.index[close_idx].strftime("%Y-%m-%d"),
                days_held=days_held,
                stock_price_open=open_price,
                strike=strike,
                hv20_at_open=vol,
                hv20_warning=hv_warn,
                theoretical_premium=theo_open,
                premium_received=prem_recv,
                close_reason=CLOSE_REASONS["forced"],
                stock_price_close=float(closes.iloc[close_idx]),
                cost_to_close=cost_to_close,
                new_premium_received=0.0,
                net_contract_pnl=net_open - cost_to_close,
                running_cash=cash_balance,
                reserve_remaining=reserve,
                rolled=False,
            ))
            result.total_premium_income += prem_recv
            result.sim_end = closes.index[close_idx].strftime("%Y-%m-%d")
            break

        if close_reason == "gap":
            result.end_reason = CLOSE_REASONS["gap"]
            result.assignment_date = closes.index[close_idx].strftime("%Y-%m-%d")
            result.assignment_stock_price = float(closes.iloc[close_idx])
            result.assignment_strike = strike
            result.capital_gain_loss = (strike - cost_basis) * SHARES_PER_CONTRACT
            days_held = (closes.index[close_idx] - closes.index[open_idx]).days
            contract_num += 1
            result.contracts.append(ContractRecord(
                number=contract_num,
                open_date=open_date,
                close_date=closes.index[close_idx].strftime("%Y-%m-%d"),
                days_held=days_held,
                stock_price_open=open_price,
                strike=strike,
                hv20_at_open=vol,
                hv20_warning=hv_warn,
                theoretical_premium=theo_open,
                premium_received=prem_recv,
                close_reason=CLOSE_REASONS["gap"],
                stock_price_close=float(closes.iloc[close_idx]),
                cost_to_close=0.0,
                new_premium_received=0.0,
                net_contract_pnl=net_open,
                running_cash=cash_balance,
                reserve_remaining=reserve,
                rolled=False,
            ))
            result.total_premium_income += prem_recv
            result.sim_end = closes.index[close_idx].strftime("%Y-%m-%d")
            break

        # Expiration
        expiry_price = float(closes.iloc[exp_idx])
        if expiry_price >= strike:
            close_reason = "assigned"
            result.end_reason = CLOSE_REASONS["assigned"]
            result.assignment_date = closes.index[exp_idx].strftime("%Y-%m-%d")
            result.assignment_stock_price = expiry_price
            result.assignment_strike = strike
            result.capital_gain_loss = (strike - cost_basis) * SHARES_PER_CONTRACT
        else:
            close_reason = "expired"

        days_held = (closes.index[exp_idx] - closes.index[open_idx]).days
        min_cash = min(min_cash, cash_balance)
        min_reserve = min(min_reserve, reserve)

        contract_num += 1
        result.contracts.append(ContractRecord(
            number=contract_num,
            open_date=open_date,
            close_date=closes.index[exp_idx].strftime("%Y-%m-%d"),
            days_held=days_held,
            stock_price_open=open_price,
            strike=strike,
            hv20_at_open=vol,
            hv20_warning=hv_warn,
            theoretical_premium=theo_open,
            premium_received=prem_recv,
            close_reason=CLOSE_REASONS[close_reason],
            stock_price_close=expiry_price,
            cost_to_close=0.0,
            new_premium_received=0.0,
            net_contract_pnl=net_open,
            running_cash=cash_balance,
            reserve_remaining=reserve,
            rolled=False,
        ))
        result.total_premium_income += prem_recv

        if close_reason == "assigned":
            result.sim_end = closes.index[exp_idx].strftime("%Y-%m-%d")
            break

        open_idx = exp_idx + 1

    result.sim_end = result.sim_end or (
        result.contracts[-1].close_date if result.contracts else result.sim_start
    )
    result._min_cash = min_cash
    result._min_reserve = min_reserve
    return result
