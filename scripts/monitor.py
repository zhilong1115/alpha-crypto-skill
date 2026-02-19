#!/usr/bin/env python3
"""Monitor open positions — check stop-loss, MA120, and current signals.
Dependencies: ccxt, pandas, numpy
Usage:
  python monitor.py --positions BTC:50000,ETH:3000
  python monitor.py --positions BTC:95000 --exchange bybit
"""
import sys
import os
import argparse
import time
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from indicators import calc_all_indicators, sma
from aggressive import get_signal as get_signal_agg
from conservative import get_signal as get_signal_con


def fetch_recent(symbol, exchange_id='bybit', bars=200):
    import ccxt
    exchange = getattr(ccxt, exchange_id)()
    exchange.load_markets()
    if symbol not in exchange.markets:
        alt = symbol.replace('/USDT', '/USD')
        if alt in exchange.markets:
            symbol = alt

    data = exchange.fetch_ohlcv(symbol, '4h', limit=bars)
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    return df


def check_position(coin, entry_price, exchange_id='bybit'):
    symbol = f"{coin.upper()}/USDT"

    # Fetch 4H data for MA120 check
    df_4h = fetch_recent(symbol, exchange_id, bars=200)
    ma120_4h = sma(df_4h['close'], 120).iloc[-1]
    current_price = df_4h.iloc[-1]['close']
    pnl_pct = (current_price / entry_price - 1) * 100

    # Fetch daily for signals
    import ccxt
    exchange = getattr(ccxt, exchange_id)()
    exchange.load_markets()
    if symbol not in exchange.markets:
        symbol = symbol.replace('/USDT', '/USD')

    all_data = []
    since = exchange.parse8601('2024-06-01T00:00:00Z')
    while True:
        data = exchange.fetch_ohlcv(symbol, '1d', since=since, limit=1000)
        if not data:
            break
        all_data.extend(data)
        since = data[-1][0] + 1
        time.sleep(0.3)
        if len(data) < 1000:
            break

    df_daily = pd.DataFrame(all_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df_daily['timestamp'] = pd.to_datetime(df_daily['timestamp'], unit='ms')
    df_daily.set_index('timestamp', inplace=True)
    df_daily = df_daily[~df_daily.index.duplicated()]
    df_daily = calc_all_indicators(df_daily)

    last = df_daily.iloc[-1]
    sig_e, score_agg, regime_e, details_e = get_signal_agg(last)
    sig_h, count_h, regime_h, target_con, details_h = get_signal_con(last)

    # Alerts
    alerts = []
    stop_loss_price = entry_price * 0.95
    if current_price <= stop_loss_price:
        alerts.append('🚨 5% STOP-LOSS HIT')
    if not np.isnan(ma120_4h) and current_price < ma120_4h:
        alerts.append('🚨 BELOW 4H MA120 — EXIT NOW')
    if pnl_pct < -3:
        alerts.append('⚠️ Position down >3%')
    if sig_e == 'SELL':
        alerts.append('⚠️ Aggressive says SELL')

    return {
        'symbol': symbol,
        'entry': entry_price,
        'current': current_price,
        'pnl_pct': pnl_pct,
        'ma120_4h': ma120_4h,
        'above_ma120': current_price > ma120_4h if not np.isnan(ma120_4h) else None,
        'stop_loss': stop_loss_price,
        'signal_agg': sig_e,
        'score_agg': score_agg,
        'signal_con': sig_h,
        'target_con': target_con,
        'alerts': alerts,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Position Monitor')
    parser.add_argument('--positions', required=True, help='Positions as COIN:ENTRY_PRICE,...')
    parser.add_argument('--exchange', default='bybit')
    args = parser.parse_args()

    positions = []
    for p in args.positions.split(','):
        coin, entry = p.split(':')
        positions.append((coin.strip(), float(entry)))

    print(f"\n🔔 Position Monitor")
    print("=" * 60)

    for coin, entry in positions:
        print(f"\n  Checking {coin}...", flush=True)
        try:
            r = check_position(coin, entry, args.exchange)
            pnl_emoji = '🟢' if r['pnl_pct'] >= 0 else '🔴'
            print(f"\n  {r['symbol']}")
            print(f"  Entry:      ${r['entry']:,.2f}")
            print(f"  Current:    ${r['current']:,.2f}")
            print(f"  P&L:        {pnl_emoji} {r['pnl_pct']:+.2f}%")
            print(f"  Stop-Loss:  ${r['stop_loss']:,.2f}")
            print(f"  4H MA120:   ${r['ma120_4h']:,.2f} ({'✅ Above' if r['above_ma120'] else '❌ Below'})")
            print(f"  Aggressive:   {r['signal_agg']} (Score: {r['score_agg']})")
            print(f"  Conservative:   {r['signal_con']} (Target: {r['target_con']*100:.0f}%)")

            if r['alerts']:
                print(f"\n  {'!'*40}")
                for a in r['alerts']:
                    print(f"  {a}")
                print(f"  {'!'*40}")
        except Exception as e:
            print(f"  ❌ Error: {e}")

    print(f"\n{'='*60}")
