#!/usr/bin/env python3
"""Backtest engine for Aggressive and H.
Dependencies: ccxt, pandas, numpy
Usage:
  python backtest.py --system E --coin BTC --years 5
  python backtest.py --system H --coin ETH --years 3
"""
import sys
import os
import argparse
import time
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from indicators import calc_all_indicators, _binary_signals
from aggressive import score_aggressive as score_E
from conservative import score_conservative as score_H, BULL_SIZING, BEAR_SIZING


def calc_metrics(equity, trades):
    total_return = (equity[-1] / equity[0] - 1) * 100
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    max_dd = abs(dd.min()) * 100
    daily_ret = np.diff(equity) / equity[:-1]
    sharpe = np.sqrt(365) * np.nanmean(daily_ret) / (np.nanstd(daily_ret) + 1e-10)

    if trades:
        wins = sum(1 for t in trades if t > 0)
        win_rate = wins / len(trades) * 100
        gross_profit = sum(t for t in trades if t > 0)
        gross_loss = abs(sum(t for t in trades if t < 0))
        profit_factor = gross_profit / (gross_loss + 1e-10)
    else:
        win_rate = profit_factor = 0

    return {
        'Total Return %': round(total_return, 2),
        'Max Drawdown %': round(max_dd, 2),
        'Sharpe': round(sharpe, 2),
        'Win Rate %': round(win_rate, 1),
        'Trades': len(trades),
        'Profit Factor': round(profit_factor, 2),
        'Calmar': round(total_return / (max_dd + 1e-10), 2),
    }


def run_backtest_e(df, fee=0.001):
    """Standard Aggressive backtest — full position on signal."""
    capital = 10000.0
    position = 0.0
    entry_price = 0.0
    equity = [capital]
    trades = []

    for i in range(1, len(df)):
        row = df.iloc[i]
        if any(np.isnan(row.get(c, np.nan)) for c in ['tsi', 'obv_ema9', 'wt1', 'wt2', 'usdt_d_tsi']):
            equity.append(equity[-1])
            continue

        score, buy_thresh, sell_thresh = score_E(row)

        if position == 0 and score >= buy_thresh:
            position = 1.0
            entry_price = row['close']
            equity[-1] -= equity[-1] * fee
        elif position > 0 and score <= sell_thresh:
            ret = row['close'] / entry_price - 1
            equity[-1] -= equity[-1] * fee
            trades.append(ret)
            position = 0

        if position > 0 and i > 1:
            price_ret = row['close'] / df.iloc[i-1]['close'] - 1
            equity.append(equity[-1] * (1 + price_ret))
        else:
            equity.append(equity[-1])

    if position > 0 and len(df) > 1:
        trades.append(df.iloc[-1]['close'] / entry_price - 1)

    return calc_metrics(np.array(equity), trades)


def run_backtest_h(df, fee=0.001):
    """Conservative backtest — graduated position sizing."""
    capital = 10000.0
    position = 0.0
    entry_price = 0.0
    equity = [capital]
    trades = []
    current_trade = None

    for i in range(1, len(df)):
        row = df.iloc[i]
        if any(np.isnan(row.get(c, np.nan)) for c in ['tsi', 'obv_ema9', 'wt1', 'wt2', 'usdt_d_tsi', 'sma200']):
            equity.append(equity[-1])
            continue

        count, bull_regime, target_pos = score_H(row)

        if target_pos > position:
            add_frac = target_pos - position
            equity[-1] -= equity[-1] * add_frac * fee
            if position == 0:
                entry_price = row['close']
                current_trade = {'entry': row['close']}
            position = target_pos
        elif target_pos < position:
            reduce_frac = position - target_pos
            if entry_price > 0:
                pnl = reduce_frac * equity[-1] * (row['close'] / entry_price - 1)
            else:
                pnl = 0
            equity[-1] += pnl - equity[-1] * reduce_frac * fee
            position = target_pos
            if position == 0 and current_trade:
                trades.append(row['close'] / current_trade['entry'] - 1)
                current_trade = None

        if position > 0 and i > 1:
            price_ret = row['close'] / df.iloc[i-1]['close'] - 1
            equity.append(equity[-1] * (1 + position * price_ret))
        else:
            equity.append(equity[-1])

    if position > 0 and len(df) > 1:
        trades.append(df.iloc[-1]['close'] / entry_price - 1)

    return calc_metrics(np.array(equity), trades)


def fetch_ohlcv(symbol, years=5, exchange_id='bybit'):
    import ccxt
    from datetime import datetime, timedelta

    exchange = getattr(ccxt, exchange_id)()
    exchange.load_markets()
    if symbol not in exchange.markets:
        alt = symbol.replace('/USDT', '/USD')
        if alt in exchange.markets:
            symbol = alt

    start = datetime.now() - timedelta(days=years * 365)
    since = int(start.timestamp() * 1000)
    all_data = []

    while True:
        data = exchange.fetch_ohlcv(symbol, '1d', since=since, limit=1000)
        if not data:
            break
        all_data.extend(data)
        since = data[-1][0] + 1
        time.sleep(0.5)
        if len(data) < 1000:
            break

    df = pd.DataFrame(all_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    df = df[~df.index.duplicated()]
    return df


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Backtest Aggressive or H')
    parser.add_argument('--system', default='E', choices=['E', 'H', 'both'])
    parser.add_argument('--coin', default='BTC')
    parser.add_argument('--years', type=int, default=5)
    parser.add_argument('--exchange', default='bybit')
    args = parser.parse_args()

    symbol = f"{args.coin.upper()}/USDT"
    print(f"\n📈 Backtesting {symbol} — {args.years} years")
    print("=" * 60)

    print(f"  Fetching data from {args.exchange}...")
    df = fetch_ohlcv(symbol, args.years, args.exchange)
    print(f"  Got {len(df)} daily candles: {df.index[0].date()} → {df.index[-1].date()}")
    df = calc_all_indicators(df)

    systems = ['E', 'H'] if args.system == 'both' else [args.system]

    for sys_name in systems:
        if sys_name == 'E':
            metrics = run_backtest_e(df)
        else:
            metrics = run_backtest_h(df)

        print(f"\n  System {sys_name} Results:")
        print(f"  {'-'*40}")
        for k, v in metrics.items():
            print(f"  {k:<20} {v:>10}")

    # Buy & hold comparison
    bh_ret = (df.iloc[-1]['close'] / df.iloc[0]['close'] - 1) * 100
    print(f"\n  Buy & Hold:        {bh_ret:>10.2f}%")
    print(f"\n{'='*60}")
