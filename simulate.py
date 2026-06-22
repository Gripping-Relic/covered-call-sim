#!/usr/bin/env python3
"""
Covered Call Income Simulation — Version 2
===========================================
Simulates a covered call options strategy applied to a single 100-share stock
position over historical daily closing prices.  The simulation is an analytical
calibration tool, not a trading system.

Version 1 introduced the core price-based roll trigger: a contract is rolled
when the stock price rises within a configurable percentage of the strike.

Version 2 adds an alternative delta-based roll trigger (--roll-trigger-delta).
Delta is the Black-Scholes N(d1) sensitivity, which combines distance-from-strike
with time remaining.  At the same price-to-strike distance, delta is higher with
more days left (higher assignment risk) and lower with fewer days left (lower risk).
This lets the trigger fire earlier in long-window contracts and later in
short-window contracts, compared to a fixed percentage threshold.

The two trigger modes are mutually exclusive.  The original price-based trigger
(--roll-trigger-pct, default 2.0) remains the default when neither flag is given.

Full specification: docs/covered_call_simulation_requirements_v2.docx
"""
import argparse
import sys

from src.data import fetch_prices
from src.simulation import run
from src.reporting import print_contract_log, print_summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Covered call income simulation over historical price data."
    )
    parser.add_argument("--ticker", required=True,
                        help="Stock ticker symbol, e.g. AAPL")
    parser.add_argument("--history-years", type=int, default=10,
                        help="Years of historical data (default: 10)")
    parser.add_argument("--strike-pct-otm", type=float, default=5.0,
                        help="Strike %% above stock price at open (default: 5.0)")
    parser.add_argument("--expiration-days", type=int, default=30,
                        help="Contract term in calendar days (default: 30)")
    parser.add_argument("--roll-trigger-pct", type=float, default=None,
                        help="Roll when price is within this %% of strike (default: 2.0, price mode). "
                             "Mutually exclusive with --roll-trigger-delta.")
    parser.add_argument("--roll-trigger-delta", type=float, default=None,
                        help="Roll when BS delta reaches this value (delta mode). "
                             "Mutually exclusive with --roll-trigger-pct.")
    parser.add_argument("--cash-reserve", type=float, default=1000.0,
                        help="Starting cash reserve for debit rolls (default: 1000)")
    parser.add_argument("--cost-basis", type=float, default=None,
                        help="Actual cost basis per share (optional)")
    parser.add_argument("--no-log", action="store_true",
                        help="Skip per-contract log, show summary only")
    args = parser.parse_args()

    if args.roll_trigger_pct is not None and args.roll_trigger_delta is not None:
        print(
            "Error: --roll-trigger-pct and --roll-trigger-delta are mutually exclusive. "
            "Supply one or the other, not both.",
            file=sys.stderr,
        )
        sys.exit(1)

    roll_trigger_delta = args.roll_trigger_delta
    if roll_trigger_delta is not None:
        roll_trigger_pct = None
    else:
        roll_trigger_pct = args.roll_trigger_pct if args.roll_trigger_pct is not None else 2.0

    try:
        closes, sim_start_idx = fetch_prices(args.ticker, args.history_years, args.expiration_days)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    result = run(
        closes=closes,
        strike_pct_otm=args.strike_pct_otm,
        expiration_days=args.expiration_days,
        roll_trigger_pct=roll_trigger_pct,
        roll_trigger_delta=roll_trigger_delta,
        cash_reserve=args.cash_reserve,
        cost_basis=args.cost_basis,
        start_idx=sim_start_idx,
    )

    if not args.no_log:
        print_contract_log(result)

    print_summary(
        result,
        ticker=args.ticker,
        history_years=args.history_years,
        strike_pct_otm=args.strike_pct_otm,
        expiration_days=args.expiration_days,
        roll_trigger_pct=roll_trigger_pct,
        roll_trigger_delta=roll_trigger_delta,
        cash_reserve=args.cash_reserve,
    )


if __name__ == "__main__":
    main()
