from fastapi import FastAPI, Body, UploadFile, File, Request
from fastapi.staticfiles import StaticFiles
import tempfile
import mimetypes
import requests
from bs4 import BeautifulSoup
import os
try:
    from alpaca_trade_api.rest import REST
except Exception:
    REST = None
import threading
import time
import uuid
from typing import List, Dict
import traceback
from datetime import datetime, timedelta

app = FastAPI(title='Velorix API')

# Ensure uploads directory exists and serve it at /api/uploads
UPLOADS_DIR = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOADS_DIR, exist_ok=True)
app.mount('/api/uploads', StaticFiles(directory=UPLOADS_DIR), name='uploads')

# Lightweight signal generator using yfinance + MomentumStrategy.
# The API returns a dashboard-friendly feed and summary metrics.

try:
    import yfinance as yf
    import pandas as pd
    from quanttrader.strategy import MomentumStrategy
    from quanttrader.alpaca import AlpacaMarketData, AlpacaExecution
    try:
        from yfinance.shared import YFRateLimitError
    except Exception:
        YFRateLimitError = Exception
except Exception:
    yf = None
    pd = None
    MomentumStrategy = None
    AlpacaMarketData = None
    YFRateLimitError = Exception

DEFAULT_WATCHLIST = ['AAPL', 'MSFT', 'NVDA', 'QQQ', 'SPY', 'IWM', 'TSLA', 'AMZN', 'META', 'GOOG']
SIGNALS_CACHE = {'expires_at': None, 'payload': None}
TRADING_STATE = {
    'alpaca_client': None,
    'exec_client': None,
    'portfolio': {},
    'cash': 0.0,
    'running': False,
    'targets': [],  # active price-target orders for watch-and-execute
}


def _has_alpaca_config():
    if AlpacaMarketData is None:
        return False
    try:
        client = AlpacaMarketData()
        return bool(client.api_key and client.api_secret)
    except Exception:
        return False


def _get_alpaca_client():
    # Prefer existing AlpacaMarketData wrapper if available
    if AlpacaMarketData is not None:
        try:
            client = AlpacaMarketData()
            client.connect()
            healthy, error = _check_alpaca_health(client)
            if healthy:
                return (client, None)
            # If the wrapper exists but health check failed, record the error
            # and continue to attempt a REST-based fallback using env vars.
            alpaca_wrapper_error = error
        except Exception:
            alpaca_wrapper_error = None
        except Exception:
            pass

    # Fallback: create a simple Alpaca REST wrapper if API key/secret are provided in env
    api_key = os.getenv('ALPACA_API_KEY')
    api_secret = os.getenv('ALPACA_API_SECRET')
    base_url = os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
    if not api_key or not api_secret:
        return None, None
    if REST is None:
        return None, 'alpaca_trade_api library not installed'

    try:
        rest = REST(api_key, api_secret, base_url=base_url)

        class SimpleAlpacaWrapper:
            def __init__(self, rest_client):
                self._rest = rest_client

            def connect(self):
                return self._rest

            def get_bars(self, symbol, timeframe='1D', limit=100):
                # REST.get_bars returns a Bars object; .df yields a pandas DataFrame
                try:
                    bars = self._rest.get_bars(symbol, timeframe=timeframe, limit=limit)
                    df = getattr(bars, 'df', None)
                    if df is None:
                        # older clients return a list-like; convert to DataFrame
                        import pandas as _pd
                        df = _pd.DataFrame(bars)
                    return df
                except Exception:
                    return None

            def get_account(self):
                return self._rest.get_account()

        client = SimpleAlpacaWrapper(rest)
        healthy, error = _check_alpaca_health(client)
        # Prefer the REST client if healthy. If the REST client is healthy,
        # return it; otherwise, if the Alpaca wrapper previously failed,
        # return that error for diagnostics.
        if healthy:
            return (client, None)
        return (None, error or alpaca_wrapper_error)
    except Exception as exc:
        return None, str(exc)


def _check_alpaca_health(client):
    try:
        connection = client.connect()
        if hasattr(connection, 'get_account'):
            connection.get_account()
        elif hasattr(client, 'get_account'):
            client.get_account()
        else:
            return False, 'Alpaca health check cannot access account API.'
        return True, None
    except Exception as exc:
        return False, str(exc)


def _cache_response(payload):
    SIGNALS_CACHE['payload'] = payload
    SIGNALS_CACHE['expires_at'] = datetime.utcnow() + timedelta(seconds=45)


def _get_cached_response(allow_stale: bool = False):
    if SIGNALS_CACHE['payload'] is None:
        return None
    if SIGNALS_CACHE['expires_at'] is None:
        return SIGNALS_CACHE['payload'] if allow_stale else None
    if datetime.utcnow() < SIGNALS_CACHE['expires_at']:
        return SIGNALS_CACHE['payload']
    if allow_stale:
        return SIGNALS_CACHE['payload']
    SIGNALS_CACHE['payload'] = None
    SIGNALS_CACHE['expires_at'] = None
    return None


def _extract_close_series(df, symbol: str):
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        if symbol in df.columns.get_level_values(0):
            try:
                symbol_frame = df[symbol]
                if 'Close' in symbol_frame.columns:
                    return symbol_frame['Close'].astype(float).dropna()
                if 'close' in symbol_frame.columns:
                    return symbol_frame['close'].astype(float).dropna()
            except Exception:
                return None
    else:
        if 'Close' in df.columns:
            return df['Close'].astype(float).dropna()
        if 'close' in df.columns:
            return df['close'].astype(float).dropna()
        # Alpaca-style bars may use single-letter column names like 'c' for close
        if 'c' in df.columns:
            try:
                return df['c'].astype(float).dropna()
            except Exception:
                pass
        # If the dataframe has a single numeric column, use it as the close series
        if df.shape[1] == 1:
            try:
                return df.iloc[:, 0].astype(float).dropna()
            except Exception:
                pass
    return None


def _build_row(symbol: str, df, strategy, window):
    # Try to get a close price series for the symbol
    series = _extract_close_series(df, symbol)
    # If we don't have enough historical points for the MomentumStrategy, fall back to a lightweight heuristic
    if series is None or len(series) < 3:
        # Attempt to fetch a short daily history via yfinance as a fallback
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period='5d', interval='1d')
            if hist is not None and not hist.empty:
                # extract close
                if 'Close' in hist.columns:
                    closes = hist['Close'].astype(float).dropna()
                elif 'close' in hist.columns:
                    closes = hist['close'].astype(float).dropna()
                elif 'c' in hist.columns:
                    closes = hist['c'].astype(float).dropna()
                else:
                    closes = hist.iloc[:, 0].astype(float).dropna()
                if len(closes) >= 2:
                    latest = float(closes.iloc[-1])
                    prev = float(closes.iloc[-2])
                    pct = ((latest - prev) / max(prev, 0.0001)) * 100.0
                    # Simple thresholds for fallback
                    thresh = 2.0
                    if pct >= thresh:
                        action = 'Buy'
                    elif pct <= -thresh:
                        action = 'Sell'
                    else:
                        action = 'Hold'
                    detail = f'Fallback: recent change {pct:+.2f}% over 1 day; threshold {thresh:.1f}%'
                    row = {
                        'symbol': symbol,
                        'action': action,
                        'signal': 1 if action == 'Buy' else ( -1 if action == 'Sell' else 0 ),
                        'price': round(latest, 2),
                        'trend': 'bullish' if action == 'Buy' else ('bearish' if action == 'Sell' else 'neutral'),
                        'momentum': f'{pct:+.2f}%',
                        'detail': detail,
                    }
                    return _enrich_with_analysis(symbol, row, series=closes)
        except Exception:
            pass
        # As a last resort, try to get a realtime quote
        try:
            p = _get_current_price(symbol, None)
            if p is not None:
                # cannot compute momentum; return hold with explanation
                row = {
                    'symbol': symbol,
                    'action': 'Hold',
                    'signal': 0,
                    'price': round(float(p), 2),
                    'trend': 'neutral',
                    'momentum': '0.00%',
                    'detail': 'Fallback: insufficient history for algorithm; showing current quote.',
                }
                return _enrich_with_analysis(symbol, row, series=None)
        except Exception:
            pass
        # No fallback available
        return None

    # We have sufficient history for the MomentumStrategy
    series = series.tail(window)
    signal = None
    if len(series) >= strategy.long_window:
        signal = strategy.generate_signals(series)
    price = float(series.iloc[-1])
    action = 'Hold'
    if signal is not None and len(signal) > 0:
        curr = int(signal.iloc[-1])
        prev = int(signal.iloc[-2]) if len(signal) > 1 else 0
        if curr == 1 and prev == 0:
            action = 'Buy'
        elif curr == 0 and prev == 1:
            action = 'Sell'
    momentum = (series.pct_change(3).iloc[-1] * 100.0) if len(series) > 3 else 0.0
    row = {
        'symbol': symbol,
        'action': action,
        'signal': int(signal.iloc[-1]) if signal is not None and len(signal) > 0 else 0,
        'price': round(price, 2),
        'trend': 'bullish' if action == 'Buy' else ('bearish' if action == 'Sell' else 'neutral'),
        'momentum': f'{momentum:+.2f}%',
        'detail': 'Computed via MomentumStrategy',
    }
    return _enrich_with_analysis(symbol, row, series=series)


def _build_rows(df, watchlist, strategy, window):
    rows = []
    for symbol in watchlist:
        row = _build_row(symbol, df, strategy, window)
        if row is not None:
            rows.append(row)
    return rows


def _fetch_symbol_df(symbol: str, interval: str, period: str, window: int, alpaca_client=None):
    # Determine if this is a Canadian symbol (e.g., SHOP.TO). For Canadian symbols we avoid extended-hours.
    is_canadian = str(symbol).upper().endswith('.TO') or str(symbol).upper().endswith('.V') or str(symbol).upper().endswith('.CA')
    if alpaca_client is not None and '.' not in symbol and interval == '1d':
        try:
            df = alpaca_client.get_bars(symbol, timeframe='1D', limit=max(window, 60))
            if df is not None and not df.empty:
                return df
        except Exception:
            pass

    try:
        # Use extended-hours (prepost) for US tickers to include pre-market and after-hours prices
        # For Canadian tickers (e.g., ending with .TO) do not request pre/post market data
        prepost = False if is_canadian else True
        df = yf.download(symbol, period=period, interval=interval, progress=False, prepost=prepost)
        if df is None or df.empty:
            ticker = yf.Ticker(symbol)
            # ticker.history supports prepost; pass it for US tickers
            try:
                df = ticker.history(period=period, interval=interval, prepost=prepost)
            except TypeError:
                # older yfinance versions may not accept prepost; fall back
                df = ticker.history(period=period, interval=interval)
        return df
    except Exception as exc:
        if isinstance(exc, YFRateLimitError) or 'too many requests' in str(exc).lower() or 'rate limited' in str(exc).lower():
            raise RuntimeError('YF_RATE_LIMIT') from exc
        return None


def _compute_rsi(series, period=14):
    # simple RSI implementation
    try:
        delta = series.diff().dropna()
        up = delta.where(delta > 0, 0.0)
        down = -delta.where(delta < 0, 0.0)
        ma_up = up.rolling(period).mean()
        ma_down = down.rolling(period).mean()
        rs = ma_up / ma_down
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1]) if not rsi.empty and not rsi.iloc[-1] is None else None
    except Exception:
        return None


def _fetch_fundamentals(symbol: str):
    # Minimal fundamentals via yfinance: forwardPE and earnings trend (if available)
    try:
        t = yf.Ticker(symbol)
        info = {}
        try:
            data = t.info
            info['forwardPE'] = data.get('forwardPE') if isinstance(data, dict) else None
        except Exception:
            info['forwardPE'] = None
        try:
            earnings = t.earnings
            # earnings is a DataFrame with Year/Revenue/Earnings; simple direction
            if earnings is not None and not earnings.empty and 'Earnings' in earnings.columns:
                diffs = earnings['Earnings'].diff().dropna()
                info['earnings_trend'] = 'up' if diffs.iloc[-1] > 0 else 'down'
            else:
                info['earnings_trend'] = None
        except Exception:
            info['earnings_trend'] = None
        return info
    except Exception:
        return {'forwardPE': None, 'earnings_trend': None}


def _compute_sentiment_from_news(symbol: str, max_articles: int = 6):
    # Simple lexicon sentiment over recent headlines fetched via yfinance news
    positive = ['beat', 'beats', 'upgrade', 'buy', 'bull', 'rose', 'surge', 'surged', 'record', 'outperform']
    negative = ['miss', 'missed', 'downgrade', 'sell', 'bear', 'fall', 'fell', 'plunge', 'loss', 'underperform']
    try:
        t = yf.Ticker(symbol)
        news = []
        try:
            news = getattr(t, 'news', []) or []
        except Exception:
            news = []
        if not news:
            return {'score': 0.0, 'count': 0}
        score = 0
        count = 0
        for item in news[:max_articles]:
            title = (item.get('title') if isinstance(item, dict) else str(item)) or ''
            s = title.lower()
            p = sum(1 for w in positive if w in s)
            n = sum(1 for w in negative if w in s)
            score += (p - n)
            count += 1
        norm = score / max(1, count)
        return {'score': float(norm), 'count': count}
    except Exception:
        return {'score': 0.0, 'count': 0}


def _enrich_with_analysis(symbol: str, row: Dict, series=None):
    # Attach fundamental, technical, and sentiment notes to `row['explain']` and structured `explain_struct`
    explain_parts = []
    struct = {'fundamental': {}, 'technical': {}, 'sentiment': {}}
    # fundamentals
    try:
        f = _fetch_fundamentals(symbol)
        struct['fundamental'] = f
        if f.get('forwardPE') is not None:
            explain_parts.append(f"PE: {f['forwardPE']:.2f}")
        if f.get('earnings_trend'):
            explain_parts.append(f"Earnings trend: {f['earnings_trend']}")
    except Exception:
        pass
    # technicals
    try:
        use_series = series
        if use_series is None:
            # try fetching short history
            t = yf.Ticker(symbol)
            hist = t.history(period='30d', interval='1d')
            if hist is not None and not hist.empty:
                if 'Close' in hist.columns:
                    use_series = hist['Close'].astype(float).dropna()
                elif 'c' in hist.columns:
                    use_series = hist['c'].astype(float).dropna()
                else:
                    use_series = hist.iloc[:, 0].astype(float).dropna()
        if use_series is not None and len(use_series) >= 3:
            sma_short = float(use_series.tail(10).mean()) if len(use_series) >= 10 else None
            sma_long = float(use_series.tail(30).mean()) if len(use_series) >= 30 else None
            rsi = _compute_rsi(use_series) if len(use_series) >= 15 else None
            struct['technical'] = {'sma_short': sma_short, 'sma_long': sma_long, 'rsi': rsi}
            if sma_short and sma_long:
                if sma_short > sma_long:
                    explain_parts.append('Technical: short SMA > long SMA (bullish)')
                else:
                    explain_parts.append('Technical: short SMA <= long SMA (bearish)')
            if rsi is not None:
                explain_parts.append(f'Technical: RSI {rsi:.0f}')
    except Exception:
        pass
    # sentiment
    try:
        s = _compute_sentiment_from_news(symbol)
        struct['sentiment'] = s
        if s.get('count', 0) > 0:
            if s['score'] > 0:
                explain_parts.append(f"Sentiment: positive ({s['score']:+.2f}) from {s['count']} articles")
            elif s['score'] < 0:
                explain_parts.append(f"Sentiment: negative ({s['score']:+.2f}) from {s['count']} articles")
            else:
                explain_parts.append(f"Sentiment: neutral from {s['count']} articles")
    except Exception:
        pass

    if not explain_parts:
        explain = row.get('detail') or 'No additional analysis available.'
    else:
        explain = ' | '.join(explain_parts)

    row['explain'] = explain
    row['explain_struct'] = struct
    return row



@app.get('/signals')
async def signals(window: int = 50, interval: str = '1d') -> Dict[str, object]:
    if MomentumStrategy is None or yf is None or pd is None:
        return {
            'signals': [
                {
                    'symbol': s,
                    'action': 'Hold',
                    'signal': 0,
                    'price': 0.0,
                    'trend': 'unknown',
                    'momentum': '0.00%',
                    'detail': 'Missing dependencies: install yfinance, pandas, and quanttrader.strategy'
                }
                for s in DEFAULT_WATCHLIST
            ],
            'summary': {
                'total': len(DEFAULT_WATCHLIST),
                'buy': 0,
                'sell': 0,
                'hold': len(DEFAULT_WATCHLIST),
                'avgMomentum': '0.00%',
                'dataSource': 'unavailable',
                'updatedAt': datetime.utcnow().isoformat() + 'Z',
                'warning': 'Backend is missing required modules.',
            }
        }

    cached = _get_cached_response()
    if cached is not None:
        return cached

    watchlist = DEFAULT_WATCHLIST
    window = max(20, min(window, 100))
    interval = interval if interval in {'1d', '1wk', '1mo'} else '1d'
    period = '1mo' if interval == '1d' else '3mo'
    strategy = MomentumStrategy(short_window=max(5, window // 2), long_window=window)

    alpaca_client, alpaca_health_error = _get_alpaca_client()
    if alpaca_client is None and _has_alpaca_config() and alpaca_health_error is None:
        alpaca_health_error = 'Alpaca config present but failed health check.'

    data_source = 'alpaca' if alpaca_client is not None else 'yfinance'

    rows = []
    rate_limited = False

    if alpaca_client is None:
        try:
            df = yf.download(
                tickers=' '.join(watchlist),
                period=period,
                interval=interval,
                group_by='ticker',
                auto_adjust=False,
                progress=False,
            )
            rows = _build_rows(df, watchlist, strategy, window)
        except Exception as exc:
            if isinstance(exc, YFRateLimitError) or 'too many requests' in str(exc).lower() or 'rate limited' in str(exc).lower():
                rate_limited = True
            rows = []

    if not rows and not rate_limited:
        for symbol in watchlist:
            try:
                df = _fetch_symbol_df(symbol, interval, period, window, alpaca_client)
                row = _build_row(symbol, df, strategy, window)
                if row is not None:
                    rows.append(row)
                else:
                    rows.append({
                        'symbol': symbol,
                        'action': 'Hold',
                        'signal': 0,
                        'price': 0.0,
                        'trend': 'neutral',
                        'momentum': '0.00%',
                        'detail': 'Not enough data to compute signals.'
                    })
            except RuntimeError as exc:
                if str(exc) == 'YF_RATE_LIMIT':
                    rate_limited = True
                    break
                traceback.print_exc()
                rows.append({
                    'symbol': symbol,
                    'action': 'Hold',
                    'signal': 0,
                    'price': 0.0,
                    'trend': 'neutral',
                    'momentum': '0.00%',
                    'detail': 'Unable to fetch symbol data.'
                })
            except Exception:
                traceback.print_exc()
                rows.append({
                    'symbol': symbol,
                    'action': 'Hold',
                    'signal': 0,
                    'price': 0.0,
                    'trend': 'neutral',
                    'momentum': '0.00%',
                    'detail': 'Unable to fetch symbol data.'
                })

    if rate_limited:
        rows = [
            {
                'symbol': s,
                'action': 'Hold',
                'signal': 0,
                'price': 0.0,
                'trend': 'neutral',
                'momentum': '0.00%',
                'detail': 'YFinance rate limit triggered. Try again later or enable Alpaca.'
            }
            for s in watchlist
        ]
        data_source = 'yfinance-rate-limited'

    buy = sum(1 for r in rows if r['action'] == 'Buy')
    sell = sum(1 for r in rows if r['action'] == 'Sell')
    hold = sum(1 for r in rows if r['action'] == 'Hold')
    # Attach any external_urls provided in the request payload to the rows
    try:
        if payload and isinstance(payload, dict) and payload.get('external_urls'):
            ext = payload.get('external_urls') or {}
            if isinstance(ext, dict):
                for r in rows:
                    sym = r.get('symbol')
                    if sym and sym in ext:
                        r['external_inputs'] = ext.get(sym)
    except Exception:
        pass
    momentums = [float(r['momentum'].replace('%', '')) for r in rows if isinstance(r.get('momentum'), str) and r['momentum'].endswith('%')]
    avg_momentum = f"{(sum(momentums) / len(momentums) if momentums else 0.0):+.2f}%"
    warning = ''
    if data_source == 'yfinance-fallback':
        warning = 'Data is using fallback pricing because live fetch failed. Retry later or enable Alpaca API keys.'
    elif data_source == 'yfinance-rate-limited':
        warning = 'YFinance rate limit hit. Wait a few minutes or use Alpaca API keys for more reliable live pricing.'
    elif data_source == 'alpaca' and alpaca_client is None:
        warning = 'Alpaca API was detected but failed to initialize.'

    response = {
        'signals': rows,
        'summary': {
            'total': len(rows),
            'buy': buy,
            'sell': sell,
            'hold': hold,
            'avgMomentum': avg_momentum,
            'dataSource': data_source,
            'alpacaEnabled': _has_alpaca_config(),
            'alpacaConnected': bool(alpaca_client),
            'alpacaHealthError': alpaca_health_error,
            'updatedAt': datetime.utcnow().isoformat() + 'Z',
            'warning': warning,
        },
    }
    _cache_response(response)
    return response


@app.get('/price')
def price(symbol: str):
    """Return current price for a symbol using Alpaca if configured, otherwise yfinance."""
    alpaca_client = None
    try:
        alpaca_client = TRADING_STATE.get('alpaca_client') or AlpacaMarketData()
    except Exception:
        alpaca_client = TRADING_STATE.get('alpaca_client')
    info = _get_price_with_session(symbol, alpaca_client)
    # Merge session dict if present
    session_info = info.get('session') if isinstance(info.get('session'), dict) else {'session': info.get('session'), 'session_cn': None}
    return {
        'symbol': symbol.upper(),
        'price': info.get('price'),
        'price_time': info.get('price_time'),
        'session': session_info,
    }


@app.get('/trade/targets/{target_id}')
def get_target(target_id: str):
    for t in TRADING_STATE.get('targets', []):
        if t.get('id') == target_id:
            return {'target': t}
    return {'error': 'not found'}, 404


@app.post('/trade/connect')
def trade_connect():
    """Attempt to initialize Alpaca client and store in TRADING_STATE."""
    client, err = _get_alpaca_client()
    TRADING_STATE['alpaca_client'] = client
    TRADING_STATE['alpaca_error'] = err
    TRADING_STATE['running'] = False

    exec_client = None
    exec_err = None
    if client is not None:
        try:
            # Try to create an execution client and test account access
            exec_client_obj = AlpacaExecution()
            exec_conn = exec_client_obj.connect()
            # attempt a lightweight account call to verify exec access
            try:
                exec_conn.get_account()
                exec_client = exec_client_obj
            except Exception:
                exec_err = 'Execution client connected but account check failed.'
        except Exception as e:
            exec_err = str(e)

    TRADING_STATE['exec_client'] = exec_client
    TRADING_STATE['exec_error'] = exec_err

    return {
        'alpacaEnabled': _has_alpaca_config(),
        'alpacaConnected': bool(client),
        'alpacaError': err,
        'execConnected': bool(exec_client),
        'execError': exec_err,
    }


@app.get('/trade/health')
def trade_health():
    client = TRADING_STATE.get('alpaca_client')
    exec_client = TRADING_STATE.get('exec_client')
    enabled = _has_alpaca_config()
    return {
        'alpacaEnabled': enabled,
        'alpacaConnected': bool(client),
        'alpacaError': TRADING_STATE.get('alpaca_error'),
        'execConnected': bool(exec_client),
        'execError': TRADING_STATE.get('exec_error'),
    }


@app.post('/trade/signals')
def trade_signals(tickers: List[str] = None, window: int = 50, interval: str = '1d', payload: dict = Body(None)):
    """Return trading-style signals for a provided watchlist (simulation only)."""
    # Accept tickers from JSON body { "tickers": [...] } or query param
    if payload and isinstance(payload, dict) and 'tickers' in payload:
        tickers = payload.get('tickers')
    tickers = tickers or DEFAULT_WATCHLIST
    window = max(20, min(window, 200))
    interval = interval if interval in {'1d', '1wk', '1mo'} else '1d'
    strategy = MomentumStrategy(short_window=max(5, window // 2), long_window=window)
    alpaca_client = TRADING_STATE.get('alpaca_client')
    rows = []
    for symbol in tickers:
        try:
            df = _fetch_symbol_df(symbol, interval, '1mo', window, alpaca_client)
            row = _build_row(symbol, df, strategy, window)
            if row is None:
                rows.append({
                    'symbol': symbol,
                    'action': 'Hold',
                    'signal': 0,
                    'price': 0.0,
                    'trend': 'neutral',
                    'momentum': '0.00%',
                    'detail': 'Not enough data to compute signals.'
                })
            else:
                # Attach any external URLs provided in the payload for this symbol
                try:
                    if payload and isinstance(payload, dict) and payload.get('external_urls'):
                        ext = payload.get('external_urls') or {}
                        if isinstance(ext, dict) and symbol in ext:
                            row['external_inputs'] = ext.get(symbol)
                            # perform light-weight extraction (non-blocking friendly: small timeout)
                            try:
                                extracted = _analyze_external_inputs(row['external_inputs'])
                                # attach brief summary and items
                                row.setdefault('explain_struct', {})
                                row['explain_struct']['external_inputs'] = extracted
                                # naive sentiment: count positive/negative words
                                txt = extracted.get('text') or ''
                                pos_words = ['good', 'great', 'positive', 'beat', 'upgrade', 'outperform']
                                neg_words = ['bad', 'downgrade', 'miss', 'negative', 'decline', 'weak']
                                score = 0
                                lowtxt = txt.lower()
                                for w in pos_words:
                                    score += lowtxt.count(w)
                                for w in neg_words:
                                    score -= lowtxt.count(w)
                                row['explain_struct']['external_sentiment'] = {'score': score, 'pos': sum(lowtxt.count(w) for w in pos_words), 'neg': sum(lowtxt.count(w) for w in neg_words)}
                                # simple adjustment: if strong negative evidence, nudge signal towards Sell
                                if score <= -3 and row.get('action') == 'Hold':
                                    row['action'] = 'Sell'
                                if score >= 3 and row.get('action') == 'Hold':
                                    row['action'] = 'Buy'
                            except Exception:
                                pass
                except Exception:
                    pass
                rows.append(row)
        except Exception:
            rows.append({
                'symbol': symbol,
                'action': 'Hold',
                'signal': 0,
                'price': 0.0,
                'trend': 'neutral',
                'momentum': '0.00%',
                'detail': 'Unable to fetch market data; check network or try again later.'
            })
    buy = sum(1 for r in rows if r['action'] == 'Buy')
    sell = sum(1 for r in rows if r['action'] == 'Sell')
    hold = sum(1 for r in rows if r['action'] == 'Hold')
    return {
        'signals': rows,
        'summary': {
            'total': len(rows),
            'buy': buy,
            'sell': sell,
            'hold': hold,
            'dataSource': 'alpaca' if TRADING_STATE.get('alpaca_client') else 'yfinance',
            'updatedAt': datetime.utcnow().isoformat() + 'Z',
        }
    }


@app.post('/trade/run_once')
def trade_run_once(tickers: List[str] = None, window: int = 50, interval: str = '1d', confirm: bool = False, paper_mode: bool = True, payload: dict = Body(None)):
    """Run a single simulated trading cycle over the given watchlist.

    This returns proposed order actions; it will not submit real orders unless
    `confirm=True` and an execution client exists in TRADING_STATE.
    """
    # Accept JSON body payload (e.g., {"tickers": [...], "window": 50, "interval": "1d", "confirm": true})
    if payload and isinstance(payload, dict):
        tickers = payload.get('tickers', tickers)
        window = payload.get('window', window)
        interval = payload.get('interval', interval)
        confirm = payload.get('confirm', confirm)
        paper_mode = payload.get('paper_mode', paper_mode)

    tickers = tickers or DEFAULT_WATCHLIST
    # Pass through payload so external URLs (if any) are considered when building signals
    signals_resp = trade_signals(tickers, window, interval, payload)
    orders = []
    try:
        from quanttrader.config import ORDER_DOLLARS
    except Exception:
        ORDER_DOLLARS = 1000

    for r in signals_resp['signals']:
        sym = r['symbol']
        action = r['action']
        price = r.get('price', 0.0) or 0.0
        if action == 'Buy':
            qty = 0
            try:
                qty = max(1, int(ORDER_DOLLARS / max(price, 0.01)))
            except Exception:
                qty = 1
            order = {'symbol': sym, 'side': 'buy', 'qty': qty, 'price': price, 'status': 'simulated'}
            # Do not execute real orders unless explicitly confirmed and exec client exists
            if confirm and TRADING_STATE.get('exec_client'):
                try:
                    TRADING_STATE['exec_client'].submit_order(symbol=sym, qty=qty, side='buy')
                    order['status'] = 'submitted'
                except Exception as exc:
                    order['status'] = f'failed: {exc}'
            orders.append(order)
        elif action == 'Sell':
            # Simulated sell of all held qty if present in portfolio
            pos = TRADING_STATE['portfolio'].get(sym, {'qty': 0})
            qty = pos.get('qty', 0)
            order = {'symbol': sym, 'side': 'sell', 'qty': qty, 'price': price, 'status': 'simulated'}
            if confirm and TRADING_STATE.get('exec_client') and qty > 0:
                try:
                    TRADING_STATE['exec_client'].submit_order(symbol=sym, qty=qty, side='sell')
                    order['status'] = 'submitted'
                except Exception as exc:
                    order['status'] = f'failed: {exc}'
            orders.append(order)
    return {'orders': orders, 'signals': signals_resp}


def _get_current_price(symbol: str, alpaca_client=None):
    # Try Alpaca market data first, fall back to yfinance
    try:
        if alpaca_client is not None and '.' not in symbol:
            df = alpaca_client.get_bars(symbol, timeframe='1Min', limit=1)
            if df is not None and not df.empty:
                # df may have 'close', 'Close' or Alpaca-style 'c' column
                if 'c' in df.columns:
                    return float(df['c'].iloc[-1])
                if 'close' in df.columns:
                    return float(df['close'].iloc[-1])
                if 'Close' in df.columns:
                    return float(df['Close'].iloc[-1])
    except Exception:
        pass
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period='1d', interval='1m')
        # For US tickers, include pre/post-market data when requesting recent history
        is_canadian = str(symbol).upper().endswith('.TO') or str(symbol).upper().endswith('.V') or str(symbol).upper().endswith('.CA')
        ticker = yf.Ticker(symbol)
        try:
            hist = ticker.history(period='1d', interval='1m', prepost= (False if is_canadian else True))
        except TypeError:
            hist = ticker.history(period='1d', interval='1m')
        if hist is not None and not hist.empty:
            return float(hist['Close'].iloc[-1])
    except Exception:
        pass
    return None


def _safe_text_from_html(html_bytes):
    try:
        soup = BeautifulSoup(html_bytes, 'html.parser')
        # remove scripts/styles
        for s in soup(['script', 'style', 'noscript']):
            s.extract()
        text = ' '.join(soup.stripped_strings)
        return text
    except Exception:
        return ''


def _analyze_external_inputs(list_of_urls_or_paths):
    """Download and extract text from common file types or web pages.

    Returns a dict with keys: text (joined), items: [{url, type, text, summary, error}], summary: short summary
    This is intentionally lightweight and best-effort: optional deps (pytesseract, PyPDF2, python-docx, openpyxl, yt_dlp) are imported only if available.
    """
    results = []
    combined_texts = []
    if not list_of_urls_or_paths:
        return {'text': '', 'items': [], 'summary': ''}

    # optional imports
    try:
        from PIL import Image
    except Exception:
        Image = None
    try:
        import pytesseract
    except Exception:
        pytesseract = None
    try:
        import PyPDF2
    except Exception:
        PyPDF2 = None
    try:
        import docx
    except Exception:
        docx = None
    try:
        import openpyxl
    except Exception:
        openpyxl = None
    try:
        import yt_dlp
    except Exception:
        yt_dlp = None

    for url in list_of_urls_or_paths:
        item = {'url': url, 'type': None, 'text': None, 'summary': None, 'error': None}
        try:
            # allow passing raw text through as a data: URL or plain text
            if isinstance(url, str) and url.startswith('data:'):
                # skip complex parsing, return decoded portion
                try:
                    _, rest = url.split(',', 1)
                    item['text'] = rest
                    item['type'] = 'data'
                    combined_texts.append(item['text'])
                    item['summary'] = (item['text'][:300] + '...') if len(item['text']) > 300 else item['text']
                    results.append(item)
                    continue
                except Exception:
                    pass

            # If a local file path was provided, read it directly without HTTP
            if isinstance(url, str) and os.path.exists(url):
                ct = mimetypes.guess_type(url)[0] or ''
                # handle by extension/type similar to remote handling
                if 'application/pdf' in ct or url.lower().endswith('.pdf'):
                    item['type'] = 'pdf'
                    if PyPDF2 is not None:
                        try:
                            with open(url, 'rb') as fh:
                                reader = PyPDF2.PdfReader(fh)
                                texts = []
                                for p in reader.pages:
                                    try:
                                        texts.append(p.extract_text() or '')
                                    except Exception:
                                        texts.append('')
                                item['text'] = '\n'.join(texts)
                        except Exception as e:
                            item['error'] = f'pdf-extract-failed: {e}'
                    else:
                        item['error'] = 'PyPDF2 not installed'
                elif mimetypes.guess_type(url)[0] and mimetypes.guess_type(url)[0].startswith('image') or url.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.gif')):
                    item['type'] = 'image'
                    if Image is not None and pytesseract is not None:
                        try:
                            img = Image.open(url)
                            text = pytesseract.image_to_string(img)
                            item['text'] = text
                        except Exception as e:
                            item['error'] = f'image-ocr-failed: {e}'
                    else:
                        item['error'] = 'PIL or pytesseract not installed'
                elif url.lower().endswith('.docx'):
                    item['type'] = 'docx'
                    if docx is not None:
                        try:
                            d = docx.Document(url)
                            texts = [p.text for p in d.paragraphs]
                            item['text'] = '\n'.join(texts)
                        except Exception as e:
                            item['error'] = f'docx-extract-failed: {e}'
                    else:
                        item['error'] = 'python-docx not installed'
                elif url.lower().endswith('.xlsx'):
                    item['type'] = 'xlsx'
                    if openpyxl is not None:
                        try:
                            wb = openpyxl.load_workbook(url, read_only=True, data_only=True)
                            texts = []
                            for name in wb.sheetnames:
                                ws = wb[name]
                                for row in ws.iter_rows(min_row=1, max_row=50, max_col=10, values_only=True):
                                    for c in row:
                                        if c is not None:
                                            texts.append(str(c))
                            item['text'] = '\n'.join(texts)
                        except Exception as e:
                            item['error'] = f'xlsx-extract-failed: {e}'
                    else:
                        item['error'] = 'openpyxl not installed'
                else:
                    # try reading as text file
                    try:
                        with open(url, 'r', encoding='utf-8', errors='ignore') as fh:
                            item['type'] = 'text'
                            item['text'] = fh.read()
                    except Exception as e:
                        item['error'] = f'file-read-failed: {e}'
                # append combined if text found and continue
                if item.get('text'):
                    combined_texts.append(item['text'])
                    item['summary'] = (item['text'][:400] + '...') if len(item['text']) > 400 else item['text']
                results.append(item)
                continue

            # For remote URLs, fetch with a short timeout
            r = requests.get(url, timeout=10, stream=True)
            ct = r.headers.get('content-type', '')
            # prioritize content-type, fallback to url extension
            if 'text/html' in ct or url.lower().endswith(('.htm', '.html')):
                item['type'] = 'html'
                item['text'] = _safe_text_from_html(r.text)
            elif 'application/pdf' in ct or url.lower().endswith('.pdf'):
                item['type'] = 'pdf'
                if PyPDF2 is not None:
                    try:
                        tmpf = tempfile.NamedTemporaryFile(delete=False)
                        for chunk in r.iter_content(1024):
                            tmpf.write(chunk)
                        tmpf.flush()
                        tmpf.close()
                        with open(tmpf.name, 'rb') as fh:
                            reader = PyPDF2.PdfReader(fh)
                            texts = []
                            for p in reader.pages:
                                try:
                                    texts.append(p.extract_text() or '')
                                except Exception:
                                    texts.append('')
                            item['text'] = '\n'.join(texts)
                    except Exception as e:
                        item['error'] = f'pdf-extract-failed: {e}'
                else:
                    item['error'] = 'PyPDF2 not installed'
            elif ct.startswith('image/') or url.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.gif')):
                item['type'] = 'image'
                if Image is not None and pytesseract is not None:
                    try:
                        tmpf = tempfile.NamedTemporaryFile(delete=False)
                        for chunk in r.iter_content(1024):
                            tmpf.write(chunk)
                        tmpf.flush()
                        tmpf.close()
                        img = Image.open(tmpf.name)
                        text = pytesseract.image_to_string(img)
                        item['text'] = text
                    except Exception as e:
                        item['error'] = f'image-ocr-failed: {e}'
                else:
                    item['error'] = 'PIL or pytesseract not installed'
            elif url.lower().endswith('.docx') or 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' in ct:
                item['type'] = 'docx'
                if docx is not None:
                    try:
                        tmpf = tempfile.NamedTemporaryFile(delete=False)
                        for chunk in r.iter_content(1024):
                            tmpf.write(chunk)
                        tmpf.flush()
                        tmpf.close()
                        d = docx.Document(tmpf.name)
                        texts = [p.text for p in d.paragraphs]
                        item['text'] = '\n'.join(texts)
                    except Exception as e:
                        item['error'] = f'docx-extract-failed: {e}'
                else:
                    item['error'] = 'python-docx not installed'
            elif url.lower().endswith('.xlsx') or 'spreadsheet' in ct or 'excel' in ct:
                item['type'] = 'xlsx'
                if openpyxl is not None:
                    try:
                        tmpf = tempfile.NamedTemporaryFile(delete=False)
                        for chunk in r.iter_content(1024):
                            tmpf.write(chunk)
                        tmpf.flush()
                        tmpf.close()
                        wb = openpyxl.load_workbook(tmpf.name, read_only=True, data_only=True)
                        texts = []
                        for name in wb.sheetnames:
                            ws = wb[name]
                            for row in ws.iter_rows(min_row=1, max_row=50, max_col=10, values_only=True):
                                for c in row:
                                    if c is not None:
                                        texts.append(str(c))
                        item['text'] = '\n'.join(texts)
                    except Exception as e:
                        item['error'] = f'xlsx-extract-failed: {e}'
                else:
                    item['error'] = 'openpyxl not installed'
            elif 'youtube.com' in url or 'youtu.be' in url:
                item['type'] = 'youtube'
                if yt_dlp is not None:
                    try:
                        ydl_opts = {'skip_download': True, 'writesubtitles': True, 'writeautomaticsub': True, 'quiet': True}
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(url, download=False)
                            # try to get subtitles or description
                            subs = info.get('subtitles') or info.get('automatic_captions')
                            if subs:
                                # take first available language track
                                langs = list(subs.keys())
                                lang = langs[0]
                                entries = subs[lang]
                                if entries and isinstance(entries, list) and len(entries) > 0:
                                    # entries may contain dicts with 'url' for the subtitle file; try fetch first
                                    sub_url = entries[0].get('url')
                                    if sub_url:
                                        sr = requests.get(sub_url, timeout=10)
                                        item['text'] = _safe_text_from_html(sr.text)
                            if not item.get('text'):
                                # fallback to description
                                item['text'] = info.get('description') or ''
                    except Exception as e:
                        item['error'] = f'yt-dlp-failed: {e}'
                else:
                    item['error'] = 'yt_dlp not installed'
            else:
                # default: treat as HTML/text
                text = _safe_text_from_html(r.text)
                item['type'] = 'html'
                item['text'] = text

            if item.get('text'):
                combined_texts.append(item['text'])
                item['summary'] = (item['text'][:400] + '...') if len(item['text']) > 400 else item['text']
        except Exception as exc:
            item['error'] = str(exc)
        results.append(item)

    joined = '\n\n'.join([i.get('text') or '' for i in results])
    summary = (joined[:800] + '...') if len(joined) > 800 else joined
    return {'text': joined, 'items': results, 'summary': summary}


@app.post('/api/upload')
async def upload_files(request: Request, files: List[UploadFile] = File(...)):
    """Accept multiple uploaded files and save them to the uploads folder.

    Returns JSON with `files: [{filename, url}]` where `url` is a relative
    path under `/api/uploads/` that can be fed back into the `external_urls` list.
    """
    saved = []
    saved_local_paths = []
    for f in files:
        try:
            content = await f.read()
            # use a uuid-prefixed filename to avoid collisions
            safe_name = f"{uuid.uuid4().hex}_{os.path.basename(f.filename)}"
            path = os.path.join(UPLOADS_DIR, safe_name)
            with open(path, 'wb') as fh:
                fh.write(content)
            public_url = str(request.base_url).rstrip('/') + f'/api/uploads/{safe_name}'
            saved.append({'filename': safe_name, 'url': public_url, 'local_path': path})
            saved_local_paths.append(path)
        except Exception as e:
            saved.append({'filename': getattr(f, 'filename', 'unknown'), 'error': str(e)})

    # Best-effort: analyze uploaded files immediately and include analysis in response.
    analysis = None
    try:
        if saved_local_paths:
            # _analyze_external_inputs accepts URLs or local file paths
            analysis = _analyze_external_inputs(saved_local_paths)
    except Exception:
        analysis = None

    return {'files': saved, 'analysis': analysis}


def _get_price_with_session(symbol: str, alpaca_client=None):
    """Return latest price plus timestamp and session label.

    Session label values (English): 'pre-market', 'regular', 'after-hours', 'closed'
    Also include a short Chinese label under `session_cn` (盘前, 盘中, 夜盘, 休市).
    """
    from datetime import datetime
    try:
        # Try Alpaca first (if available)
        if alpaca_client is not None and '.' not in symbol:
            try:
                df = alpaca_client.get_bars(symbol, timeframe='1Min', limit=1)
                if df is not None and not df.empty:
                    # determine close and timestamp
                    if 'c' in df.columns:
                        price = float(df['c'].iloc[-1])
                    elif 'close' in df.columns:
                        price = float(df['close'].iloc[-1])
                    elif 'Close' in df.columns:
                        price = float(df['Close'].iloc[-1])
                    else:
                        price = float(df.iloc[:, 0].iloc[-1])
                    ts = df.index[-1]
                    if getattr(ts, 'tzinfo', None) is None:
                        # assume UTC
                        ts = ts.replace(tzinfo=datetime.timezone.utc)
                    return {'price': price, 'price_time': ts.isoformat(), 'session': _session_from_dt(ts)}
            except Exception:
                pass

        # Fallback to yfinance minute history (include pre/post)
        try:
            ticker = yf.Ticker(symbol)
            is_canadian = str(symbol).upper().endswith('.TO') or str(symbol).upper().endswith('.V') or str(symbol).upper().endswith('.CA')
            try:
                hist = ticker.history(period='1d', interval='1m', prepost=(False if is_canadian else True))
            except TypeError:
                hist = ticker.history(period='1d', interval='1m')
            if hist is not None and not hist.empty:
                # prefer 'Close' column
                if 'Close' in hist.columns:
                    price = float(hist['Close'].iloc[-1])
                elif 'close' in hist.columns:
                    price = float(hist['close'].iloc[-1])
                elif 'c' in hist.columns:
                    price = float(hist['c'].iloc[-1])
                else:
                    price = float(hist.iloc[:, 0].iloc[-1])
                ts = hist.index[-1]
                return {'price': price, 'price_time': ts.isoformat(), 'session': _session_from_dt(ts)}
        except Exception:
            pass
    except Exception:
        pass
    return {'price': None, 'price_time': None, 'session': 'closed'}


def _session_from_dt(dt):
    # Determine market session in New York time
    try:
        from datetime import timezone
        try:
            from zoneinfo import ZoneInfo
            ny = dt.astimezone(ZoneInfo('America/New_York'))
        except Exception:
            # fallback: assume UTC and offset -4/-5 depending on DST not handled here
            ny = dt
        hour = ny.hour
        minute = ny.minute
        t = hour * 60 + minute
        pre_start = 4 * 60
        pre_end = 9 * 60 + 30
        reg_start = 9 * 60 + 30
        reg_end = 16 * 60
        post_start = 16 * 60
        post_end = 20 * 60
        if pre_start <= t < pre_end:
            return {'session': 'pre-market', 'session_cn': '盘前'}
        if reg_start <= t < reg_end:
            return {'session': 'regular', 'session_cn': '盘中'}
        if post_start <= t < post_end:
            return {'session': 'after-hours', 'session_cn': '夜盘'}
        return {'session': 'closed', 'session_cn': '休市'}
    except Exception:
        return {'session': 'closed', 'session_cn': '休市'}


def _process_targets_once():
    """One pass over registered targets: check current price and execute/simulate orders."""
    targets = TRADING_STATE.get('targets', [])
    if not targets:
        return
    alpaca_client = TRADING_STATE.get('alpaca_client')
    exec_client = TRADING_STATE.get('exec_client')
    for t in list(targets):
        if t.get('status') != 'open':
            continue
        symbol = t.get('symbol')
        target_price = t.get('target_price')
        side = t.get('side', 'sell')
        cur = _get_current_price(symbol, alpaca_client)
        if cur is None:
            continue
        # check trigger
        triggered = (side == 'sell' and cur >= target_price) or (side == 'buy' and cur <= target_price)
        if triggered:
            t['triggered_at'] = datetime.utcnow().isoformat() + 'Z'
            t['exec_price'] = cur
            # simulate or submit
            if t.get('confirm') and exec_client:
                try:
                    qty = t.get('qty') or 1
                    exec_client.submit_order(symbol=symbol, qty=qty, side=side)
                    t['status'] = 'submitted'
                except Exception as exc:
                    t['status'] = f'failed: {exc}'
            else:
                t['status'] = 'simulated'


def _target_watcher_loop(interval_seconds: int = 10):
    while True:
        try:
            _process_targets_once()
        except Exception:
            traceback.print_exc()
        time.sleep(interval_seconds)


# start background watcher thread
_watcher_thread = threading.Thread(target=_target_watcher_loop, args=(10,), daemon=True)
_watcher_thread.start()


@app.post('/trade/targets')
def add_target(payload: dict = Body(...)):
    """Register a price target for a symbol. If `confirm=True` and execution client exists, will submit real orders when triggered."""
    symbol = payload.get('symbol')
    side = payload.get('side', 'sell')
    target_price = payload.get('target_price')
    qty = payload.get('qty', 0)
    confirm = payload.get('confirm', False)
    if not symbol or target_price is None:
        return {'error': 'symbol and target_price required'}, 400
    t = {
        'id': str(uuid.uuid4()),
        'symbol': str(symbol).upper(),
        'side': str(side).lower(),
        'target_price': float(target_price),
        'qty': int(qty or 0),
        'confirm': bool(confirm),
        'status': 'open',
        'created_at': datetime.utcnow().isoformat() + 'Z'
    }
    TRADING_STATE.setdefault('targets', []).append(t)
    return {'target': t}


@app.get('/trade/targets')
def list_targets():
    return {'targets': TRADING_STATE.get('targets', [])}


@app.post('/trade/targets/clear')
def clear_targets():
    TRADING_STATE['targets'] = []
    return {'ok': True}
