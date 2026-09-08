import pandas as pd
from typing import Dict


class Backtester:
    def __init__(self, initial_cash: float = 100000.0):
        self.initial_cash = initial_cash

    def run_backtest(self, data: Dict[str, pd.DataFrame], strategy, rebalance_freq: str = 'D') -> pd.DataFrame:
        valid_data = {
            t: df for t, df in data.items() if not df.empty and 'Close' in df.columns
        }
        if not valid_data:
            raise ValueError('No valid price data available for backtest')

        all_idx = pd.Index(sorted(set().union(*(df.index for df in valid_data.values()))))
        prices = {t: df['Close'].reindex(all_idx).ffill() for t, df in valid_data.items()}
        tickers = list(prices.keys())
        signals = {t: strategy.generate_signals(prices[t]) for t in tickers}
        cash = self.initial_cash
        holdings = {t: 0.0 for t in tickers}
        equity_curve = []
        for date in all_idx:
            active = [t for t in tickers if signals[t].get(date, 0) == 1]
            n_active = max(1, len(active))
            target_alloc = 1.0 / n_active
            pv = cash + sum(holdings[t] * prices[t].loc[date] for t in tickers)
            for t in tickers:
                target_value = (target_alloc * pv) if t in active else 0.0
                price = prices[t].loc[date]
                target_shares = 0.0 if price == 0 else target_value / price
                holdings[t] = target_shares
            pv = cash + sum(holdings[t] * prices[t].loc[date] for t in tickers)
            equity_curve.append({'date': date, 'equity': pv})
        eq = pd.DataFrame(equity_curve).set_index('date')
        return eq
