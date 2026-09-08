import numpy as np
import pandas as pd
from datetime import datetime


def generate_sample_data(ticker: str, start: str, end: str) -> pd.DataFrame:
    dates = pd.bdate_range(start=start, end=end)
    np.random.seed(abs(hash(ticker)) % (2**32))
    returns = np.random.normal(loc=0.0005, scale=0.02, size=len(dates))
    price = 100 * np.exp(np.cumsum(returns))
    df = pd.DataFrame({
        'Open': price * (1 - 0.002),
        'High': price * (1 + 0.003),
        'Low': price * (1 - 0.003),
        'Close': price,
        'Volume': np.random.randint(100000, 500000, size=len(dates)),
    }, index=dates)
    return df
