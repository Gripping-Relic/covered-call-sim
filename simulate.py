#!/usr/bin/env python3
import argparse
import sys

from src.data import fetch_prices
from src.simulation import run
from src.reporting import print_contract_log, print_summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Covered call income simulation over historical price data."
    )
    parser.add_argument("--ticker", required=True, help="Stock ticker symbol, e.g. AAPL")
    parser.add_argument("--history-years", type=int, default=10,
                        help="Years of historical data (default: 10)")
    parser.add_argument("--strike-pct-otm", type=float, default=5.0,
                        help="Strike %% above stock price at open (default: 5.0)")
    parser.add_argument("--expiration-days", type=int, default=30,
                        help="Contract term in calendar days (default: 30)")
    parser.add_argument("--roll-trigger-pct", type=float, default=2.0,
                        help="Roll when price is within this %% of strike (default: 2.0)")
    parser.add_argument("--cash-reserve", type=float, default=1000.0,
                        help="Starting cash reserve for debit rolls (default: 1000)")
    parser.add_argument("--cost-basis", type=float, default=None,
                        help="Actual cost basis per share (optional)")
    parser.add_argument("--no-log", action="store_true",
                        help="Skip per-contract log, show summary only")
    args = parser.parse_args()

    try:
        closes, sim_start_idx = fetch_prices(args.ticker, args.history_years, args.expiration_days)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    result = run(
        closes=closes,
        strike_pct_otm=args.strike_pct_otm,
        expiration_days=args.expiration_days,
        roll_trigger_pct=args.roll_trigger_pct,
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
        roll_trigger_pct=args.roll_trigger_pct,
        cash_reserve=args.cash_reserve,
    )


if __name__ == "__main__":
    main()
