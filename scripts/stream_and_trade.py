#!/usr/bin/env python3
"""Stream/poll live market data from Alpaca and optionally execute paper orders.

This script supports a local paper-mode (simulated execution) and can
take an initial portfolio + cash. In paper-mode the script will update
the simulated portfolio and cash when orders are executed.
"""

import argparse
import csv
import os
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pandas as pd
from quanttrader.alpaca import AlpacaExecution, AlpacaMarketData
from quanttrader.strategy import MomentumStrategy
from quanttrader.config import ORDER_DOLLARS
from quanttrader.logger import setup_logging


log = setup_logging('stream_and_trade')


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--tickers', nargs='+', required=True)
    p.add_argument('--window', type=int, default=50)
    p.add_argument('--interval', type=int, default=60)
    p.add_argument('--confirm', action='store_true', help='Submit orders when a buy signal occurs')
    p.add_argument('--dry-run', action='store_true', help='Do not submit orders even if --confirm is set')
    p.add_argument('--trade-log', default=None, help='CSV file to save live ticks, signals, and order actions')
    p.add_argument('--timeframe', default='1Min', help='Alpaca bar timeframe for history')
    p.add_argument('--max-cycles', type=int, default=0, help='Stop after this many polling cycles (0 = forever)')
    p.add_argument('--paper-mode', action='store_true', help='Use local paper execution (simulate orders)')
    p.add_argument('--max-position-pct', type=float, default=5.0, help='Max position size as percent of equity')
    p.add_argument('--order-alloc-pct', type=float, default=2.0, help='Percent of equity to allocate per new order')
    p.add_argument('--profit-target-pct', type=float, default=12.0, help='Account-level profit stop percent')
    p.add_argument('--loss-limit-pct', type=float, default=6.0, help='Account-level loss stop percent')
    p.add_argument('--positions', default=None, help='Initial positions, comma-separated SYMBOL:QTY:AVG_PRICE e.g. NVDA:10:48.15,SNDK:10:48.00')
    p.add_argument('--cash', type=float, default=None, help='Initial cash (fiat) to track for paper trading')
    p.add_argument('--ticker-mappings', default=None, help='Ticker mappings, comma-separated INPUT:DATA e.g. NVDA:NVDA.TO,SNDK:SNDK.TO')
    return p.parse_args()


def resolve_data_symbol(symbol: str, ticker_map: dict):
    if not ticker_map:
        ticker_map = {}
    symbol = symbol.upper()
    if symbol in ticker_map:
        return ticker_map[symbol]
    fallback = {
        'NVDA': 'NVDA.TO',
        'SNDK': 'SNDK.TO',
        'CNQ': 'CNQ.TO',
    }
    return fallback.get(symbol, symbol)


def get_initial_history(client, symbol: str, timeframe: str, limit: int):
    try:
        bars = client.get_bars(symbol, timeframe, limit=limit)
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
        df = df[['Close']].copy()
        if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
            df.index = df.index.tz_convert(None)
        return df
    except Exception as e:
        log.warning('Failed to fetch initial bars for %s: %s', symbol, e)
        return None


def get_latest_price(client, symbol: str):
    try:
        trade = client.get_latest_trade(symbol)
        return float(trade.price)
    except Exception as e:
        log.warning('Failed to fetch latest price for %s: %s', symbol, e)
        return None
    


def main():
    args = parse_args()
    tickers = args.tickers
    exec_client = AlpacaExecution()
    data_client = AlpacaMarketData()

    try:
        exec_client.connect()
        data_client.connect()
    except Exception as e:
        log.error('Alpaca connect failed: %s', e)
        return

    log.info('Connected to Alpaca at %s', exec_client.base_url)

    history = {t: deque(maxlen=args.window) for t in tickers}
    stats = {
        'cycles': 0,
        'symbols': len(tickers),
        'price_updates': 0,
        'price_failures': 0,
        'orders_attempted': 0,
        'orders_submitted': 0,
        'warmup_success': 0,
        'warmup_failures': 0,
    }
    ticker_map = {}
    if args.ticker_mappings:
        for part in args.ticker_mappings.split(','):
            try:
                src, dst = part.split(':', 1)
                ticker_map[src.strip().upper()] = dst.strip().upper()
            except Exception:
                log.warning('Invalid ticker mapping: %s', part)

    # Portfolio state for paper-mode
    portfolio = {}
    cash = None
    if args.paper_mode:
        from quanttrader.execution import PaperExecution
        exec_client = PaperExecution()
        # load initial positions
        if args.positions:
            for part in args.positions.split(','):
                try:
                    sym, qty, avg = part.split(':')
                    sym = sym.strip().upper()
                    portfolio[sym] = {'qty': int(float(qty)), 'avg_price': float(avg)}
                except Exception:
                    log.warning('Invalid position entry: %s', part)
        # set initial cash
        if args.cash is not None:
            cash = float(args.cash)
        else:
            # fallback to ORDER_DOLLARS if not provided
            cash = float(ORDER_DOLLARS)
    else:
        # try to use configured ORDER_DOLLARS as placeholder cash if not in paper mode
        cash = None

    trade_log_writer = None
    trade_log_file = None
    if args.trade_log:
        trade_log_path = Path(args.trade_log)
        trade_log_file = trade_log_path.open('a', newline='', encoding='utf-8')
        trade_log_writer = csv.DictWriter(
            trade_log_file,
            fieldnames=['timestamp', 'symbol', 'price', 'signal', 'order_action', 'order_status', 'order_id', 'order_qty', 'comment'],
        )
        if trade_log_path.stat().st_size == 0:
            trade_log_writer.writeheader()

    for t in tickers:
        data_symbol = resolve_data_symbol(t, ticker_map)
        df = get_initial_history(data_client, data_symbol, args.timeframe, limit=args.window)
        if df is not None and 'Close' in df.columns and not df.empty:
            history[t].extend(df['Close'].tolist())
            stats['warmup_success'] += 1
            log.info('Loaded %s bars for %s (%s)', len(history[t]), t, data_symbol)
        else:
            stats['warmup_failures'] += 1
            log.warning('No initial history for %s (%s); warming with live ticks', t, data_symbol)

    strategy = MomentumStrategy(short_window=20, long_window=50)

    try:
        while True:
            stats['cycles'] += 1
            now = datetime.now(timezone.utc)
            for t in tickers:
                data_symbol = resolve_data_symbol(t, ticker_map)
                price = get_latest_price(data_client, data_symbol)
                if price is None:
                    stats['price_failures'] += 1
                    continue
                stats['price_updates'] += 1
                history[t].append(price)
                series = pd.Series(list(history[t]))
                signal = None
                if len(series) >= strategy.long_window:
                    signal = strategy.generate_signals(series)
                latest_sig = int(signal.iloc[-1]) if signal is not None else 0
                log.info('%s %s live_price=%.2f signal=%s', now.isoformat(), t, price, latest_sig)

                order_action = 'none'
                order_status = ''
                order_id = ''
                order_qty = ''
                if latest_sig == 1:
                    order_action = 'signal'
                    if args.confirm:
                        order_action = 'submit'
                        if args.dry_run:
                            order_status = 'dry-run'
                            log.info('Dry-run: order not submitted for %s at %.2f', t, price)
                        else:
                            # Determine equity estimate (use paper cash if available, otherwise fallback to ORDER_DOLLARS)
                            equity_est = float(cash) if cash is not None else float(ORDER_DOLLARS)
                            alloc_value = max(0.0, equity_est * (args.order_alloc_pct / 100.0))
                            qty = max(1, int(alloc_value / max(price, 0.01)))
                            # cap by ORDER_DOLLARS
                            try:
                                cap_qty = max(1, int(ORDER_DOLLARS / max(price, 0.01)))
                            except Exception:
                                cap_qty = qty
                            qty = min(qty, cap_qty)
                            # enforce max position percent
                            existing_value = portfolio.get(t, {}).get('qty', 0) * price
                            target_value = qty * price + existing_value
                            if args.max_position_pct > 0 and target_value > equity_est * (args.max_position_pct / 100.0):
                                order_status = 'position-limit'
                                qty = 0
                            # if paper-mode and cash limited, scale down
                            if cash is not None and qty * price > cash:
                                affordable_qty = int(cash / max(price, 0.01))
                                if affordable_qty > 0:
                                    qty = min(qty, affordable_qty)
                                else:
                                    order_status = 'insufficient-cash'
                            stats['orders_attempted'] += 1
                            order_qty = qty
                            try:
                                if qty > 0:
                                    order = exec_client.submit_order(symbol=t, qty=qty, side='buy')
                                else:
                                    order = None
                                stats['orders_submitted'] += 1
                                order_status = 'submitted'
                                order_id = getattr(order, 'id', str(order))
                                log.info('Submitted order: %s', order)
                            except Exception as e:
                                order_status = 'failed'
                                log.error('Order failed: %s', e)
                    else:
                        order_status = 'signal-only'
                if trade_log_writer is not None:
                    trade_log_writer.writerow({
                        'timestamp': now.isoformat(),
                        'symbol': t,
                        'price': price,
                        'signal': latest_sig,
                        'order_action': order_action,
                        'order_status': order_status,
                        'order_id': order_id,
                        'order_qty': order_qty,
                        'comment': '',
                    })
                    trade_log_file.flush()
            if args.max_cycles and stats['cycles'] >= args.max_cycles:
                log.info('Reached max cycles (%d); finishing.', args.max_cycles)
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        log.info('Stopped by user')
    finally:
        if trade_log_file is not None:
            trade_log_file.close()
        log.info('Run summary: cycles=%d symbols=%d price_updates=%d price_failures=%d warmup_success=%d warmup_failures=%d orders_attempted=%d orders_submitted=%d',
                 stats['cycles'], stats['symbols'], stats['price_updates'], stats['price_failures'],
                 stats['warmup_success'], stats['warmup_failures'], stats['orders_attempted'], stats['orders_submitted'])
        if args.trade_log:
            log.info('Trade log written to %s', args.trade_log)


if __name__ == '__main__':
    main()
