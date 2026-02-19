#!/usr/bin/env python3
"""Analyze E and H performance specifically during bear market (2021-11 to 2022-12)."""
import pandas as pd
import numpy as np
import time, ccxt
from indicators import calc_all_indicators
from scoring import score_E, _binary_signals
from backtest import run_backtest, calc_metrics
from run_hybrid import run_hybrid_backtest, score_H


def fetch_ohlcv(symbol, start='2021-02-01', end='2026-02-01'):
    for eid in ['okx', 'kraken', 'bybit']:
        try:
            exchange = getattr(ccxt, eid)()
            exchange.load_markets()
            if symbol not in exchange.markets:
                alt = symbol.replace('/USDT', '/USD')
                if alt in exchange.markets:
                    symbol = alt
            break
        except:
            continue
    since = exchange.parse8601(f'{start}T00:00:00Z')
    end_ms = exchange.parse8601(f'{end}T00:00:00Z')
    all_data = []
    while since < end_ms:
        data = exchange.fetch_ohlcv(symbol, '1d', since=since, limit=1000)
        if not data: break
        all_data.extend(data)
        since = data[-1][0] + 1
        time.sleep(0.5)
    df = pd.DataFrame(all_data, columns=['timestamp','open','high','low','close','volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    df = df[~df.index.duplicated()]
    return df


def main():
    coins = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    
    # Define market phases
    phases = {
        'Bull 2021 (Feb-Nov)':  ('2021-02-01', '2021-11-10'),
        'Bear 2022 (Nov21-Dec22)': ('2021-11-10', '2022-12-31'),
        'Recovery 2023': ('2023-01-01', '2023-12-31'),
        'Bull 2024-25': ('2024-01-01', '2026-02-01'),
        'Full 5yr': ('2021-02-01', '2026-02-01'),
    }
    
    all_results = []
    
    for coin in coins:
        print(f"\nFetching {coin}...")
        df_full = fetch_ohlcv(coin)
        df_full = calc_all_indicators(df_full, usdt_d_close=None)
        print(f"  Got {len(df_full)} candles")
        
        for phase_name, (start, end) in phases.items():
            df = df_full.loc[start:end].copy()
            if len(df) < 50:
                print(f"  {phase_name}: skipped (only {len(df)} candles)")
                continue
            
            # Buy & hold baseline
            bh_ret = (df['close'].iloc[-1] / df['close'].iloc[0] - 1) * 100
            
            # System E
            e_metrics = run_backtest(df, score_E, 'E')
            
            # System H
            h_metrics = run_hybrid_backtest(df)
            
            for sys_name, metrics in [('E', e_metrics), ('H', h_metrics), ('Buy&Hold', {'Total Return %': round(bh_ret,2), 'Max Drawdown %': 0, 'Sharpe': 0, 'Win Rate %': 0, 'Trades': 0, 'Profit Factor': 0, 'Calmar': 0})]:
                metrics['System'] = sys_name
                metrics['Coin'] = coin.split('/')[0]
                metrics['Phase'] = phase_name
                metrics['Days'] = len(df)
                all_results.append(metrics)
    
    rdf = pd.DataFrame(all_results)
    
    # Print by phase
    for phase in phases:
        sub = rdf[rdf['Phase'] == phase]
        if sub.empty: continue
        print(f"\n{'='*100}")
        print(f"  {phase}")
        print(f"{'='*100}")
        
        for coin in ['BTC', 'ETH', 'SOL']:
            coin_sub = sub[sub['Coin'] == coin]
            if coin_sub.empty: continue
            print(f"\n  {coin}:")
            for _, row in coin_sub.iterrows():
                sys = row['System']
                ret = row['Total Return %']
                dd = row['Max Drawdown %']
                sharpe = row['Sharpe']
                trades = row['Trades']
                if sys == 'Buy&Hold':
                    print(f"    {sys:10s}: Return {ret:>12,.1f}%")
                else:
                    print(f"    {sys:10s}: Return {ret:>12,.1f}% | MaxDD {dd:>6.1f}% | Sharpe {sharpe:>5.2f} | Trades {trades}")
    
    # Summary: average across coins per phase
    print(f"\n\n{'='*100}")
    print("  AVERAGE ACROSS ALL COINS")
    print(f"{'='*100}")
    for phase in phases:
        sub = rdf[rdf['Phase'] == phase]
        if sub.empty: continue
        print(f"\n  {phase}:")
        for sys in ['E', 'H', 'Buy&Hold']:
            ss = sub[sub['System'] == sys]
            if ss.empty: continue
            avg_ret = ss['Total Return %'].mean()
            avg_dd = ss['Max Drawdown %'].mean()
            avg_sharpe = ss['Sharpe'].mean()
            if sys == 'Buy&Hold':
                print(f"    {sys:10s}: Avg Return {avg_ret:>12,.1f}%")
            else:
                print(f"    {sys:10s}: Avg Return {avg_ret:>12,.1f}% | Avg MaxDD {avg_dd:>6.1f}% | Avg Sharpe {avg_sharpe:>5.2f}")


if __name__ == '__main__':
    main()
