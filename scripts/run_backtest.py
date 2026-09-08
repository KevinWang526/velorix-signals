#!/usr/bin/env python3
import argparse
import os
import sys
import matplotlib.pyplot as plt

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from quanttrader.data import fetch_data
from quanttrader.sample_data import generate_sample_data
from quanttrader.strategy import MomentumStrategy
from quanttrader.backtest import Backtester


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--tickers', nargs='+', required=True)
    p.add_argument('--start', required=True)
    p.add_argument('--end', required=True)
    return p.parse_args()


def main():
    args = parse_args()
    data = fetch_data(args.tickers, args.start, args.end)
    if not data:
        print('Real data not available; generating synthetic data for smoke test')
        data = {t: generate_sample_data(t, args.start, args.end) for t in args.tickers}
    strat = MomentumStrategy()
    bt = Backtester()
    eq = bt.run_backtest(data, strat)
    print(eq.tail())
    eq.plot(title='Equity Curve')
    plt.tight_layout()
    try:
        plt.show()
    except Exception:
        output_file = 'equity_curve.png'
        plt.savefig(output_file)
        print(f'Saved equity curve to {output_file}')


if __name__ == '__main__':
    main()
