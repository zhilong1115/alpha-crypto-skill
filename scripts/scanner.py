#!/usr/bin/env python3
"""Scan multiple coins for trading signals using Aggressive and H.
Dependencies: ccxt, pandas, numpy
Usage:
  python scanner.py --coins BTC,ETH,SOL
  python scanner.py --coin BTC --timeframe 1d
  python scanner.py --coins BTC,ETH,SOL --system H
"""
import sys
import os
import argparse
import time

sys.path.insert(0, os.path.dirname(__file__))


def scan(coins, timeframe='1d', system='E', exchange_id='bybit'):
    if system == 'E':
        from aggressive import analyze_coin
    else:
        from conservative import analyze_coin

    results = []
    for coin in coins:
        symbol = f"{coin.upper()}/USDT"
        try:
            print(f"  Scanning {symbol}...", end=' ', flush=True)
            result = analyze_coin(symbol, timeframe, exchange_id)
            results.append(result)
            print(f"{'🟢' if result['signal']=='BUY' else '🔴' if result['signal']=='SELL' else '🟡'} {result['signal']}")
            time.sleep(0.5)
        except Exception as e:
            print(f"❌ Error: {e}")
            results.append({'symbol': symbol, 'signal': 'ERROR', 'error': str(e)})
    return results


def print_results(results, system):
    print(f"\n{'='*70}")
    print(f"  CRYPTO SCANNER — System {system}")
    print(f"{'='*70}")

    for r in results:
        if r.get('error'):
            print(f"  {r['symbol']:<12} ❌ {r['error']}")
            continue

        emoji = {'BUY': '🟢', 'SELL': '🔴', 'HOLD': '🟡'}.get(r['signal'], '❓')
        price = f"${r['price']:,.2f}"

        if system == 'E':
            score_str = f"Score: {r['score']}/100"
        else:
            score_str = f"Bullish: {r['bullish_count']}/4 → {r['target_position']}"

        indicators = ' '.join(f"{k}:{v}" for k, v in r['details'].items())

        print(f"\n  {r['symbol']:<12} {emoji} {r['signal']:<5} {price:>12}")
        print(f"  {'':12} {r['regime']} | {score_str}")
        print(f"  {'':12} {indicators}")

    print(f"\n{'='*70}")

    buys = [r for r in results if r.get('signal') == 'BUY']
    if buys:
        print(f"\n  🟢 BUY signals: {', '.join(r['symbol'] for r in buys)}")
    sells = [r for r in results if r.get('signal') == 'SELL']
    if sells:
        print(f"  🔴 SELL signals: {', '.join(r['symbol'] for r in sells)}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Crypto Signal Scanner')
    parser.add_argument('--coins', default='BTC,ETH,SOL', help='Comma-separated coins')
    parser.add_argument('--coin', help='Single coin to scan')
    parser.add_argument('--timeframe', default='1d', help='Timeframe (default: 1d)')
    parser.add_argument('--system', default='aggressive', choices=['aggressive', 'conservative'], help='Aggressive or H')
    parser.add_argument('--exchange', default='bybit', help='Exchange (default: bybit)')
    args = parser.parse_args()

    coins = [args.coin] if args.coin else args.coins.split(',')
    print(f"\n🔍 Scanning {len(coins)} coin(s) with System {args.system}...")

    results = scan(coins, args.timeframe, args.system, args.exchange)
    print_results(results, args.system)
