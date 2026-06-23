import csv
import sys
from typing import Optional

from .simulation import SimulationResult
from .pricing import COMMISSION, SLIPPAGE, RISK_FREE_RATE


def _fmt(val: float, prefix: str = "$") -> str:
    return f"{prefix}{val:,.2f}"


def print_contract_log(result: SimulationResult, file=sys.stdout) -> None:
    hdr = (
        f"{'#':>4}  {'Open':10}  {'Close':10}  {'Days':>4}  "
        f"{'S@Open':>8}  {'Strike':>7}  {'HV20':>6}  {'Delta':>6}  "
        f"{'Theo':>6}  {'Recv':>6}  {'Reason':<20}  "
        f"{'S@Close':>8}  {'CloseCost':>9}  {'NewPrem':>7}  "
        f"{'NetP&L':>8}  {'Cash':>10}  {'Reserve':>10}  {'HVW':>3}"
    )
    print(hdr, file=file)
    print("-" * len(hdr), file=file)
    for c in result.contracts:
        print(
            f"{c.number:>4}  {c.open_date:10}  {c.close_date:10}  {c.days_held:>4}  "
            f"{c.stock_price_open:>8.2f}  {c.strike:>7.2f}  {c.hv20_at_open:>6.4f}  {c.delta_at_open:>6.4f}  "
            f"{c.theoretical_premium:>6.2f}  {c.premium_received:>6.2f}  {c.close_reason:<20}  "
            f"{c.stock_price_close:>8.2f}  {c.cost_to_close:>9.2f}  {c.new_premium_received:>7.2f}  "
            f"{c.net_contract_pnl:>8.2f}  {c.running_cash:>10.2f}  {c.reserve_remaining:>10.2f}  "
            f"{'Y' if c.hv20_warning else 'N':>3}",
            file=file,
        )


def write_contract_log_csv(result: SimulationResult, path: str) -> None:
    fields = [
        "number", "open_date", "close_date", "days_held",
        "stock_price_open", "strike", "hv20_at_open", "hv20_warning",
        "delta_at_open", "theoretical_premium", "premium_received",
        "close_reason", "stock_price_close", "cost_to_close",
        "new_premium_received", "net_contract_pnl", "running_cash",
        "reserve_remaining", "rolled",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for c in result.contracts:
            writer.writerow({field: getattr(c, field) for field in fields})


def print_summary(
    result: SimulationResult,
    ticker: str,
    history_years: int,
    strike_pct_otm: float,
    expiration_days: int,
    roll_trigger_pct: Optional[float],
    roll_trigger_delta: Optional[float],
    cash_reserve: float,
    file=sys.stdout,
) -> None:
    contracts = result.contracts
    if not contracts:
        print("No contracts executed.", file=file)
        return

    from datetime import date as _date
    start = _date.fromisoformat(result.sim_start)
    end = _date.fromisoformat(result.sim_end or contracts[-1].close_date)
    years_sim = max((end - start).days / 365.25, 0.0001)

    rolled_contracts = [c for c in contracts if c.rolled]
    assigned_contracts = [c for c in contracts
                          if "Assigned" in c.close_reason or "Gap" in c.close_reason or "Forced" in c.close_reason]

    gross_premium = result.total_premium_income
    total_commissions = len(contracts) * COMMISSION + len(rolled_contracts) * COMMISSION
    total_slippage = sum(
        c.theoretical_premium * SLIPPAGE + (
            (c.cost_to_close / (1 + SLIPPAGE) * SLIPPAGE) if c.cost_to_close > 0 else 0
        )
        for c in contracts
    )
    net_income = gross_premium - total_commissions - total_slippage

    avg_stock_price = sum(c.stock_price_open for c in contracts) / len(contracts)
    annualized_yield = (net_income / (avg_stock_price * 100)) / years_sim * 100

    debit_rolls = [c for c in contracts if c.rolled and c.net_contract_pnl < 0]
    largest_debit = max((abs(c.net_contract_pnl) for c in debit_rolls), default=0.0)
    gap_events = [c for c in contracts if c.close_reason == "Gap Assignment"]
    reserve_exhausted = result._min_reserve <= 0

    p = lambda *args, **kwargs: print(*args, file=file, **kwargs)

    p()
    p("=" * 70)
    p("SIMULATION SUMMARY")
    p("=" * 70)

    p("\n--- Parameters ---")
    p(f"  Ticker:            {ticker}")
    p(f"  History:           {history_years} years")
    p(f"  Strike % OTM:      {strike_pct_otm:.1f}%")
    p(f"  Expiration:        {expiration_days} calendar days")
    if roll_trigger_delta is not None:
        p(f"  Roll trigger:      delta >= {roll_trigger_delta:.2f} (delta mode)")
    else:
        p(f"  Roll trigger:      {roll_trigger_pct:.1f}% from strike (price mode)")
    p(f"  Slippage:          {SLIPPAGE * 100:.0f}%")
    p(f"  Commission:        {_fmt(COMMISSION, '$')} per leg")
    p(f"  Risk-free rate:    {RISK_FREE_RATE * 100:.1f}%")
    p(f"  Cash reserve:      {_fmt(cash_reserve)}")

    p("\n--- Period Coverage ---")
    p(f"  Start:             {result.sim_start}")
    p(f"  End:               {result.sim_end}")
    p(f"  Total days:        {(end - start).days}")
    p(f"  End reason:        {result.end_reason}")

    p("\n--- Contract Activity ---")
    expired = [c for c in contracts if c.close_reason == "Expired Worthless"]
    p(f"  Total contracts:   {len(contracts)}")
    p(f"  Expired worthless: {len(expired)}")
    p(f"  Rolled:            {len(rolled_contracts)}")
    p(f"  Assigned:          {len(assigned_contracts)}")

    p("\n--- Income Summary ---")
    p(f"  Gross premium:     {_fmt(gross_premium)}")
    p(f"  Total commissions: {_fmt(total_commissions)}")
    p(f"  Est. slippage:     {_fmt(total_slippage)}")
    p(f"  Net income:        {_fmt(net_income)}")
    p(f"  Annualized yield:  {annualized_yield:.2f}%")
    if contracts:
        avg_prem = gross_premium / len(contracts)
        avg_days = sum(c.days_held for c in contracts) / len(contracts)
        p(f"  Avg premium/contract: {_fmt(avg_prem)}")
        p(f"  Avg holding period:   {avg_days:.1f} days")

    p("\n--- Risk / Stress ---")
    p(f"  Debit rolls:       {len(debit_rolls)}")
    p(f"  Largest debit:     {_fmt(largest_debit)}")
    p(f"  Lowest cash:       {_fmt(result._min_cash)}")
    p(f"  Lowest reserve:    {_fmt(result._min_reserve)}")
    p(f"  Reserve exhausted: {'YES' if reserve_exhausted else 'No'}")
    p(f"  Gap events:        {len(gap_events)}")

    if result.capital_gain_loss is not None:
        p("\n--- Assignment ---")
        p(f"  Date:              {result.assignment_date}")
        p(f"  Stock at assign:   {_fmt(result.assignment_stock_price or 0)}")
        p(f"  Strike:            {_fmt(result.assignment_strike or 0)}")
        p(f"  Cost basis:        {_fmt(result.cost_basis)}")
        p(f"  Capital gain/loss: {_fmt(result.capital_gain_loss)}")
        p(f"  Premium income:    {_fmt(result.total_premium_income)}")
        combined = result.capital_gain_loss + result.total_premium_income
        p(f"  Combined outcome:  {_fmt(combined)}")

    p()
