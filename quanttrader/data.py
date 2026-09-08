import time
from typing import List, Dict


def fetch_data(tickers: List[str], start: str, end: str, interval: str = "1d") -> Dict[str, 'pd.DataFrame']:
    import pandas as pd
    import yfinance as yf
    import pandas_datareader.data as web

    data: Dict[str, pd.DataFrame] = {}
    if not tickers:
        return data

    for ticker in tickers:
        df = pd.DataFrame()
        # Try pandas-datareader first for daily Yahoo data
        try:
            df = web.DataReader(ticker, 'yahoo', start, end)
        except Exception:
            df = pd.DataFrame()

        if df.empty:
            # fallback to yfinance for daily data if datareader fails
            for attempt in range(2):
                try:
                    df = yf.download(
                        ticker,
                        start=start,
                        end=end,
                        interval=interval,
                        auto_adjust=True,
                        threads=False,
                        progress=False,
                    )
                    if df is not None and not df.empty:
                        break
                except Exception:
                    time.sleep(5 + attempt * 5)

        if df is None or df.empty or 'Close' not in df.columns:
            continue

        df = df.dropna()
        if df.empty or 'Close' not in df.columns:
            continue

        data[ticker] = df
    return data
