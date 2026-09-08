import os
from typing import Optional, List
import pandas as pd
import requests
from pathlib import Path

try:
    from dotenv import load_dotenv
    from dotenv import find_dotenv
except ImportError:
    load_dotenv = None
    find_dotenv = None

if load_dotenv is not None:
    env_path = Path(__file__).resolve().parents[1] / '.env'
    if env_path.exists():
        load_dotenv(dotenv_path=str(env_path))
    else:
        load_dotenv(find_dotenv())
else:
    env_path = Path(__file__).resolve().parents[1] / '.env'
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            clean = line.strip()
            if not clean or clean.startswith('#') or '=' not in clean:
                continue
            key, value = clean.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip())

# Workaround for older urllib3 / Python 3.12 compatibility.
# alpaca-trade-api or urllib3 may reference ssl.PROTOCOL_SSLv23 internally.
import ssl
try:
    if not hasattr(ssl, 'PROTOCOL_SSLv23'):
        ssl.PROTOCOL_SSLv23 = ssl.PROTOCOL_TLS_CLIENT
except Exception:
    pass

try:
    import urllib3.util.ssl_ as urllib3_ssl
    if not hasattr(urllib3_ssl, 'PROTOCOL_SSLv23'):
        urllib3_ssl.PROTOCOL_SSLv23 = ssl.PROTOCOL_SSLv23
except Exception:
    pass

try:
    import alpaca_trade_api as tradeapi
except Exception:
    tradeapi = None

try:
    import yfinance as yf
except Exception:
    yf = None


class AlpacaExecution:
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, base_url: Optional[str] = None):
        # Support both common env var names: APCA_* (Alpaca SDK) and ALPACA_* (project .env)
        self.api_key = api_key or os.getenv('APCA_API_KEY_ID') or os.getenv('ALPACA_API_KEY')
        self.api_secret = api_secret or os.getenv('APCA_API_SECRET_KEY') or os.getenv('ALPACA_SECRET_KEY')
        self.base_url = base_url or os.getenv('APCA_API_BASE_URL') or os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
        self.client = None

    def connect(self):
        if tradeapi is None:
            raise RuntimeError('Install alpaca-trade-api (pip install alpaca-trade-api)')
        if self.client is None:
            self.client = tradeapi.REST(self.api_key, self.api_secret, self.base_url, api_version='v2')
        return self.client

    def get_account(self):
        c = self.connect()
        return c.get_account()

    def submit_order(self, symbol: str, qty: float, side: str = 'buy', type: str = 'market', time_in_force: str = 'day', validate: bool = False):
        c = self.connect()
        return c.submit_order(symbol=symbol, qty=qty, side=side, type=type, time_in_force=time_in_force, validate=validate)

    def cancel_all_orders(self):
        c = self.connect()
        return c.cancel_all_orders()

    def get_position(self, symbol: str):
        c = self.connect()
        try:
            return c.get_position(symbol)
        except Exception:
            return None


class AlpacaMarketData:
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.getenv('APCA_API_KEY_ID') or os.getenv('ALPACA_API_KEY')
        self.api_secret = api_secret or os.getenv('APCA_API_SECRET_KEY') or os.getenv('ALPACA_SECRET_KEY')
        self.base_url = base_url or os.getenv('APCA_API_BASE_URL') or os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
        self.client = None

    def connect(self):
        if tradeapi is None:
            raise RuntimeError('Install alpaca-trade-api (pip install alpaca-trade-api)')
        if self.client is None:
            self.client = tradeapi.REST(self.api_key, self.api_secret, self.base_url, api_version='v2')
        return self.client

    def _yfinance_interval(self, timeframe: str) -> str:
        mapping = {
            '1Min': '1m',
            '5Min': '5m',
            '15Min': '15m',
            '1H': '60m',
            '1D': '1d',
        }
        return mapping.get(timeframe, '1d')

    def _yahoo_chart(self, symbol: str, interval: str, period: str):
        url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}'
        params = {'interval': interval, 'range': period}
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        result = data.get('chart', {}).get('result')
        if not result:
            return None
        return result[0]

    def _yahoo_history(self, symbol: str, timeframe: str = '1Min', limit: int = 100):
        interval = self._yfinance_interval(timeframe)
        period = '5d' if interval != '1d' else '1mo'
        chart = self._yahoo_chart(symbol, interval, period)
        if chart is None:
            return pd.DataFrame()
        timestamps = chart.get('timestamp', [])
        quote = chart.get('indicators', {}).get('quote', [{}])[0]
        closes = quote.get('close', [])
        if not timestamps or not closes:
            return pd.DataFrame()
        df = pd.DataFrame({'Close': closes}, index=pd.to_datetime(timestamps, unit='s'))
        if df.empty:
            return pd.DataFrame()
        return df.dropna().tail(limit)

    def _yfinance_bars(self, symbol: str, timeframe: str = '1Min', limit: int = 100, start=None, end=None):
        if '.' in symbol:
            return self._yahoo_history(symbol, timeframe, limit)
        if yf is None:
            raise RuntimeError('Install yfinance to fetch Canadian market data: pip install yfinance')
        interval = self._yfinance_interval(timeframe)
        period = '5d' if interval != '1d' else '1mo'
        try:
            df = yf.download(symbol, period=period, interval=interval, auto_adjust=False, progress=False)
        except Exception:
            df = pd.DataFrame()
        if df is None or df.empty:
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(period=period, interval=interval)
            except Exception:
                df = pd.DataFrame()
        if df is None or df.empty:
            return pd.DataFrame()
        if 'Close' not in df.columns and 'close' in df.columns:
            df = df.rename(columns={'close': 'Close'})
        if 'Close' in df.columns:
            return df[['Close']].tail(limit)
        return pd.DataFrame()

    def _yfinance_latest_price(self, symbol: str):
        if '.' in symbol:
            try:
                chart = self._yahoo_chart(symbol, '1d', '5d')
                if chart is not None:
                    quote = chart.get('indicators', {}).get('quote', [{}])[0]
                    closes = quote.get('close', [])
                    if closes and closes[-1] is not None:
                        return float(closes[-1])
            except Exception:
                pass
        if yf is None:
            raise RuntimeError('Install yfinance to fetch Canadian market data: pip install yfinance')
        try:
            ticker = yf.Ticker(symbol)
            info = getattr(ticker, 'fast_info', None)
            if info is not None:
                last_price = getattr(info, 'last_price', None)
                if last_price is not None:
                    return float(last_price)
            info_dict = getattr(ticker, 'info', None) or {}
            if isinstance(info_dict, dict):
                for key in ('regularMarketPrice', 'currentPrice', 'ask', 'previousClose'):
                    if key in info_dict and info_dict[key] is not None:
                        return float(info_dict[key])
            try:
                hist = ticker.history(period='5d', interval='1d')
                if hist is not None and not hist.empty and 'Close' in hist.columns:
                    val = hist['Close'].iloc[-1]
                    if val is not None:
                        return float(val)
            except Exception:
                pass
            try:
                df = yf.download(symbol, period='5d', interval='1d', progress=False)
                if df is not None and not df.empty and 'Close' in df.columns:
                    val = df['Close'].iloc[-1]
                    if val is not None:
                        return float(val)
            except Exception:
                pass
            fallback = self._yfinance_bars(symbol, '1Min', 1)
            if fallback is not None and not fallback.empty and 'Close' in fallback.columns:
                val = fallback['Close'].iloc[-1]
                if val is not None:
                    return float(val)
        except Exception:
            pass
        return None

    def get_bars(self, symbol: str, timeframe: str = '1Min', limit: int = 100, start=None, end=None):
        if '.' in symbol:
            return self._yfinance_bars(symbol, timeframe, limit, start, end)
        try:
            c = self.connect()
            bars = c.get_bars(symbol, timeframe, limit=limit, start=start, end=end)
            df = getattr(bars, 'df', None)
            if df is None:
                df = bars
            if isinstance(df, type(None)):
                return self._yfinance_bars(symbol, timeframe, limit, start, end)
            if isinstance(df, dict):
                df = df.get(symbol, pd.DataFrame())
            return df
        except Exception:
            return self._yfinance_bars(symbol, timeframe, limit, start, end)

    def get_latest_trade(self, symbol: str):
        if '.' in symbol:
            price = self._yfinance_latest_price(symbol)
            if price is not None:
                from types import SimpleNamespace
                return SimpleNamespace(price=price)
            raise RuntimeError(f'No latest price found for {symbol}')
        try:
            c = self.connect()
            return c.get_latest_trade(symbol)
        except Exception:
            price = self._yfinance_latest_price(symbol)
            if price is not None:
                from types import SimpleNamespace
                return SimpleNamespace(price=price)
            raise

    def get_latest_quote(self, symbol: str):
        if '.' in symbol:
            price = self._yfinance_latest_price(symbol)
            if price is not None:
                from types import SimpleNamespace
                return SimpleNamespace(bidprice=price, askprice=price)
            raise RuntimeError(f'No latest quote found for {symbol}')
        c = self.connect()
        return c.get_latest_quote(symbol)

    def get_last_price(self, symbol: str):
        trade = self.get_latest_trade(symbol)
        return float(trade.price)

    def get_last_prices(self, symbols: List[str]):
        return {s: self.get_last_price(s) for s in symbols}
