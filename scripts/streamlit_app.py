#!/usr/bin/env python3
import csv
from datetime import datetime, timezone, time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from streamlit.components.v1 import html

try:
    import yfinance as yf
except ImportError:
    yf = None

from quanttrader.alpaca import AlpacaExecution, AlpacaMarketData
from quanttrader.config import ORDER_DOLLARS
from quanttrader.strategy import MomentumStrategy


PAGE_TITLE = 'Velorix Live UI'
PAGE_ICON = '📈'
DEFAULT_WATCHLIST = ['AAPL', 'MSFT', 'NVDA', 'QQQ', 'SPY', 'IWM', 'TSLA', 'AMZN', 'META', 'GOOG']


def inject_styles():
    st.markdown(
        """
        <style>
            .main .block-container {
                padding-top: 1rem;
                padding-bottom: 1rem;
                padding-left: 1.5rem;
                padding-right: 1.5rem;
                max-width: 1400px;
            }
            .stApp {
                background: #090c11;
                color: #e9f0fb;
            }
            .stSidebar {
                background: linear-gradient(180deg, #0f1726 0%, #111c2b 100%);
            }
            .header-card,
            .metric-card,
            .info-card,
            .table-card,
            .form-card {
                border-radius: 24px;
                padding: 24px;
                background: rgba(255,255,255,0.05);
                box-shadow: 0 24px 55px rgba(0, 0, 0, 0.18);
                border: 1px solid rgba(255,255,255,0.08);
                backdrop-filter: blur(18px);
            }
            .metric-card {
                min-height: 140px;
                color: #ffffff;
            }
            .metric-card.orange {
                background: linear-gradient(135deg, #ff7a34 0%, #ff872a 100%);
                color: white;
            }
            .metric-card.green {
                background: linear-gradient(135deg, #1ac18f 0%, #12b18b 100%);
                color: white;
            }
            .metric-card.dark {
                background: rgba(255,255,255,0.07);
                color: #e9f0fb;
            }
            .metric-card h3,
            .metric-card p,
            .metric-card span {
                color: inherit;
            }
            .metric-card small {
                color: rgba(255,255,255,0.8);
            }
            .nav-section {
                padding: 18px 14px 14px 14px;
                margin-bottom: 1rem;
                border-radius: 24px;
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.08);
            }
            .nav-link {
                display: flex;
                align-items: center;
                gap: 10px;
                padding: 12px 14px;
                border-radius: 14px;
                margin-bottom: 8px;
                color: #cbd5f7;
            }
            .nav-link.active,
            .nav-link:hover {
                background: rgba(255,255,255,0.08);
                color: white;
            }
            .nav-link svg {
                width: 18px;
                height: 18px;
            }
            .filter-badge {
                display: inline-flex;
                align-items: center;
                border-radius: 999px;
                padding: 8px 14px;
                margin-right: 8px;
                margin-bottom: 8px;
                background: rgba(255,255,255,0.08);
                color: #e9f0fb;
                border: 1px solid rgba(255,255,255,0.1);
                font-size: 0.9rem;
                font-weight: 600;
            }
            .filter-badge.active {
                background: #2d6bf6;
                border-color: #2d6bf6;
            }
            .signal-table th {
                color: #a0b3dd;
                font-weight: 700;
            }
            .signal-table td {
                color: #e9f0fb;
            }
            .signal-badge {
                display: inline-flex;
                align-items: center;
                border-radius: 999px;
                padding: 6px 12px;
                font-size: 0.85rem;
                font-weight: 700;
            }
            .signal-badge.long {
                background: #1e8f53;
                color: white;
            }
            .signal-badge.short {
                background: #d04460;
                color: white;
            }
            .panel-card {
                border-radius: 20px;
                padding: 22px 24px;
                background: rgba(24, 38, 61, 0.82);
                border: 1px solid rgba(255,255,255,0.08);
                margin-bottom: 1rem;
            }
            .status-pill {
                display: inline-flex;
                align-items: center;
                padding: 0.45rem 0.85rem;
                border-radius: 999px;
                font-size: 0.9rem;
                font-weight: 700;
                background: rgba(45, 107, 246, 0.18);
                color: #d6e4ff;
                border: 1px solid rgba(45, 107, 246, 0.4);
            }
            .metric-row {
                display: flex;
                gap: 18px;
                flex-wrap: wrap;
                margin-bottom: 20px;
            }
            .metric-row .metric-card {
                flex: 1 1 240px;
                min-width: 220px;
            }
            .metric-card h3 {
                margin-bottom: 0.35rem;
                font-size: 1rem;
                letter-spacing: 0.02em;
                text-transform: uppercase;
                color: #a0b3dd;
            }
            .metric-card p {
                margin: 0;
                font-size: 2rem;
                font-weight: 700;
            }
            .metric-card small {
                opacity: 0.82;
            }
            .stButton>button {
                border-radius: 14px;
                padding: 0.9rem 1rem;
                font-weight: 700;
            }
            .stButton>button:hover {
                opacity: 0.95;
            }
            .stTextInput>div>div>input,
            .stNumberInput>div>div>input,
            .stSelectbox>div>div>div>select,
            .stCheckbox>label {
                color: #e9f0fb;
            }
            .stMarkdown>div>p,
            .stMarkdown>div>h1,
            .stMarkdown>div>h2,
            .stMarkdown>div>h3,
            .stMarkdown>div>h4,
            .stMarkdown>div>h5 {
                color: #e9f0fb;
            }
            .css-1d391kg .st-cm {
                background: transparent;
            }
            /* Left nav / app shell */
            .app-shell {
                display: flex;
                gap: 18px;
            }
            .left-nav {
                min-width: 220px;
                background: linear-gradient(180deg, #07111a 0%, #0b1824 100%);
                border-radius: 14px;
                padding: 18px;
                color: #cfe6ff;
            }
            .left-nav a { color: #cfe6ff; text-decoration: none; display:block; padding:8px 10px; border-radius:8px }
            .left-nav a.active { background:#1f3a62; font-weight:800; }
            /* small utility */
            .muted { color: #9fb4db; }
        </style>
        """,
        unsafe_allow_html=True,
    )

STRATEGY_PRESETS = {
    'Strong stock momentum': {
        'tickers': 'AAPL MSFT NVDA',
        'timeframe': '5Min',
        'window': 50,
        'profit_target_pct': 5.0,
        'loss_limit_pct': 3.0,
        'description': 'Follow strong market leaders with trend momentum and moderate stops.',
    },
    'ETF rotation': {
        'tickers': 'QQQ SPY XIU.TO',
        'timeframe': '15Min',
        'window': 50,
        'profit_target_pct': 4.0,
        'loss_limit_pct': 2.5,
        'description': 'Rotate among ETFs for sector/market exposure while keeping risk controls tight.',
    },
    'Small-cap with hard stop': {
        'tickers': 'IWM SMH',
        'timeframe': '15Min',
        'window': 60,
        'profit_target_pct': 6.0,
        'loss_limit_pct': 3.0,
        'description': 'Small-cap / higher-volatility selection with strict position sizing and stop limits.',
    },
}


def init_state():
    if 'cycle' not in st.session_state:
        st.session_state.cycle = 0
    if 'history' not in st.session_state:
        st.session_state.history = {}
    if 'trade_log' not in st.session_state:
        st.session_state.trade_log = []
    if 'last_prices' not in st.session_state:
        st.session_state.last_prices = {}
    if 'status' not in st.session_state:
        st.session_state.status = 'Ready'
    if 'unavailable_symbols' not in st.session_state:
        st.session_state.unavailable_symbols = {}
    if 'data_client' not in st.session_state:
        st.session_state.data_client = None
    if 'exec_client' not in st.session_state:
        st.session_state.exec_client = None
    if 'initialized' not in st.session_state:
        st.session_state.initialized = False
    if 'paper_mode' not in st.session_state:
        st.session_state.paper_mode = False
    if 'portfolio' not in st.session_state:
        st.session_state.portfolio = {}
    if 'cash' not in st.session_state:
        st.session_state.cash = 0.0
    if 'starting_equity' not in st.session_state:
        st.session_state.starting_equity = 0.0
    if 'ticker_map' not in st.session_state:
        st.session_state.ticker_map = {}
    if 'running' not in st.session_state:
        st.session_state.running = False
    if 'warmup' not in st.session_state:
        st.session_state.warmup = True
    if 'total_profit' not in st.session_state:
        st.session_state.total_profit = 0.0
    if 'total_loss' not in st.session_state:
        st.session_state.total_loss = 0.0
    if 'last_order' not in st.session_state:
        st.session_state.last_order = None
    if 'analysis_mode' not in st.session_state:
        st.session_state.analysis_mode = False


def connect_clients():
    import os
    # If user provided API keys in the UI, set them into the environment for
    # the Alpaca clients (these client constructors read env vars by default).
    api_key = st.session_state.get('api_key')
    api_secret = st.session_state.get('api_secret')
    if api_key:
        os.environ['APCA_API_KEY_ID'] = api_key
    if api_secret:
        os.environ['APCA_API_SECRET_KEY'] = api_secret

    if st.session_state.data_client is None:
        st.session_state.data_client = AlpacaMarketData()
    if st.session_state.exec_client is None:
        st.session_state.exec_client = AlpacaExecution()
    try:
        st.session_state.data_client.connect()
        st.session_state.exec_client.connect()
        st.session_state.last_connect = datetime.now(timezone.utc).isoformat()
        return True, None
    except Exception as exc:
        # Keep clients as None so we don't reuse expired/invalid connections
        st.session_state.data_client = None
        st.session_state.exec_client = None
        return False, str(exc)


def now_et():
    return datetime.now(ZoneInfo('America/New_York'))


def is_market_open_et(now=None):
    now = now or now_et()
    if now.weekday() >= 5:
        return False
    return dt_time(9, 30) <= now.time() < dt_time(16, 0)


def market_status_for_symbol(symbol: str):
    data_sym = st.session_state.ticker_map.get(symbol, symbol)
    if data_sym.endswith('.TO'):
        return is_market_open_et(), 'TSX'
    return is_market_open_et(), 'NYSE/NASDAQ'


def market_status_for_tickers(tickers):
    statuses = {}
    for symbol in tickers:
        open_flag, exchange = market_status_for_symbol(symbol)
        statuses[symbol] = {
            'open': open_flag,
            'exchange': exchange,
            'symbol': st.session_state.ticker_map.get(symbol, symbol),
        }
    return statuses


def build_close_series(bars, symbol):
    df = getattr(bars, 'df', None)
    if df is None:
        df = bars
    if not isinstance(df, pd.DataFrame):
        return None
    if isinstance(df.columns, pd.MultiIndex):
        if symbol in df.columns.get_level_values(0):
            df = df.xs(symbol, level=0, axis=1)
        else:
            return None
    df = df.copy()
    if 'close' in df.columns:
        df = df.rename(columns={'close': 'Close'})
    elif 'Close' not in df.columns:
        return None
    if df.empty:
        return None
    if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    return df[['Close']]


def initialize_session(tickers, window, timeframe):
    connected, error = connect_clients()
    if not connected:
        st.session_state.status = f'Connection failed: {error}'
        return False

    st.session_state.history = {t: [] for t in tickers}
    st.session_state.trade_log = []
    st.session_state.last_prices = {}
    st.session_state.unavailable_symbols = {}
    st.session_state.cycle = 0
    st.session_state.initialized = True
    st.session_state.status = 'Connected and initialized'
    st.session_state.running = False
    st.session_state.warmup = True
    st.session_state.total_profit = 0.0
    st.session_state.total_loss = 0.0
    st.session_state.last_order = None
    st.session_state.starting_equity = float(st.session_state.cash)

    for symbol in tickers:
        try:
            data_sym = st.session_state.ticker_map.get(symbol, symbol)
            bars = st.session_state.data_client.get_bars(data_sym, timeframe, limit=window)
            df = build_close_series(bars, data_sym)
            if df is None:
                df = build_close_series(bars, symbol)
            if df is not None:
                st.session_state.history[symbol] = df['Close'].tolist()[-window:]
                st.session_state.status = f'Loaded history for {symbol}'
            else:
                st.session_state.status = f'No history for {symbol}, warming live ticks'
                st.session_state.unavailable_symbols[symbol] = 'history unavailable'
        except Exception as exc:
            st.session_state.history[symbol] = []
            st.session_state.status = f'History failed for {symbol}: {exc}'
            st.session_state.unavailable_symbols[symbol] = f'history failed: {exc}'
    return True


def append_history(symbol, price, window):
    history = st.session_state.history.setdefault(symbol, [])
    history.append(price)
    if len(history) > window:
        history[:] = history[-window:]


def record_trade_log(symbol, price, signal, action, status, order_id, order_qty, comment=''):
    st.session_state.trade_log.append({
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'symbol': symbol,
        'price': price,
        'signal': signal,
        'order_action': action,
        'order_status': status,
        'order_id': order_id,
        'order_qty': order_qty,
        'comment': comment,
    })


def fetch_company_news(symbol: str):
    if yf is None:
        return []
    try:
        ticker = yf.Ticker(symbol)
        news = getattr(ticker, 'news', None)
        if callable(news):
            news = news()
        if not news:
            return []
        return news[:5]
    except Exception:
        return []


def analyze_symbol(symbol: str, close_series: pd.Series, current_price: float, position: dict):
    summary = {
        'symbol': symbol,
        'trend': 'insufficient data',
        'momentum': 'unknown',
        'recommendation': 'No recommendation available.',
        'entry': 'Wait for a clearer signal or more data.',
        'exit': 'Manage risk based on your existing position and stop levels.',
        'support': None,
        'resistance': None,
        'future': 'No future view available until more data is collected.',
    }
    if close_series is None or len(close_series) < 20:
        return summary

    series = close_series.copy().astype(float)
    short_ema = series.ewm(span=12, adjust=False).mean()
    long_ema = series.ewm(span=26, adjust=False).mean()
    recent_rsi = None
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    recent_rsi = 100 - (100 / (1 + rs))
    rsi_value = float(recent_rsi.iloc[-1]) if len(recent_rsi) >= 1 else None
    momentum = float(series.pct_change(3).iloc[-1]) * 100.0
    price_slope = float(series.pct_change(5).mean()) * 100.0
    trend = 'bullish' if short_ema.iloc[-1] > long_ema.iloc[-1] else 'bearish'
    summary['trend'] = trend
    summary['momentum'] = f'{momentum:+.2f}% over the last 3 bars'
    if rsi_value is not None:
        summary['momentum'] += f', RSI {rsi_value:.1f}'

    support = float(series.tail(20).min())
    resistance = float(series.tail(20).max())
    summary['support'] = support
    summary['resistance'] = resistance

    position_qty = int(position.get('qty', 0))
    avg_cost = float(position.get('avg_cost', 0.0))
    if trend == 'bullish' and momentum > 0:
        if position_qty == 0:
            summary['recommendation'] = (
                'Trend looks positive. Consider waiting for a small pullback toward the short EMA or recent support before buying. '
                'If you decide to buy, keep the first entry size conservative, e.g. 10-20% of your target position.'
            )
        else:
            summary['recommendation'] = (
                'You are in a positive trend. Hold the position and consider adding on a favorable pullback. '
                'Use a trailing stop if price stays above the short EMA.'
            )
    else:
        if position_qty > 0:
            summary['recommendation'] = (
                'Trend is weakening. Consider trimming or closing the position if price drops below the short EMA or recent support.'
            )
        else:
            summary['recommendation'] = (
                'Not a strong buy signal today. Wait for the trend to turn bullish and momentum to improve before initiating a position.'
            )

    if current_price < support:
        summary['entry'] = 'Price is below recent support; avoid new long entries until a stable base forms.'
    elif current_price < short_ema.iloc[-1]:
        summary['entry'] = 'Current price is below the short EMA. A pullback buy around this level may be more attractive than chasing higher prices.'
    else:
        summary['entry'] = 'Price is above the short EMA. If trend stays strong, use a small starter position and watch for a shallow pullback.'

    if position_qty > 0:
        if current_price > avg_cost:
            summary['exit'] = 'The position is profitable. Consider holding with a trailing stop near the short EMA or below recent support.'
        else:
            summary['exit'] = 'The position is currently below cost. Consider reducing risk if the trend does not recover quickly.'
    else:
        summary['exit'] = 'No current position. Use the trend and support/resistance levels to plan future entries.'

    if price_slope > 0.2:
        future = 'The short-term slope is positive, suggesting a higher probability of continuation in the direction of the trend.'
    else:
        future = 'The short-term slope is flat or negative, so future direction is uncertain and caution is warranted.'
    summary['future'] = future
    return summary


def compact_signal_label(signal_series):
    if signal_series is None or len(signal_series) == 0:
        return 'Hold'
    current = int(signal_series.iloc[-1])
    prev = int(signal_series.iloc[-2]) if len(signal_series) > 1 else 0
    if current == 1 and prev == 0:
        return 'Buy'
    if current == 0 and prev == 1:
        return 'Sell'
    return 'Hold'


def build_signal_feed(tickers, window, timeframe, max_symbols=20):
    strategy = MomentumStrategy(short_window=max(5, window // 2), long_window=window)
    rows = []
    for symbol in tickers:
        data_sym = st.session_state.ticker_map.get(symbol, symbol)
        try:
            client = st.session_state.data_client or AlpacaMarketData()
            bars = client.get_bars(data_sym, timeframe, limit=window)
            df = build_close_series(bars, data_sym)
            if df is None:
                df = build_close_series(bars, symbol)
            if df is None or df.empty:
                continue
            series = df['Close'].astype(float)
            signal = None
            if len(series) >= strategy.long_window:
                signal = strategy.generate_signals(series)
            current_price = float(series.iloc[-1])
            action = compact_signal_label(signal)
            analysis = analyze_symbol(symbol, series, current_price, st.session_state.portfolio.get(symbol, {'qty': 0, 'avg_cost': 0.0}))
            momentum = float(series.pct_change(3).iloc[-1]) * 100.0 if len(series) > 3 else 0.0
            rows.append({
                'symbol': symbol,
                'data_symbol': data_sym,
                'action': action,
                'signal': int(signal.iloc[-1]) if signal is not None else 0,
                'price': current_price,
                'trend': analysis['trend'],
                'momentum': f'{momentum:+.2f}%',
                'detail': analysis['recommendation'],
            })
        except Exception:
            continue
    rows.sort(key=lambda x: (0 if x['action'] == 'Buy' else 1 if x['action'] == 'Hold' else 2, -abs(float(x['momentum'].replace('%', '') or 0))))
    return rows[:max_symbols]


def render_signal_table(rows):
    if not rows:
        return ''
    html = [
        '<div class="table-card">',
        '<table style="width:100%; border-collapse:collapse;">',
        '<thead><tr style="text-align:left; color:#9fb4db;">',
        '<th style="padding:10px">Asset</th><th style="padding:10px">Action</th><th style="padding:10px">Price</th><th style="padding:10px">Trend</th><th style="padding:10px">Momentum</th>',
        '</tr></thead>',
        '<tbody>'
    ]
    for r in rows:
        action = r.get('action', 'Hold')
        badge_class = 'signal-badge long' if action == 'Buy' else ('signal-badge short' if action == 'Sell' else 'signal-badge')
        momentum = r.get('momentum', '0.00%')
        try:
            mval = float(momentum.replace('%', '').replace('+', '').replace('-', '') or 0.0)
        except Exception:
            mval = 0.0
        momentum_color = '#1ac18f' if momentum.strip().startswith('+') else ('#d04460' if momentum.strip().startswith('-') else '#cfe6ff')
        row_html = (
            f"<tr style=\"border-top:1px solid rgba(255,255,255,0.04)\">"
            f"<td style=\"padding:12px;vertical-align:middle;\"><strong>{r['symbol']}</strong>"
            f"<div class=\"muted\" style=\"font-size:0.85rem\">{r['data_symbol']}</div></td>"
            f"<td style=\"padding:12px;vertical-align:middle;\"><span class=\"{badge_class}\">{action}</span></td>"
            f"<td style=\"padding:12px;vertical-align:middle;\">${r['price']:.2f}</td>"
            f"<td style=\"padding:12px;vertical-align:middle;\">{r.get('trend','-').title()}</td>"
            f"<td style=\"padding:12px;vertical-align:middle;color:{momentum_color};\">{momentum}</td>"
            f"</tr>"
        )
        html.append(row_html)
    html.append('</tbody></table></div>')
    return ''.join(html)


def render_analysis_section(tickers, window, timeframe):
    st.subheader('Helper analysis')
    for symbol in tickers:
        data_sym = st.session_state.ticker_map.get(symbol, symbol)
        history = st.session_state.history.get(symbol, [])
        if not history:
            st.warning(f'No price history available for {symbol}.')
            continue

        close_series = pd.Series(history)
        current_price = None
        if symbol in st.session_state.last_prices:
            current_price = float(st.session_state.last_prices[symbol])
        else:
            try:
                latest_trade = st.session_state.data_client.get_latest_trade(data_sym)
                current_price = float(latest_trade.price)
            except Exception:
                current_price = float(close_series.iloc[-1]) if len(close_series) else 0.0

        if current_price is None:
            current_price = float(close_series.iloc[-1]) if len(close_series) else 0.0

        position = st.session_state.portfolio.get(symbol, {'qty': 0, 'avg_cost': 0.0})
        analysis = analyze_symbol(symbol, close_series, current_price, position)

        st.markdown(f'### {symbol} ({data_sym})')
        if data_sym != symbol:
            st.write('Input symbol:', symbol)
            st.write('Mapped data symbol:', data_sym)
        st.write('Current price:', f'{current_price:.2f}')
        st.write('Position:', f"{position.get('qty', 0)} @ {position.get('avg_cost', 0.0):.2f}")
        st.write('Trend:', analysis['trend'])
        st.write('Momentum:', analysis['momentum'])
        if analysis['support'] is not None and analysis['resistance'] is not None:
            st.write(f"Support: {analysis['support']:.2f} | Resistance: {analysis['resistance']:.2f}")
        st.write('Recommendation:', analysis['recommendation'])
        st.write('Entry guidance:', analysis['entry'])
        st.write('Exit guidance:', analysis['exit'])
        st.write('Future view:', analysis['future'])

        chart_df = pd.DataFrame({
            'Close': close_series,
            'Short EMA': close_series.ewm(span=12, adjust=False).mean(),
            'Long EMA': close_series.ewm(span=26, adjust=False).mean(),
        })
        st.line_chart(chart_df.tail(max(window, 50)))

        if yf is not None:
            news = fetch_company_news(data_sym)
            if news:
                st.write('Latest news:')
                for item in news:
                    title = item.get('title') or item.get('headline')
                    link = item.get('link') or item.get('id')
                    summary = item.get('summary') or item.get('publisher') or ''
                    if title:
                        if link:
                            st.write(f"- [{title}]({link}) {summary}")
                        else:
                            st.write(f"- {title} {summary}")
            else:
                st.write('No recent news available through yfinance.')
        else:
            st.write('Install yfinance to enable news and company report summaries.')

        st.markdown('---')


def run_cycle(tickers, window, timeframe, confirm, dry_run, max_position_pct=0.0, order_alloc_pct=5.0):
    short_window = max(5, window // 2)
    long_window = window
    strategy = MomentumStrategy(short_window=short_window, long_window=long_window)
    stats = []
    for symbol in tickers:
        try:
            data_sym = st.session_state.ticker_map.get(symbol, symbol)
            price = float(st.session_state.data_client.get_latest_trade(data_sym).price)
            st.session_state.last_prices[symbol] = price
            append_history(symbol, price, window)
            series = pd.Series(st.session_state.history[symbol])
            signal = None
            if len(series) >= strategy.long_window:
                signal = strategy.generate_signals(series)
            order_action = 'none'
            order_status = ''
            order_id = ''
            order_qty = ''
            if signal is not None:
                current = int(signal.iloc[-1])
                prev = int(signal.iloc[-2]) if len(signal) > 1 else 0
                if current == 1 and prev == 0:
                    order_action = 'buy'
                elif current == 0 and prev == 1:
                    order_action = 'sell'
                else:
                    order_action = 'hold'
                if st.session_state.warmup:
                    order_status = 'warmup'
                    order_action = 'hold'
                elif order_action in ('buy', 'sell'):
                    if order_action == 'buy':
                        # Size order by percent of current equity (safer than using full ORDER_DOLLARS)
                        alloc_value = max(0.0, current_equity() * (order_alloc_pct / 100.0))
                        qty = max(1, int(alloc_value / max(price, 0.01)))
                        # Cap by ORDER_DOLLARS as an upper limit
                        try:
                            cap_qty = max(1, int(ORDER_DOLLARS / max(price, 0.01)))
                        except Exception:
                            cap_qty = qty
                        qty = min(qty, cap_qty)
                        order_qty = qty
                    else:
                        p = st.session_state.portfolio.get(symbol, {'qty': 0, 'avg_cost': 0.0})
                        sell_qty = p['qty']
                        order_qty = sell_qty
                    if not confirm:
                        order_status = 'signal-only'
                    elif order_action == 'buy':
                        if current_percent_pl() < 0:
                            order_status = 'buy-blocked-loss'
                        else:
                            if max_position_pct > 0:
                                existing_value = st.session_state.portfolio.get(symbol, {}).get('qty', 0) * price
                                target_value = qty * price + existing_value
                                if target_value > current_equity() * (max_position_pct / 100.0):
                                    order_status = 'position-limit'
                                    qty = 0
                            if qty > 0:
                                if st.session_state.paper_mode:
                                    cost = qty * price
                                    if st.session_state.cash >= cost:
                                        p = st.session_state.portfolio.get(symbol, {'qty': 0, 'avg_cost': 0.0})
                                        total_qty = p['qty'] + qty
                                        if total_qty > 0:
                                            new_avg = ((p['qty'] * p['avg_cost']) + (qty * price)) / total_qty
                                        else:
                                            new_avg = price
                                        st.session_state.portfolio[symbol] = {'qty': total_qty, 'avg_cost': new_avg}
                                        st.session_state.cash -= cost
                                        order_status = 'simulated-buy'
                                        order_id = f'sim-buy-{symbol}-{st.session_state.cycle+1}'
                                    else:
                                        order_status = 'insufficient-cash'
                                else:
                                    if dry_run:
                                        order_status = 'dry-run'
                                    else:
                                        try:
                                            order = st.session_state.exec_client.submit_order(symbol=symbol, qty=qty, side='buy')
                                            order_status = 'submitted'
                                            order_id = getattr(order, 'id', str(order))
                                        except Exception as exc:
                                            order_status = 'failed'
                                            order_id = ''
                                            st.warning(f'Order failed for {symbol}: {exc}')
                    elif order_action == 'sell':
                        p = st.session_state.portfolio.get(symbol, {'qty': 0, 'avg_cost': 0.0})
                        if p['qty'] > 0:
                            sell_qty = p['qty']
                            order_qty = sell_qty
                            proceeds = sell_qty * price
                            cost_basis = sell_qty * p['avg_cost']
                            pnl = proceeds - cost_basis
                            if pnl < 0:
                                order_status = 'sell-blocked-loss'
                            else:
                                if st.session_state.paper_mode:
                                    st.session_state.total_profit += pnl
                                    st.session_state.cash += proceeds
                                    st.session_state.portfolio[symbol] = {'qty': 0, 'avg_cost': 0.0}
                                    order_status = 'simulated-sell'
                                    order_id = f'sim-sell-{symbol}-{st.session_state.cycle+1}'
                                else:
                                    if dry_run:
                                        order_status = 'dry-run'
                                    else:
                                        try:
                                            order = st.session_state.exec_client.submit_order(symbol=symbol, qty=sell_qty, side='sell')
                                            order_status = 'submitted'
                                            order_id = getattr(order, 'id', str(order))
                                        except Exception as exc:
                                            order_status = 'failed'
                                            order_id = ''
                                            st.warning(f'Order failed for {symbol}: {exc}')
                        else:
                            order_status = 'nothing-to-sell'
                else:
                    order_status = 'signal-only'
            record_trade_log(symbol, price, int(signal.iloc[-1]) if signal is not None else 0, order_action, order_status, order_id, order_qty)
            stats.append({'symbol': symbol, 'price': price, 'signal': int(signal.iloc[-1]) if signal is not None else 0, 'status': order_status})
        except Exception as exc:
            st.warning(f'Live price failed for {symbol}: {exc}')
            st.session_state.unavailable_symbols[symbol] = str(exc)
            record_trade_log(symbol, 0.0, 0, 'none', 'price-failed', '', '', str(exc))
    st.session_state.cycle += 1
    if st.session_state.warmup:
        st.session_state.warmup = False
        st.session_state.status = 'Warmup cycle completed'
    else:
        st.session_state.status = f'Cycle {st.session_state.cycle} completed'
    return stats


def trade_log_csv():
    if not st.session_state.trade_log:
        return ''
    df = pd.DataFrame(st.session_state.trade_log)
    return df.to_csv(index=False).encode('utf-8')


def portfolio_dataframe():
    rows = []
    last_prices = st.session_state.get('last_prices', {})
    for sym, pos in st.session_state.portfolio.items():
        qty = pos.get('qty', 0)
        avg = pos.get('avg_cost', 0.0)
        price = float(last_prices.get(sym, 0.0))
        data_sym = st.session_state.ticker_map.get(sym, sym)
        market = qty * price
        cost = qty * avg
        pnl = market - cost
        rows.append({'symbol': sym, 'data_symbol': data_sym, 'qty': qty, 'avg_cost': avg, 'price': price, 'market_value': market, 'cost_basis': cost, 'unrealized_pnl': pnl})
    df = pd.DataFrame(rows)
    return df


def start_trading(profit_target_pct=0.0, loss_limit_pct=0.0):
    st.session_state.running = True
    status_parts = ['Running']
    if profit_target_pct > 0:
        status_parts.append(f'stop after profit ≥ {profit_target_pct:.2f}%')
    if loss_limit_pct > 0:
        status_parts.append(f'stop after loss ≥ {loss_limit_pct:.2f}%')
    st.session_state.status = ' | '.join(status_parts)


def stop_trading():
    st.session_state.running = False
    st.session_state.status = 'Stopped'


def current_equity():
    cash = st.session_state.cash
    value = cash
    for sym, pos in st.session_state.portfolio.items():
        qty = pos.get('qty', 0)
        price = float(st.session_state.last_prices.get(sym, 0.0))
        value += qty * price
    return value


def current_percent_pl():
    if st.session_state.starting_equity <= 0:
        return 0.0
    return (current_equity() - st.session_state.starting_equity) / st.session_state.starting_equity * 100.0


def check_stop_thresholds(profit_target_pct, loss_limit_pct):
    pct_pl = current_percent_pl()
    if profit_target_pct > 0 and pct_pl >= profit_target_pct:
        st.session_state.status = f'Stopped after profit target: {pct_pl:.2f}% >= {profit_target_pct:.2f}%'
        return True
    if loss_limit_pct > 0 and pct_pl <= -loss_limit_pct:
        st.session_state.status = f'Stopped after loss limit: {pct_pl:.2f}% <= -{loss_limit_pct:.2f}%'
        return True
    return False


def main():
    st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON)
    init_state()
    inject_styles()

    with st.container():
        st.markdown(
            '<div class="header-card">'
            '<div style="display:flex;align-items:center;gap:18px;flex-wrap:wrap; justify-content:space-between;">'
            '<div>'
            f'<h1 style="margin:0;font-size:2.6rem;">{PAGE_TITLE}</h1>'
            '<p style="margin:0.5rem 0 0 0; color:#cddbf5; font-size:1rem; line-height:1.5; max-width:760px;">A modern personal quant dashboard with live signals, risk controls, and helper analysis for US and Canadian stocks.</p>'
            '</div>'
            '<div style="display:flex;gap:12px;flex-wrap:wrap;align-items:center;">'
            '<div style="background:#1f3a62;border-radius:999px;padding:12px 16px;color:#d6e4ff;font-weight:700;">Live session</div>'
            '</div>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )

    equity_value = current_equity() if st.session_state.initialized else 0.0
    cash_value = st.session_state.cash if st.session_state.initialized else 0.0
    positions_count = sum(1 for pos in st.session_state.portfolio.values() if pos.get('qty', 0) > 0)
    cycle_count = st.session_state.cycle

    st.markdown(
        '<div class="metric-row">'
        f'<div class="metric-card dark"><h3>Current equity</h3><p>${equity_value:,.2f}</p><small>Cash + net positions</small></div>'
        f'<div class="metric-card dark"><h3>Available cash</h3><p>${cash_value:,.2f}</p><small>Paper balance</small></div>'
        f'<div class="metric-card dark"><h3>Positions</h3><p>{positions_count}</p><small>Symbols held</small></div>'
        f'<div class="metric-card dark"><h3>Cycles</h3><p>{cycle_count}</p><small>Live updates run</small></div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Broker credentials panel: allow users to paste fresh keys and test connection
    with st.sidebar.expander('Broker / API Keys (Alpaca)', expanded=True):
        st.markdown('Provide API credentials to connect to your broker. Keys are used only in-memory for this session.')
        api_key_input = st.text_input('Alpaca API key', value=st.session_state.get('api_key', ''))
        api_secret_input = st.text_input('Alpaca API secret', value=st.session_state.get('api_secret', ''), type='password')
        if st.button('Test connection'):
            st.session_state['api_key'] = api_key_input.strip()
            st.session_state['api_secret'] = api_secret_input.strip()
            ok, err = connect_clients()
            if ok:
                st.success('Connected to Alpaca successfully.')
            else:
                st.error(f'Connection failed: {err}')

    with st.sidebar.form('settings'):
        st.markdown('## Workspace')
        st.caption('Strategy presets, watchlist, and risk controls.')
        strategy_mode = st.selectbox('Strategy preset', list(STRATEGY_PRESETS.keys()), index=0)
        preset = STRATEGY_PRESETS[strategy_mode]
        st.markdown(f"**Preset:** {preset['description']}")
        st.markdown(f"Recommended tickers: `{preset['tickers']}`")
        use_auto_watchlist = st.checkbox('Use default AlphaSignal-style watchlist', value=True, help='Auto-select a core set of tickers for live signal scanning.')
        if use_auto_watchlist:
            tickers_input = st.text_input('Watchlist', value=' '.join(DEFAULT_WATCHLIST))
        else:
            tickers_input = st.text_input('Watchlist', value=preset['tickers'])
        mappings_input = st.text_input('Ticker mappings (INPUT:DATA, e.g. NVDA:NVDA.TO)', 'NVDA:NVDA.TO,SNDK:SNDK.TO,CNQ:CNQ.TO')
        positions_input = st.text_input('Starting portfolio positions', 'NVDA:10:48.15,SNDK:10:48.00,CNQ:20:60.64')
        st.markdown('---')
        st.markdown('## Data & timing')
        timeframe = st.selectbox('History timeframe', ['1Min', '5Min', '15Min', '1H', '1D'], index=['1Min','5Min','15Min','1H','1D'].index(preset['timeframe']))
        window = st.number_input('History window', min_value=20, max_value=200, value=preset['window'])
        st.markdown('---')
        st.markdown('## Risk controls')
        paper_mode = st.checkbox('Paper mode', value=True, help='Simulate orders locally for safe testing.')
        confirm = st.checkbox('Confirm orders', value=False, help='Require explicit order approval before executing.')
        cash_input = st.number_input('Starting cash', min_value=0.0, value=1000.0, format='%f')
        max_position_pct = st.number_input('Max position size (%)', min_value=0.0, value=5.0, format='%f', help='Limit the size of any single position as a percentage of equity.')
        order_alloc_pct = st.number_input('Order allocation (%) per trade', min_value=0.1, max_value=100.0, value=2.0, format='%f', help='Percent of equity to allocate to each new order.')
        profit_target_pct = st.number_input('Take profit threshold (%)', min_value=0.0, value=12.0, format='%f', help='Stop trading when account profit hits this percentage.')
        loss_limit_pct = st.number_input('Stop loss threshold (%)', min_value=0.0, value=6.0, format='%f', help='Stop trading when account loss hits this percentage.')
        dry_run = st.checkbox('Dry run', value=True, help='Do not execute real orders while testing.')
        trade_log_path = st.text_input('Trade log file', './trade_log_ui.csv')
        init_button = st.form_submit_button('Initialize session')

    if init_button:
        tickers = [t.strip().upper() for t in tickers_input.split() if t.strip()]
        if not tickers:
            st.error('Enter at least one ticker.')
        else:
            initialize_session(tickers, window, timeframe)
            # apply paper-mode and starting positions/cash
            st.session_state.paper_mode = bool(paper_mode)
            st.session_state.cash = float(cash_input)
            st.session_state.portfolio = {}
            # parse ticker mappings
            st.session_state.ticker_map = {}
            if mappings_input:
                for part in mappings_input.split(','):
                    part = part.strip()
                    if not part:
                        continue
                    try:
                        src, dst = [p.strip().upper() for p in part.split(':', 1)]
                        st.session_state.ticker_map[src] = dst
                    except Exception:
                        st.warning(f'Invalid mapping entry: {part}')
            if positions_input:
                for part in positions_input.split(','):
                    part = part.strip()
                    if not part:
                        continue
                    try:
                        sym, qty, avg = [p.strip() for p in part.split(':')]
                        sym = sym.upper()
                        qty = int(qty)
                        avg = float(avg)
                        st.session_state.portfolio[sym] = {'qty': qty, 'avg_cost': avg}
                    except Exception:
                        st.warning(f'Invalid position entry: {part}')
            st.session_state.starting_equity = st.session_state.cash + sum(
                pos['qty'] * pos['avg_cost'] for pos in st.session_state.portfolio.values()
            )
            st.session_state.running = False

    if st.session_state.initialized:
        status_badge = '<span class="status-pill">Running</span>' if st.session_state.running else '<span class="status-pill">Ready</span>'
        st.markdown(
            f'<div class="panel-card"><strong>Session status:</strong> {st.session_state.status} &nbsp;&nbsp; {status_badge}</div>',
            unsafe_allow_html=True,
        )
        tab1, tab2 = st.tabs(['Trader', 'Helper'])
        with tab1:
            st.markdown('<div class="panel-card"><strong>Trader mode</strong></div>', unsafe_allow_html=True)
            if st.session_state.unavailable_symbols:
                details = '\n'.join(f'{symbol}: {reason}' for symbol, reason in st.session_state.unavailable_symbols.items())
                st.warning(f'Symbol data issues detected:\n{details}')
            market_status = market_status_for_tickers(st.session_state.history.keys())
            st.markdown(
                '**Signal legend:** 1 = long/buy condition; 0 = flat/exit condition.\n'
                'Orders are placed on transitions: 0→1 triggers buy, 1→0 triggers sell.'
            )
            closed = {symbol: info for symbol, info in market_status.items() if not info['open']}
            if closed:
                details = '\n'.join(f"{symbol} ({info['exchange']})" for symbol, info in closed.items())
                st.warning(f'Market closed for these symbols: {details}')
            col1, col2 = st.columns(2)
            with col1:
                st.button('Start auto trading', on_click=start_trading, args=(profit_target_pct, loss_limit_pct), disabled=st.session_state.running or bool(closed), key='start_button')
            with col2:
                st.button('Stop trading', on_click=stop_trading, disabled=not st.session_state.running, key='stop_button')

            if st.session_state.running:
                if closed:
                    stop_trading()
                    st.warning('Trading stopped because market closed for one or more symbols.')
                else:
                    run_cycle(st.session_state.history.keys(), window, timeframe, confirm, dry_run, max_position_pct, order_alloc_pct)
                    if check_stop_thresholds(profit_target_pct, loss_limit_pct):
                        stop_trading()
                    else:
                        st.info('Running...')
                        st.rerun()

            st.markdown('<div class="panel-card"><strong>Signal feed</strong></div>', unsafe_allow_html=True)
            signal_rows = build_signal_feed(st.session_state.history.keys(), window, timeframe)
            if signal_rows:
                signal_table = pd.DataFrame(signal_rows)[['symbol', 'action', 'signal', 'price', 'trend', 'momentum', 'detail']]
                signal_table = signal_table.rename(columns={
                    'symbol': 'Symbol',
                    'action': 'Action',
                    'signal': 'Raw',
                    'price': 'Price',
                    'trend': 'Trend',
                    'momentum': 'Momentum',
                    'detail': 'Signal summary',
                })
                st.table(signal_table)
            else:
                st.info('No signal feed rows available yet; initialize and connect to fetch live market data.')

            if st.session_state.cycle:
                realized = st.session_state.total_profit - st.session_state.total_loss
                unrealized = sum(
                    (float(st.session_state.last_prices.get(sym, 0.0)) - pos.get('avg_cost', 0.0)) * pos.get('qty', 0)
                    for sym, pos in st.session_state.portfolio.items()
                )
                percent_pl = current_percent_pl()
                st.markdown('<div class="panel-card"><strong>Session summary</strong></div>', unsafe_allow_html=True)
                summary_cols = st.columns(4)
                summary_cols[0].metric('Cycles', st.session_state.cycle)
                summary_cols[1].metric('Realized P/L', f'${realized:.2f}')
                summary_cols[2].metric('Unrealized P/L', f'${unrealized:.2f}')
                summary_cols[3].metric('Net % P/L', f'{percent_pl:.2f}%')
                st.markdown('<div class="panel-card">'
                            f'<p><strong>Starting equity</strong>: ${st.session_state.starting_equity:.2f}</p>'
                            f'<p><strong>Current equity</strong>: ${current_equity():.2f}</p>'
                            '</div>', unsafe_allow_html=True)
                st.markdown('### Last prices')
                st.table(pd.DataFrame.from_dict(st.session_state.last_prices, orient='index', columns=['price']))
                if st.session_state.paper_mode:
                    st.markdown('<div class="panel-card"><strong>Portfolio</strong></div>', unsafe_allow_html=True)
                    dfp = portfolio_dataframe()
                    if not dfp.empty:
                        st.table(dfp)
                    st.markdown(f'<p><strong>Cash</strong>: ${st.session_state.cash:.2f}</p>', unsafe_allow_html=True)
                st.markdown('### Trade history')
                st.table(pd.DataFrame(st.session_state.trade_log).tail(20))
                if st.button('Download trade log'):
                    csv_bytes = trade_log_csv()
                    if csv_bytes:
                        st.download_button('Download CSV', csv_bytes, file_name=Path(trade_log_path).name, mime='text/csv')
        with tab2:
            st.write('**Helper mode**')
            render_analysis_section(st.session_state.history.keys(), window, timeframe)
    else:
        st.info('Initialize a session to start live testing.')


if __name__ == '__main__':
    main()
