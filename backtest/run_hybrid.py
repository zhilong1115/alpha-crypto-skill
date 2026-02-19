#!/usr/bin/env python3
"""Run E+G Hybrid backtest and compare against pure E and G."""
import ccxt
import pandas as pd
import numpy as np
import time
from indicators import calc_all_indicators
from scoring import _binary_signals, score_E, score_G, SYSTEMS
from backtest import run_backtest, calc_metrics


def score_H(row):
    """System H: E+G Hybrid — Adaptive threshold + graduated position sizing.
    
    Uses SMA200 to determine regime (like E), then counts bullish indicators
    and assigns position size (like G), with regime-adjusted sizing.
    
    Bull regime (SMA200 rising):
        4/4 bullish → 50% position
        3/4 bullish → 30% position
        2/4 bullish → 15% position
        1/4 or less → 0%
    
    Bear regime (SMA200 falling):
        4/4 bullish → 30% position
        3/4 bullish → 15% position
        2/4 or less → 0%
    """
    s = _binary_signals(row)
    count = int(s['tsi_bull']) + int(s['obv_bull']) + int(s['usdt_bull']) + int(s['wt_bull'])
    
    bull_regime = row['sma200'] > row['sma200_prev'] if not np.isnan(row.get('sma200', np.nan)) else True
    
    if bull_regime:
        sizing = {4: 0.50, 3: 0.30, 2: 0.15, 1: 0.0, 0: 0.0}
    else:
        sizing = {4: 0.30, 3: 0.15, 2: 0.0, 1: 0.0, 0: 0.0}
    
    target_pos = sizing.get(count, 0.0)
    # Return count and regime info encoded — we'll handle in custom backtest
    return count, bull_regime, target_pos


def run_hybrid_backtest(df, fee=0.001):
    """Custom backtest for System H with graduated position sizing."""
    capital = 10000.0
    position = 0.0  # current position fraction
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
            # Scale into position
            add_frac = target_pos - position
            cost = equity[-1] * add_frac * fee
            equity[-1] -= cost
            if position == 0:
                entry_price = row['close']
                current_trade = {'entry': row['close'], 'entry_idx': i}
            position = target_pos
        elif target_pos < position:
            # Scale out
            reduce_frac = position - target_pos
            if entry_price > 0:
                pnl = reduce_frac * equity[-1] * (row['close'] / entry_price - 1)
            else:
                pnl = 0
            cost = equity[-1] * reduce_frac * fee
            equity[-1] += pnl - cost
            position = target_pos
            if position == 0 and current_trade:
                ret = row['close'] / current_trade['entry'] - 1
                trades.append(ret)
                current_trade = None
        
        # Update equity with position P&L
        if position > 0 and i > 1:
            price_ret = row['close'] / df.iloc[i-1]['close'] - 1
            equity.append(equity[-1] * (1 + position * price_ret))
        else:
            equity.append(equity[-1])
    
    # Close any open position
    if position > 0 and len(df) > 1:
        ret = df.iloc[-1]['close'] / entry_price - 1
        trades.append(ret)
    
    equity = np.array(equity)
    return calc_metrics(equity, trades)


def fetch_ohlcv(symbol, start_date='2021-02-01', end_date='2026-02-01'):
    for eid in ['bybit', 'okx', 'kraken']:
        try:
            exchange = getattr(ccxt, eid)()
            exchange.load_markets()
            if symbol not in exchange.markets:
                alt = symbol.replace('/USDT', '/USD')
                if alt in exchange.markets:
                    symbol = alt
                else:
                    continue
            break
        except:
            continue
    else:
        raise Exception(f"No exchange for {symbol}")
    
    since = exchange.parse8601(f'{start_date}T00:00:00Z')
    end_ms = exchange.parse8601(f'{end_date}T00:00:00Z')
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
    all_results = []
    
    for coin in coins:
        print(f"\nFetching {coin}...")
        df = fetch_ohlcv(coin)
        print(f"  Got {len(df)} candles: {df.index[0]} → {df.index[-1]}")
        df = calc_all_indicators(df, usdt_d_close=None)
        
        # Run System E (baseline)
        print(f"  Running System E...")
        e_metrics = run_backtest(df, score_E, 'E')
        e_metrics['System'] = 'E (Adaptive)'
        e_metrics['Coin'] = coin
        all_results.append(e_metrics)
        
        # Run System G (baseline)
        print(f"  Running System G...")
        g_metrics = run_backtest(df, score_G, 'G')
        g_metrics['System'] = 'G (Sizing)'
        g_metrics['Coin'] = coin
        all_results.append(g_metrics)
        
        # Run System H (E+G Hybrid)
        print(f"  Running System H (E+G Hybrid)...")
        h_metrics = run_hybrid_backtest(df)
        h_metrics['System'] = 'H (E+G Hybrid)'
        h_metrics['Coin'] = coin
        all_results.append(h_metrics)
    
    # Display results
    rdf = pd.DataFrame(all_results)
    cols = ['Coin', 'System', 'Total Return %', 'Max Drawdown %', 'Sharpe', 'Win Rate %', 'Trades', 'Profit Factor', 'Calmar']
    rdf = rdf[cols]
    
    print("\n" + "="*120)
    print("E vs G vs H (E+G HYBRID) COMPARISON")
    print("="*120)
    print(rdf.to_string(index=False))
    
    # Average metrics per system
    print("\n\nAVERAGE METRICS ACROSS ALL COINS:")
    print("-"*80)
    for sys in ['E (Adaptive)', 'G (Sizing)', 'H (E+G Hybrid)']:
        sub = rdf[rdf['System'] == sys]
        print(f"\n  {sys}:")
        print(f"    Avg Return:     {sub['Total Return %'].mean():,.0f}%")
        print(f"    Avg Max DD:     {sub['Max Drawdown %'].mean():.1f}%")
        print(f"    Avg Sharpe:     {sub['Sharpe'].mean():.2f}")
        print(f"    Avg Win Rate:   {sub['Win Rate %'].mean():.1f}%")
        print(f"    Avg Trades:     {sub['Trades'].mean():.0f}")
        print(f"    Avg PF:         {sub['Profit Factor'].mean():.2f}")
        print(f"    Avg Calmar:     {sub['Calmar'].mean():,.0f}")
    
    # Save
    with open('results/hybrid_comparison.md', 'w') as f:
        f.write("# System H (E+G Hybrid) Backtest Results\n\n")
        f.write("## Hybrid Logic\n")
        f.write("- Uses SMA200 direction to determine bull/bear regime (from E)\n")
        f.write("- Counts bullish indicators and sizes position gradually (from G)\n\n")
        f.write("### Position Sizing:\n")
        f.write("| Regime | 4/4 Bullish | 3/4 | 2/4 | 1/4 | 0/4 |\n")
        f.write("|--------|-------------|-----|-----|-----|-----|\n")
        f.write("| Bull (SMA200↑) | 50% | 30% | 15% | 0% | 0% |\n")
        f.write("| Bear (SMA200↓) | 30% | 15% | 0% | 0% | 0% |\n\n")
        f.write("## Comparison: E vs G vs H\n\n")
        f.write(rdf.to_markdown(index=False))
        f.write("\n")
    
    print("\n✅ Results saved to results/hybrid_comparison.md")


if __name__ == '__main__':
    main()
