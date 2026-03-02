#!/usr/bin/env python3
"""5-year backtest comparing TSI threshold V1/V2/V3 for Aggressive strategy."""
import sys, os, time, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from indicators import calc_all_indicators

# TSI threshold versions
TSI_VERSIONS = {
    'V1': 0,    # tsi < 0
    'V2': -25,  # tsi < -25
    'V3': -40,  # tsi < -40
}

def binary_signals_with_threshold(row, tsi_threshold=0):
    tsi_bull = row['tsi'] < tsi_threshold and row['tsi'] > row['tsi_prev']
    tsi_bear = row['tsi'] > 0 and row['tsi'] < row['tsi_prev']
    obv_bull = row['obv'] > row['obv_ema9']
    obv_bear = row['obv'] < row['obv_ema9']
    usdt_bull = row['usdt_d_tsi'] < row['usdt_d_tsi_prev']
    usdt_bear = row['usdt_d_tsi'] > row['usdt_d_tsi_prev']
    wt_bull = row['wt1'] > row['wt2']
    wt_bear = row['wt1'] < row['wt2']
    return {
        'tsi_bull': tsi_bull, 'tsi_bear': tsi_bear,
        'obv_bull': obv_bull, 'obv_bear': obv_bear,
        'usdt_bull': usdt_bull, 'usdt_bear': usdt_bear,
        'wt_bull': wt_bull, 'wt_bear': wt_bear,
    }

def score_aggressive_v(row, tsi_threshold=0):
    s = binary_signals_with_threshold(row, tsi_threshold)
    score = (int(s['tsi_bull'])*25 + int(s['obv_bull'])*25 +
             int(s['usdt_bull'])*25 + int(s['wt_bull'])*25)
    bull_regime = row['sma200'] > row['sma200_prev'] if not np.isnan(row.get('sma200', np.nan)) else True
    if bull_regime:
        return score, 50, 25
    else:
        return score, 75, 50

def fetch_ohlcv(symbol, start='2020-01-01', end='2025-01-01'):
    import ccxt
    # Try multiple exchanges
    for ex_id in ['binance', 'okx', 'bybit']:
        try:
            exchange = getattr(ccxt, ex_id)()
            exchange.load_markets()
            if symbol in exchange.markets:
                print(f"  Using {ex_id} for {symbol}")
                break
        except Exception as e:
            print(f"  {ex_id} failed: {e}")
            continue
    
    all_data = []
    since = exchange.parse8601(f'{start}T00:00:00Z')
    end_ts = exchange.parse8601(f'{end}T00:00:00Z')
    
    while since < end_ts:
        try:
            data = exchange.fetch_ohlcv(symbol, '1d', since=since, limit=1000)
        except Exception as e:
            print(f"  Error fetching {symbol}: {e}")
            break
        if not data:
            break
        all_data.extend(data)
        since = data[-1][0] + 86400000
        time.sleep(0.3)
    
    df = pd.DataFrame(all_data, columns=['timestamp','open','high','low','close','volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    df = df[~df.index.duplicated()]
    df = df[df.index < end]
    print(f"  {symbol}: {len(df)} days, {df.index[0].date()} to {df.index[-1].date()}")
    return df

def run_backtest(df, tsi_threshold, initial=1000):
    capital = initial
    position = 0.0
    entry_price = 0.0
    equity = [capital]
    trades = []

    for i in range(1, len(df)):
        row = df.iloc[i]
        if any(np.isnan(row.get(c, np.nan)) for c in ['tsi','obv_ema9','wt1','wt2','usdt_d_tsi']):
            equity.append(equity[-1])
            continue

        score, buy_thresh, sell_thresh = score_aggressive_v(row, tsi_threshold)

        if position == 0 and score >= buy_thresh:
            position = 1.0
            entry_price = row['close']
        elif position > 0 and score <= sell_thresh:
            ret = row['close'] / entry_price - 1
            trades.append({'ret': ret, 'date': df.index[i]})
            position = 0

        if position > 0 and i > 1:
            price_ret = row['close'] / df.iloc[i-1]['close'] - 1
            equity.append(equity[-1] * (1 + price_ret))
        else:
            equity.append(equity[-1])

    # Close open position
    if position > 0:
        ret = df.iloc[-1]['close'] / entry_price - 1
        trades.append({'ret': ret, 'date': df.index[-1]})

    equity = np.array(equity)
    return equity, trades

def calc_metrics(equity, trades, years=5):
    total_ret = (equity[-1]/equity[0] - 1) * 100
    ann_ret = ((equity[-1]/equity[0]) ** (1/years) - 1) * 100
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    max_dd = abs(dd.min()) * 100
    daily_ret = np.diff(equity) / equity[:-1]
    sharpe = np.sqrt(365) * np.nanmean(daily_ret) / (np.nanstd(daily_ret) + 1e-10)
    win_rate = sum(1 for t in trades if t['ret']>0)/len(trades)*100 if trades else 0
    return {
        'total_ret': round(total_ret, 1),
        'ann_ret': round(ann_ret, 1),
        'max_dd': round(max_dd, 1),
        'sharpe': round(sharpe, 2),
        'trades': len(trades),
        'win_rate': round(win_rate, 1),
    }

def yearly_backtest(df_full, tsi_threshold, initial=1000):
    """Run backtest per year."""
    results = {}
    for year in range(2020, 2025):
        start = f'{year}-01-01'
        end = f'{year+1}-01-01'
        df_year = df_full[(df_full.index >= start) & (df_full.index < end)]
        if len(df_year) < 50:
            results[year] = None
            continue
        eq, trades = run_backtest(df_year, tsi_threshold, initial)
        ret = round((eq[-1]/eq[0]-1)*100, 1)
        results[year] = ret
    return results

def bnh_return(df):
    return round((df.iloc[-1]['close']/df.iloc[0]['close']-1)*100, 1)

def main():
    coins = {'BTC': 'BTC/USDT', 'ETH': 'ETH/USDT', 'SOL': 'SOL/USDT'}
    
    # Fetch data
    print("Fetching 5-year data...")
    dfs = {}
    for name, sym in coins.items():
        dfs[name] = fetch_ohlcv(sym)
    
    # Calculate indicators
    print("\nCalculating indicators...")
    for name in dfs:
        dfs[name] = calc_all_indicators(dfs[name])
    
    # Run backtests
    print("\nRunning backtests...")
    results = {}
    yearly = {}
    
    for name in dfs:
        df = dfs[name]
        n_years = (df.index[-1] - df.index[0]).days / 365.25
        bh = bnh_return(df)
        results[name] = {'bnh': bh}
        yearly[name] = {}
        
        for vname, thresh in TSI_VERSIONS.items():
            eq, trades = run_backtest(df, thresh)
            m = calc_metrics(eq, trades, n_years)
            results[name][vname] = m
            yearly[name][vname] = yearly_backtest(df, thresh)
            print(f"  {name} {vname}: {m['total_ret']}% (B&H: {bh}%)")
    
    # Format report
    report = "📊 *5年回测报告 (2020-2025)*\n"
    report += "_Aggressive模式 TSI阈值对比_\n\n"
    
    for name in ['BTC', 'ETH', 'SOL']:
        if name not in results:
            continue
        r = results[name]
        bh = r['bnh']
        report += f"*{name} - 5年对比：*\n"
        report += "```\n"
        report += f"{'版本':<4} {'总收益':>8} {'年化':>7} {'回撤':>7} {'夏普':>6} {'胜率':>6} {'交易':>4} {'vsB&H':>8}\n"
        for v in ['V1','V2','V3']:
            m = r[v]
            vs = round(m['total_ret'] - bh, 1)
            sign = '+' if vs >= 0 else ''
            report += f"{v:<4} {m['total_ret']:>7}% {m['ann_ret']:>6}% {m['max_dd']:>6}% {m['sharpe']:>6} {m['win_rate']:>5}% {m['trades']:>4} {sign}{vs:>6}%\n"
        report += f"B&H  {bh:>7}%\n"
        report += "```\n\n"
    
    # Yearly BTC breakdown
    report += "*按年份BTC表现 (收益率%):*\n"
    report += "```\n"
    report += f"{'年份':<5} {'V1':>7} {'V2':>7} {'V3':>7} {'B&H':>7}  市场\n"
    
    market_labels = {2020: '🐂牛', 2021: '🐂牛', 2022: '🐻熊', 2023: '🔄复苏', 2024: '🐂牛'}
    
    for year in range(2020, 2025):
        df_y = dfs['BTC'][(dfs['BTC'].index >= f'{year}-01-01') & (dfs['BTC'].index < f'{year+1}-01-01')]
        bh_y = bnh_return(df_y) if len(df_y) > 10 else 'N/A'
        vals = []
        for v in ['V1','V2','V3']:
            val = yearly['BTC'][v].get(year)
            vals.append(f"{val:>6}%" if val is not None else "    N/A")
        label = market_labels.get(year, '')
        report += f"{year:<5} {vals[0]} {vals[1]} {vals[2]} {bh_y:>6}%  {label}\n"
    report += "```\n\n"
    
    # Yearly ETH
    report += "*按年份ETH表现 (收益率%):*\n"
    report += "```\n"
    report += f"{'年份':<5} {'V1':>7} {'V2':>7} {'V3':>7} {'B&H':>7}\n"
    for year in range(2020, 2025):
        df_y = dfs['ETH'][(dfs['ETH'].index >= f'{year}-01-01') & (dfs['ETH'].index < f'{year+1}-01-01')]
        bh_y = bnh_return(df_y) if len(df_y) > 10 else 'N/A'
        vals = []
        for v in ['V1','V2','V3']:
            val = yearly['ETH'][v].get(year)
            vals.append(f"{val:>6}%" if val is not None else "    N/A")
        report += f"{year:<5} {vals[0]} {vals[1]} {vals[2]} {bh_y:>6}%\n"
    report += "```\n\n"
    
    # Conclusion
    # Find best overall
    best_btc = max(['V1','V2','V3'], key=lambda v: results['BTC'][v]['total_ret'])
    best_eth = max(['V1','V2','V3'], key=lambda v: results['ETH'][v]['total_ret'])
    best_sharpe = max(['V1','V2','V3'], key=lambda v: results['BTC'][v]['sharpe'])
    
    # Bear market (2022) best
    bear_best = max(['V1','V2','V3'], key=lambda v: yearly['BTC'][v].get(2022, -999))
    # Bull market (2021) best  
    bull_best = max(['V1','V2','V3'], key=lambda v: yearly['BTC'][v].get(2021, -999))
    
    report += "*结论：*\n"
    report += f"• BTC 5年总收益最优: *{best_btc}* ({results['BTC'][best_btc]['total_ret']}%)\n"
    report += f"• ETH 5年总收益最优: *{best_eth}* ({results['ETH'][best_eth]['total_ret']}%)\n"
    report += f"• BTC 风险调整最优(夏普): *{best_sharpe}* ({results['BTC'][best_sharpe]['sharpe']})\n"
    report += f"• 牛市(2021)最优: *{bull_best}* ({yearly['BTC'][bull_best].get(2021)}%)\n"
    report += f"• 熊市(2022)最优: *{bear_best}* ({yearly['BTC'][bear_best].get(2022)}%)\n\n"
    report += "_V1: tsi<0 | V2: tsi<-25 | V3: tsi<-40_\n"
    report += "_无手续费，全仓单币种，初始$1000_"
    
    print("\n" + report)
    
    # Save report
    with open(os.path.join(os.path.dirname(__file__), 'report_5yr.txt'), 'w') as f:
        f.write(report)
    
    print("\nReport saved to report_5yr.txt")

if __name__ == '__main__':
    main()
