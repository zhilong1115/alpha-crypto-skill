"""Fetch data, run all 7 systems on 3 coins, output comparison."""
import ccxt
import pandas as pd
import numpy as np
import time
import os
from indicators import calc_all_indicators
from scoring import SYSTEMS
from backtest import run_backtest


def fetch_ohlcv(symbol, exchange_id='binanceus', timeframe='1d',
                start_date='2021-02-01', end_date='2026-02-01'):
    # Try multiple exchanges
    for eid in ['bybit', 'okx', 'kraken', exchange_id]:
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
        except Exception:
            continue
    else:
        raise Exception(f"No exchange available for {symbol}")
    since = exchange.parse8601(f'{start_date}T00:00:00Z')
    end_ms = exchange.parse8601(f'{end_date}T00:00:00Z')
    all_data = []
    while since < end_ms:
        data = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        if not data:
            break
        all_data.extend(data)
        since = data[-1][0] + 1
        time.sleep(0.5)
    df = pd.DataFrame(all_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    df = df[~df.index.duplicated()]
    return df


def main():
    coins = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    results = []

    for coin in coins:
        print(f"\nFetching {coin}...")
        try:
            df = fetch_ohlcv(coin)
        except Exception as e:
            print(f"  Error fetching {coin}: {e}")
            continue
        print(f"  Got {len(df)} candles from {df.index[0]} to {df.index[-1]}")

        # USDT.D not available via ccxt, using inverse BTC as proxy (noted in results)
        df = calc_all_indicators(df, usdt_d_close=None)

        for sys_name, score_fn in SYSTEMS.items():
            print(f"  Running System {sys_name}...")
            metrics = run_backtest(df, score_fn, sys_name)
            metrics['System'] = sys_name
            metrics['Coin'] = coin
            results.append(metrics)

    # Build comparison table
    rdf = pd.DataFrame(results)
    cols = ['Coin', 'System', 'Total Return %', 'Max Drawdown %', 'Sharpe', 'Win Rate %', 'Trades', 'Profit Factor', 'Calmar']
    rdf = rdf[cols]

    print("\n" + "="*120)
    print("COMPARISON TABLE: All Systems × All Coins")
    print("="*120)
    print(rdf.to_string(index=False))

    # Best system by average Calmar
    avg_calmar = rdf.groupby('System')['Calmar'].mean().sort_values(ascending=False)
    best = avg_calmar.index[0]
    print(f"\n🏆 BEST SYSTEM: {best} (avg Calmar: {avg_calmar.iloc[0]:.2f})")
    print(f"\nCalmar ranking:\n{avg_calmar.to_string()}")

    # Save results
    os.makedirs('results', exist_ok=True)
    with open('results/comparison.md', 'w') as f:
        f.write("# Crypto 4-Indicator Scoring System Backtest Results\n\n")
        f.write(f"**Date**: {pd.Timestamp.now().strftime('%Y-%m-%d')}\n")
        f.write(f"**Coins tested**: {', '.join(coins)}\n")
        f.write(f"**Period**: 2021-02-01 to 2026-02-01 (~5 years, full crypto cycle)\n")
        f.write(f"**Fee**: 0.1% per trade\n\n")
        f.write("⚠️ **Note**: USDT.D data simulated using inverse BTC price correlation (direct USDT dominance not available via ccxt).\n\n")
        f.write("## Comparison Table\n\n")
        f.write(rdf.to_markdown(index=False))
        f.write("\n\n## Rankings by Average Calmar Ratio\n\n")
        f.write("| System | Avg Calmar |\n|--------|------------|\n")
        for sys, cal in avg_calmar.items():
            marker = " 🏆" if sys == best else ""
            f.write(f"| {sys}{marker} | {cal:.2f} |\n")
        f.write(f"\n## Winner: System {best}\n\n")
        f.write(f"Average Calmar Ratio: {avg_calmar.iloc[0]:.2f}\n")

        # Add per-system descriptions
        descs = {
            'A': 'Equal Weight (25 each), buy≥75, sell≤25',
            'B': 'Layered/Hierarchical (USDT.D gate), buy≥70, sell≤20',
            'C': 'TSI-Heavy (TSI=40pts), buy≥70, sell≤20',
            'D': 'Momentum-Heavy (WT+OBV=60pts), buy≥70, sell≤20',
            'E': 'Adaptive Threshold (regime-dependent), variable thresholds',
            'F': 'Continuous Scoring (non-binary), buy≥65, sell≤25',
            'G': 'Confirmation Count with Position Sizing (graduated)',
        }
        f.write("\n## System Descriptions\n\n")
        for k, v in descs.items():
            f.write(f"- **System {k}**: {v}\n")

    print(f"\nResults saved to results/comparison.md")
    return best, avg_calmar.iloc[0], rdf


if __name__ == '__main__':
    main()
