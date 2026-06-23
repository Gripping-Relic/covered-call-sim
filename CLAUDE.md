# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

This is a **covered call income simulation** tool. It applies a covered call options strategy to a single 100-share stock position over historical price data to answer: how much net premium income would a given parameter set have generated, would shares have been called away (assigned), how often would rolls be required, and was the $1,000 cash reserve ever stressed?

This is an analytical/calibration tool — not a trading system. The full specification is in `docs/covered_call_simulation_requirements_v2.docx`.

## Implementation Stack

- **Language**: Python
- **Data**: `yfinance` for historical daily adjusted closing prices
- **Option pricing**: Black-Scholes (European call as proxy for American-style); use `scipy.stats.norm` for N(d1), N(d2)
- **Output**: Console (tabular per-contract log + summary report)

## Key Parameters and Defaults

| Parameter | Default | Notes |
|---|---|---|
| `ticker` | required | e.g. AAPL, MSFT, KO |
| `history_years` | 10 | Years of historical data to fetch |
| `strike_pct_otm` | 5.0 | % above stock price at contract open |
| `expiration_days` | 30 | Calendar days per contract term |
| `roll_trigger_pct` | 2.0 | Price mode: roll fires when price ≥ strike × (1 − pct/100). Default when neither trigger flag is given. Mutually exclusive with `roll_trigger_delta`. |
| `roll_trigger_delta` | None | Delta mode: roll fires when BS delta (N(d1)) reaches this value. Combines distance-from-strike with time remaining, so it fires earlier on long-window contracts and later on short ones. Mutually exclusive with `roll_trigger_pct`. |
| `cash_reserve` | 1000.00 | USD reserve to fund debit rolls |
| `cost_basis` | None | If omitted, use first adjusted close in dataset |

Internal constants (not exposed as CLI args):
- `SLIPPAGE` = 0.05 (5%): sell at 95% of BS theoretical, buy back at 105%
- `COMMISSION` = $0.65 per contract leg
- `RISK_FREE_RATE` = 0.04 (4%, fixed)
- Strike rounding: nearest $0.50

## Architecture

The simulation is best structured as a pipeline of four concerns:

1. **Data layer** — fetch and validate adjusted closes via yfinance; compute HV20 (annualized std dev of log returns over prior 20 trading days, `× √252`) at each open date.

2. **Pricing engine** — Black-Scholes call pricer given `(S, K, T, r, sigma)`. Apply slippage at call sites: `× 0.95` when selling, `× 1.05` when buying back.

3. **Simulation loop** — iterates over trading days, managing a single contract at a time:
   - **Open**: set strike (rounded to $0.50), compute HV20, BS delta (always recorded), and BS premium; collect net credit; charge commission.
   - **Daily monitor**: check roll trigger. Two mutually exclusive modes:
     - *Price mode* (default): fires when `closing_price ≥ strike × (1 − roll_trigger_pct/100)`.
     - *Delta mode*: fires when BS delta (N(d1)) reaches `roll_trigger_delta`. Delta accounts for both distance-from-strike and time remaining, so the trigger is earlier on long-window contracts and later on short ones.
   - **Roll**: close existing contract (BS value at current date × 1.05 + commission), open new contract same day with fresh strike and full `expiration_days` term.
   - **Expiration**: if roll never triggered and close < strike → expired worthless (ideal); if close ≥ strike → assignment.
   - **Gap assignment**: if any day's close jumps past the strike without triggering the roll threshold first.
   - **Forced assignment**: debit roll required but cash balance + reserve insufficient.
   - **Cash accounting**: running balance starts at $0, separate $1,000 reserve drawn only for debit roll shortfalls; replenish reserve from subsequent net credits before accumulating income.

4. **Reporting** — two outputs:
   - Per-contract log (one row per contract with fields listed in Section 7 of the spec)
   - Summary report (simulation parameters, period coverage, contract activity counts, income totals, annualized yield, risk/stress indicators, assignment detail if applicable)

## Simulation Stop Conditions

- Data exhausted (all historical days consumed)
- Assignment (voluntary, gap, or forced) — simulation ends immediately; shares called away at strike price

## Suggested Test Tickers

- **KO** (Coca-Cola): low volatility baseline, small consistent premiums
- **MSFT** (Microsoft): moderate volatility, tests roll cost behavior under uptrend
- **AAPL** (Apple): higher volatility, tests gap assignment scenario

Running all three with identical parameters reveals how much outcome is driven by stock character vs. parameter choices.

## Commands

```bash
# Create and activate environment
conda create -n covered-call-sim python=3.11 -y
conda activate covered-call-sim
pip install -r requirements.txt

# Run simulation — summary only (price-based roll trigger, default)
python simulate.py --ticker KO --no-log

# Run with delta-based roll trigger
python simulate.py --ticker AAPL --roll-trigger-delta 0.40 --no-log

# Run with full per-contract log
python simulate.py --ticker AAPL --history-years 10 --strike-pct-otm 5 --expiration-days 30 --roll-trigger-pct 2 --cash-reserve 1000

# Compare three tickers with identical parameters
for t in KO MSFT AAPL; do python simulate.py --ticker $t --no-log; done
```

All `--` flags except `--ticker` have defaults (see parameters table above). `--no-log` suppresses the per-contract table and shows only the summary.
