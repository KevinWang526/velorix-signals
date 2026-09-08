#!/usr/bin/env python3
import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from quanttrader.alpaca import AlpacaExecution
from quanttrader.config import ALPACA_BASE_URL


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--symbol', required=True)
    p.add_argument('--qty', type=float, default=1.0)
    p.add_argument('--side', choices=['buy', 'sell'], default='buy')
    p.add_argument('--confirm', action='store_true')
    return p.parse_args()


def main():
    args = parse_args()
    ap = AlpacaExecution()
    print('Using Alpaca base URL:', ALPACA_BASE_URL)
    try:
        account = ap.get_account()
        print('Account status:', account.status)
    except Exception as e:
        print('Failed to get account:', e)
        return

    if not args.confirm:
        print(f"Dry run: would {args.side} {args.qty} {args.symbol}")
        return

    try:
        order = ap.submit_order(symbol=args.symbol, qty=args.qty, side=args.side)
        print('Order:', order)
    except Exception as e:
        print('Order failed:', e)


if __name__ == '__main__':
    main()
