#!/usr/bin/env python3
"""Backtest TSI threshold comparison: tsi<0 vs tsi<-25 vs tsi<-40"""
import sys, os
import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from indicators import calc_all_indicators

def fetch_data(ticker, start='2023-01-01'):
    df = yf.download(ticker, start=start, auto_adjust=True, progress=False)
    df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]
    df = df[['open','high','low','close','volume']].copy()
    df.index = pd.to_datetime(df.index)
    # Remove timezone
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    return df

def score_with_threshold(row, tsi_threshold):
    tsi_bull = row['tsi'] < tsi_threshold and row['tsi'] > row['tsi_prev']
    obv_bull = row['obv'] > row['obv_ema9']
    usdt_bull = row['usdt_d_tsi'] < row['usdt_d_tsi_prev']
    wt_bull = row['wt1'] > row['wt2']
    score = (int(tsi_bull)*25 + int(obv_bull)*25 + int(usdt_bull)*25 + int(wt_bull)*25)
    bull_regime = (row['sma200'] > row['sma200_prev'] if not np.isnan(row.get('sma200', np.nan)) else True)
    return (score, 50, 25) if bull_regime else (score, 75, 50)

def run_backtest(df, tsi_threshold, initial=1000.0, fee=0.001):
    capital = initial
    position = 0.0
    entry_price = 0.0
    equity = [capital]
    trades = []
    buy_dates = []
    
    for i in range(1, len(df)):
        row = df.iloc[i]
        if any(np.isnan(row.get(c, np.nan)) for c in ['tsi','obv_ema9','wt1','wt2','usdt_d_tsi']):
            equity.append(equity[-1])
            continue
        score, buy_thresh, sell_thresh = score_with_threshold(row, tsi_threshold)
        if position == 0 and score >= buy_thresh:
            position = 1.0
            entry_price = row['close']
            equity[-1] = equity[-1] * (1 - fee)
            buy_dates.append(df.index[i].strftime('%m/%d'))
        elif position > 0 and score <= sell_thresh:
            ret = row['close'] / entry_price - 1
            trades.append(ret)
            equity[-1] = equity[-1] * (1 - fee)
            position = 0
        if position > 0:
            price_ret = row['close'] / df.iloc[i-1]['close'] - 1
            equity.append(equity[-1] * (1 + price_ret))
        else:
            equity.append(equity[-1])
    
    if position > 0:
        ret = df.iloc[-1]['close'] / entry_price - 1
        trades.append(ret)
    
    equity = np.array(equity)
    total_return = (equity[-1] / equity[0] - 1) * 100
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    max_dd = abs(dd.min()) * 100
    wins = sum(1 for t in trades if t > 0)
    win_rate = (wins / len(trades) * 100) if trades else 0
    
    return {
        'trades': len(trades), 'total_return': round(total_return, 1),
        'max_dd': round(max_dd, 1), 'win_rate': round(win_rate, 0),
        'buy_dates': buy_dates, 'final_equity': round(equity[-1], 2),
    }

coins = {'BTC': 'BTC-USD', 'ETH': 'ETH-USD', 'SOL': 'SOL-USD'}
thresholds = [('V1(tsi<0)', 0), ('V2(tsi<-25)', -25), ('V3(tsi<-40)', -40)]

results = {}
tsi_current = {}
for name, ticker in coins.items():
    print(f"Fetching {name}...")
    df = fetch_data(ticker)
    df = calc_all_indicators(df)
    df_bt = df[df.index >= '2024-01-01']
    last = df.iloc[-1]
    tsi_current[name] = (last['tsi'], last['tsi_prev'])
    print(f"  {len(df_bt)} days | TSI now: {last['tsi']:.1f} (prev {last['tsi_prev']:.1f})")
    
    for vname, thresh in thresholds:
        r = run_backtest(df_bt, thresh)
        results[f"{name}_{vname}"] = r
        buys = ', '.join(r['buy_dates'][:6])
        print(f"  {vname}: {r['trades']}T {r['total_return']}% ret {r['max_dd']}% DD {r['win_rate']}% WR | buys: {buys}")

# Print summary table
print("\n=== PER COIN ===")
for name in coins:
    print(f"\n{name}:")
    for vname, _ in thresholds:
        r = results[f"{name}_{vname}"]
        print(f"  {vname}: {r['trades']}T | ${r['final_equity']} | {r['total_return']}% | DD {r['max_dd']}% | WR {r['win_rate']}%")

print("\n=== AGGREGATE ===")
for vname, thresh in thresholds:
    total_trades = sum(results[f"{c}_{vname}"]['trades'] for c in coins)
    avg_return = np.mean([results[f"{c}_{vname}"]['total_return'] for c in coins])
    avg_dd = np.mean([results[f"{c}_{vname}"]['max_dd'] for c in coins])
    avg_wr = np.mean([results[f"{c}_{vname}"]['win_rate'] for c in coins])
    print(f"{vname}: {total_trades}T | avg {avg_return:.1f}% | DD {avg_dd:.1f}% | WR {avg_wr:.0f}%")
