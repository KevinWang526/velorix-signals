import pandas as pd
from abc import ABC, abstractmethod


class BaseStrategy(ABC):
    @abstractmethod
    def generate_signals(self, price: pd.Series) -> pd.Series:
        """Return a Series of signals indexed like price: 1 for long, 0 for flat."""


class MomentumStrategy(BaseStrategy):
    def __init__(self, short_window: int = 20, long_window: int = 50, momentum_window: int = 3):
        self.short_window = short_window
        self.long_window = long_window
        self.momentum_window = momentum_window

    def generate_signals(self, price: pd.Series) -> pd.Series:
        short_ema = price.ewm(span=self.short_window, adjust=False).mean()
        long_ema = price.ewm(span=self.long_window, adjust=False).mean()
        momentum = price.pct_change(self.momentum_window)
        rising = price > short_ema
        strong_momentum = momentum > 0
        signal = ((short_ema > long_ema) & rising & strong_momentum).astype(int)
        return signal.fillna(0).astype(int)
