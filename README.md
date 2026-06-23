# Covered Call Income Simulator

Applies a covered call options strategy to a single 100-share stock position over historical price data and reports how much net premium income the strategy would have generated, how often contracts were rolled or assigned, and whether the cash reserve was ever stressed.

This is an analytical and calibration tool — not a trading system. Full specification: `docs/covered_call_simulation_requirements_v2.docx`.

## What It Does

The simulator walks through years of daily adjusted closing prices, opening and managing one covered call contract at a time:

- **Opens** each contract with a strike set a configurable percentage out-of-the-money, priced via Black-Scholes using realized 20-day historical volatility.
- **Monitors** daily closes and **rolls** the contract forward when a trigger fires — either price-based (within a configurable % of the strike) or delta-based (Black-Scholes N(d1) reaches a threshold), collecting or paying the difference.
- **Expires** contracts worthless (the ideal outcome) when the stock closes below the strike at expiration.
- **Assigns** shares (and stops the simulation) when the stock closes above the strike at expiration, gaps past the strike intraday, or a debit roll can't be funded from the cash reserve.

Premium income, commissions, and 5% slippage on both legs are tracked throughout.

## Setup

```bash
conda create -n covered-call-sim python=3.11 -y
conda activate covered-call-sim
pip install -r requirements.txt
```

## Usage

```bash
conda activate covered-call-sim
python simulate.py --ticker <TICKER> [options]
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--ticker` | required | Stock ticker symbol, e.g. `AAPL` |
| `--history-years` | 10 | Years of historical data to fetch |
| `--strike-pct-otm` | 5.0 | Strike % above stock price at contract open |
| `--expiration-days` | 30 | Contract term in calendar days |
| `--roll-trigger-pct` | 2.0 | **Price mode:** roll when price is within this % of the strike. Default when neither trigger flag is given. Mutually exclusive with `--roll-trigger-delta`. |
| `--roll-trigger-delta` | — | **Delta mode:** roll when BS delta (N(d1)) reaches this value. Accounts for both price distance and time remaining — fires earlier on long-window contracts, later on short ones. Mutually exclusive with `--roll-trigger-pct`. |
| `--cash-reserve` | 1000.0 | Cash reserve (USD) available to fund debit rolls |
| `--cost-basis` | (first close) | Actual cost basis per share, used for assignment P&L |
| `--no-log` | off | Show summary only; suppress per-contract table |

### Examples

```bash
# Low-volatility baseline, price-based roll trigger (default)
python simulate.py --ticker KO --no-log

# Delta-based roll trigger — fires when delta reaches 0.40
python simulate.py --ticker AAPL --roll-trigger-delta 0.40 --no-log

# Moderate volatility — tests roll behavior in an uptrend
python simulate.py --ticker MSFT --no-log

# Higher volatility — more likely to trigger gap assignment
python simulate.py --ticker AAPL --no-log

# Full per-contract log for one ticker
python simulate.py --ticker AAPL --history-years 10 --strike-pct-otm 5 --expiration-days 30 --roll-trigger-pct 2 --cash-reserve 1000

# Compare all three back-to-back
for t in KO MSFT AAPL; do python simulate.py --ticker $t --no-log; done
```

## Output

### Per-contract log (omit with `--no-log`)

One row per contract showing: contract number, open/close dates, days held, stock price and strike at open, HV20 volatility, BS delta at open (always recorded regardless of trigger mode), theoretical and received premium, close reason, stock price and cost-to-close at close, new premium (if rolled), net P&L, running cash balance, reserve remaining, and an HV20 warning flag.

### Summary report

Always printed after the log:

- **Parameters** — the full parameter set used for the run
- **Period coverage** — simulation start/end dates, total calendar days, and why it ended (data exhausted or assignment)
- **Contract activity** — total contracts, expired worthless, rolled, assigned
- **Income summary** — gross premium, commissions, estimated slippage, net income, annualized yield as a % of position value, average premium per contract, average holding period
- **Risk / stress** — number of debit rolls, largest single debit, lowest cash and reserve balances reached, whether the reserve was fully exhausted, gap assignment events
- **Assignment detail** (if applicable) — date, stock price, strike, cost basis, capital gain/loss, premium income, and combined outcome
