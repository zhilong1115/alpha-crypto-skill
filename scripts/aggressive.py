#!/usr/bin/env python3
"""Aggressive mode: Adaptive Threshold scoring.
Equal weight 25pts each for TSI, OBV, USDT.D, WaveTrend.
Thresholds adapt based on SMA200 direction (bull/bear regime).

Dependencies: pandas, numpy, ccxt
"""
import sys
import os
import argparse
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from indicators import calc_all_indicators, _binary_signals


def score_aggressive(row):
    """Score 0-100. Returns (score, buy_threshold, sell_threshold)."""
    s = _binary_signals(row)
    score = (int(s['tsi_bull']) * 25 + int(s['obv_bull']) * 25 +
             int(s['usdt_bull']) * 25 + int(s['wt_bull']) * 25)

    bull_regime = (row['sma200'] > row['sma200_prev']
                   if not np.isnan(row.get('sma200', np.nan)) else True)
    if bull_regime:
        return score, 50, 25  # Buy >= 50, Sell <= 25
    else:
        return score, 75, 50  # Buy >= 75, Sell <= 50


def get_signal(row):
    """Return (signal, score, regime, details)."""
    score, buy_thresh, sell_thresh = score_aggressive(row)
    s = _binary_signals(row)
    regime = 'BULL' if buy_thresh == 50 else 'BEAR'

    details = {
        'TSI': '✅' if s['tsi_bull'] else '❌',
        'OBV': '✅' if s['obv_bull'] else '❌',
        'USDT.D': '✅' if s['usdt_bull'] else '❌',
        'WaveTrend': '✅' if s['wt_bull'] else '❌',
    }

    if score >= buy_thresh:
        signal = 'BUY'
    elif score <= sell_thresh:
        signal = 'SELL'
    else:
        signal = 'HOLD'

    return signal, score, regime, details


def analyze_coin(symbol='BTC/USDT', timeframe='1d', exchange_id='bybit'):
    """Fetch data and return current Aggressive signal."""
    import ccxt
    import time

    exchange = getattr(ccxt, exchange_id)()
    exchange.load_markets()

    if symbol not in exchange.markets:
        alt = symbol.replace('/USDT', '/USD')
        if alt in exchange.markets:
            symbol = alt

    # Fetch enough data for SMA200
    all_data = []
    since = exchange.parse8601('2024-01-01T00:00:00Z')
    while True:
        data = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        if not data:
            break
        all_data.extend(data)
        since = data[-1][0] + 1
        time.sleep(0.3)
        if len(all_data) > 2000:
            break

    df = pd.DataFrame(all_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    df = df[~df.index.duplicated()]
    df = calc_all_indicators(df)

    last = df.iloc[-1]
    signal, score, regime, details = get_signal(last)

    return {
        'symbol': symbol,
        'timeframe': timeframe,
        'price': last['close'],
        'signal': signal,
        'score': score,
        'regime': regime,
        'details': details,
        'tsi': round(last['tsi'], 2),
        'wt1': round(last['wt1'], 2),
        'mayer': round(last['mayer'], 3) if not np.isnan(last.get('mayer', np.nan)) else None,
        'date': str(df.index[-1]),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Aggressive: Adaptive Threshold Signals')
    parser.add_argument('--coin', default='BTC', help='Coin symbol (default: BTC)')
    parser.add_argument('--timeframe', default='1d', help='Timeframe (default: 1d)')
    parser.add_argument('--exchange', default='bybit', help='Exchange (default: bybit)')
    args = parser.parse_args()

    symbol = f"{args.coin.upper()}/USDT"
    print(f"\n📊 Aggressive Analysis: {symbol} ({args.timeframe})")
    print("=" * 50)

    result = analyze_coin(symbol, args.timeframe, args.exchange)

    emoji = {'BUY': '🟢', 'SELL': '🔴', 'HOLD': '🟡'}[result['signal']]
    print(f"Price:     ${result['price']:,.2f}")
    print(f"Signal:    {emoji} {result['signal']}")
    print(f"Score:     {result['score']}/100")
    print(f"Regime:    {result['regime']}")
    print(f"TSI:       {result['tsi']}")
    print(f"WaveTrend: {result['wt1']}")
    if result['mayer']:
        print(f"Mayer:     {result['mayer']}")
    print(f"\nIndicators:")
    for k, v in result['details'].items():
        print(f"  {k}: {v}")
    print(f"\nDate: {result['date']}")
