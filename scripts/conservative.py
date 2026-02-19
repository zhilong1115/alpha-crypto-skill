#!/usr/bin/env python3
"""Conservative mode: E+G Hybrid with graduated position sizing.
SMA200 determines regime, bullish indicator count determines position size.

Dependencies: pandas, numpy, ccxt
"""
import sys
import os
import argparse
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from indicators import calc_all_indicators, _binary_signals


# Position sizing tables
BULL_SIZING = {4: 0.50, 3: 0.30, 2: 0.15, 1: 0.0, 0: 0.0}
BEAR_SIZING = {4: 0.30, 3: 0.15, 2: 0.0, 1: 0.0, 0: 0.0}


def score_conservative(row):
    """Returns (count, bull_regime, target_position_pct)."""
    s = _binary_signals(row)
    count = sum(int(v) for k, v in s.items() if k.endswith('_bull'))

    bull_regime = (row['sma200'] > row['sma200_prev']
                   if not np.isnan(row.get('sma200', np.nan)) else True)

    sizing = BULL_SIZING if bull_regime else BEAR_SIZING
    target_pos = sizing.get(count, 0.0)

    return count, bull_regime, target_pos


def get_signal(row):
    """Return (signal, count, regime, target_pct, details)."""
    s = _binary_signals(row)
    count, bull_regime, target_pos = score_conservative(row)
    regime = 'BULL' if bull_regime else 'BEAR'

    details = {
        'TSI': '✅' if s['tsi_bull'] else '❌',
        'OBV': '✅' if s['obv_bull'] else '❌',
        'USDT.D': '✅' if s['usdt_bull'] else '❌',
        'WaveTrend': '✅' if s['wt_bull'] else '❌',
    }

    if target_pos >= 0.30:
        signal = 'BUY'
    elif target_pos == 0:
        signal = 'SELL'
    else:
        signal = 'HOLD'

    return signal, count, regime, target_pos, details


def analyze_coin(symbol='BTC/USDT', timeframe='1d', exchange_id='bybit'):
    """Fetch data and return current Conservative signal."""
    import ccxt
    import time

    exchange = getattr(ccxt, exchange_id)()
    exchange.load_markets()
    if symbol not in exchange.markets:
        alt = symbol.replace('/USDT', '/USD')
        if alt in exchange.markets:
            symbol = alt

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
    signal, count, regime, target_pos, details = get_signal(last)

    return {
        'symbol': symbol,
        'timeframe': timeframe,
        'price': last['close'],
        'signal': signal,
        'bullish_count': count,
        'regime': regime,
        'target_position': f"{target_pos*100:.0f}%",
        'details': details,
        'tsi': round(last['tsi'], 2),
        'wt1': round(last['wt1'], 2),
        'date': str(df.index[-1]),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Conservative: E+G Hybrid Signals')
    parser.add_argument('--coin', default='BTC', help='Coin symbol (default: BTC)')
    parser.add_argument('--timeframe', default='1d', help='Timeframe (default: 1d)')
    parser.add_argument('--exchange', default='bybit', help='Exchange (default: bybit)')
    args = parser.parse_args()

    symbol = f"{args.coin.upper()}/USDT"
    print(f"\n📊 Conservative Analysis: {symbol} ({args.timeframe})")
    print("=" * 50)

    result = analyze_coin(symbol, args.timeframe, args.exchange)

    emoji = {'BUY': '🟢', 'SELL': '🔴', 'HOLD': '🟡'}[result['signal']]
    print(f"Price:      ${result['price']:,.2f}")
    print(f"Signal:     {emoji} {result['signal']}")
    print(f"Bullish:    {result['bullish_count']}/4")
    print(f"Regime:     {result['regime']}")
    print(f"Position:   {result['target_position']}")
    print(f"TSI:        {result['tsi']}")
    print(f"WaveTrend:  {result['wt1']}")
    print(f"\nIndicators:")
    for k, v in result['details'].items():
        print(f"  {k}: {v}")
    print(f"\nDate: {result['date']}")
