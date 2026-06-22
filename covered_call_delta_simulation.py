import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

def black_scholes_call(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        return max(S - K, 0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    call_price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return max(call_price, 0)

def calculate_hv20(prices):
    if len(prices) < 2:
        return 0.25
    log_returns = np.log(prices / prices.shift(1)).dropna()
    if len(log_returns) < 2:
        return 0.25
    hv = log_returns.std() * np.sqrt(252)
    return hv

class CoveredCallSimulator:
    def __init__(self, ticker, history_years=10, strike_pct_otm=5.0, expiration_days=30,
                 roll_trigger_pct=2.0, cash_reserve=1000.0, cost_basis=None):
        self.ticker = ticker.upper()
        self.history_years = history_years
        self.strike_pct_otm = strike_pct_otm / 100.0
        self.expiration_days = expiration_days
        self.roll_trigger_pct = roll_trigger_pct / 100.0
        self.cash_reserve = cash_reserve
        self.cost_basis = cost_basis
        self.commission = 0.65
        self.slippage_open = 0.95
        self.slippage_close = 1.05
        self.r = 0.04

    def run(self, prices=None):
        """prices should be a pandas Series with datetime index of Adj Close prices"""
        if prices is None:
            print("No price data provided. Using synthetic data for demo.")
            # Generate synthetic price data for testing
            dates = pd.date_range(start='2016-01-01', periods=2000, freq='B')
            np.random.seed(42)
            prices = pd.Series(100 * np.exp(np.cumsum(np.random.normal(0.0005, 0.015, len(dates)))), index=dates, name='Adj Close')
        
        if len(prices) < self.expiration_days:
            raise ValueError("Not enough historical data")

        if self.cost_basis is None:
            self.cost_basis = prices.iloc[0]

        contracts = []
        cash_balance = 0.0
        reserve = self.cash_reserve
        current_date = prices.index[0]
        contract_num = 1
        assignment = None

        print(f"Starting simulation for {self.ticker} with {len(prices)} days of data.")

        i = 0
        while i < len(prices) - self.expiration_days:
            current_date = prices.index[i]
            S = prices.iloc[i]
            hv = calculate_hv20(prices.iloc[max(0, i-30):i+1])
            K = round(S * (1 + self.strike_pct_otm) / 0.5) * 0.5
            
            days_to_exp = self.expiration_days
            T = days_to_exp / 365.0
            theoretical = black_scholes_call(S, K, T, self.r, hv)
            premium_received = theoretical * self.slippage_open - self.commission
            
            cash_balance += premium_received
            
            contract = {
                'contract_num': contract_num,
                'open_date': current_date.date(),
                'stock_open': round(S, 2),
                'strike': K,
                'hv20': round(hv, 4),
                'theoretical_premium': round(theoretical, 2),
                'premium_received': round(premium_received, 2),
                'days_held': None,
                'close_date': None,
                'close_reason': None,
                'stock_close': None,
                'cost_to_close': None,
                'net_pnl': round(premium_received, 2),
            }
            
            rolled = False
            for j in range(1, days_to_exp + 1):
                if i + j >= len(prices):
                    break
                day_idx = i + j
                day = prices.index[day_idx]
                close_price = prices.iloc[day_idx]
                
                trigger_level = K * (1 - self.roll_trigger_pct)
                if close_price >= trigger_level:
                    remaining_days = days_to_exp - j
                    if remaining_days < 1:
                        remaining_days = 1
                    T_close = remaining_days / 365.0
                    hv_close = calculate_hv20(prices.iloc[max(0, day_idx-30):day_idx+1])
                    theoretical_close = black_scholes_call(close_price, K, T_close, self.r, hv_close)
                    close_cost = theoretical_close * self.slippage_close + self.commission
                    
                    cash_balance -= close_cost
                    
                    # New contract
                    new_S = close_price
                    new_K = round(new_S * (1 + self.strike_pct_otm) / 0.5) * 0.5
                    new_T = self.expiration_days / 365.0
                    new_hv = calculate_hv20(prices.iloc[max(0, day_idx-30):day_idx+1])
                    new_theoretical = black_scholes_call(new_S, new_K, new_T, self.r, new_hv)
                    new_premium = new_theoretical * self.slippage_open - self.commission
                    
                    cash_balance += new_premium
                    
                    contract['close_date'] = day.date()
                    contract['close_reason'] = 'Rolled'
                    contract['stock_close'] = round(close_price, 2)
                    contract['cost_to_close'] = round(close_cost, 2)
                    contract['net_pnl'] = round(premium_received - close_cost + new_premium, 2)
                    
                    i = day_idx
                    rolled = True
                    break
                
                if close_price >= K:
                    contract['close_date'] = day.date()
                    contract['close_reason'] = 'Gap Assignment'
                    contract['stock_close'] = round(close_price, 2)
                    assignment = {'date': day.date(), 'price': close_price, 'strike': K, 'gain_loss': (K - self.cost_basis) * 100}
                    rolled = True
                    break
            
            if not rolled:
                exp_idx = min(i + days_to_exp, len(prices)-1)
                exp_day = prices.index[exp_idx]
                final_price = prices.iloc[exp_idx]
                if final_price >= K:
                    contract['close_reason'] = 'Assigned at Expiration'
                    assignment = {'date': exp_day.date(), 'price': final_price, 'strike': K, 'gain_loss': (K - self.cost_basis) * 100}
                else:
                    contract['close_reason'] = 'Expired Worthless'
                contract['close_date'] = exp_day.date()
                contract['stock_close'] = round(final_price, 2)
                i = exp_idx
            
            contracts.append(contract)
            contract_num += 1
            if assignment:
                break

        df = pd.DataFrame(contracts)
        total_net = df['net_pnl'].sum() if not df.empty else 0
        
        print("\n=== SIMULATION SUMMARY ===")
        print(f"Ticker: {self.ticker}")
        print(f"Contracts: {len(contracts)}")
        print(f"Total Net Premium Income: ${total_net:,.2f}")
        print(f"Final Cash Balance: ${cash_balance:,.2f}")
        if assignment:
            print(f"Assignment on {assignment['date']} at ${assignment['price']:.2f}")
        print("\nLast 5 contracts:")
        print(df.tail().to_string(index=False))
        
        return df

# Run demo with synthetic data
if __name__ == "__main__":
    sim = CoveredCallSimulator("AAPL", history_years=5, strike_pct_otm=7.0, expiration_days=30, roll_trigger_pct=2.0)
    sim.run()