#!/usr/bin/env python3
"""4H短线策略V3回测 — 网格搜索 + 分批止盈 + 最长持仓 + 反过拟合
V3改进:
1. TP从5x→3.5x ATR, 加分批止盈(2x ATR平半仓)
2. ADX阈值从25→22
3. 最长持仓20根4H(80h)
4. 参数网格搜索 + 训练/验证集分离
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ccxt
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from short_term_indicators import add_all_indicators, calc_ema
from itertools import product
import time
import json

# ── 固定参数 ──
FEE_RATE = 0.0006
SLIPPAGE = 0.0005
LEVERAGE = 3
MAX_MARGIN_PCT = 0.15
INITIAL_CAPITAL = 10000
COOLDOWN_BARS = 2
VOL_MULT = 1.2
TRAIL_TRIGGER_ATR = 2.0
TRAIL_ATR_MULT = 1.5
MAX_HOLD_BARS = 20  # 最长持仓20根4H K线


def fetch_historical(symbol: str, days: int = 210) -> pd.DataFrame:
    exchange = ccxt.bybit({'enableRateLimit': True})
    all_data = []
    since = exchange.parse8601((datetime.utcnow() - timedelta(days=days)).isoformat())
    while True:
        batch = exchange.fetch_ohlcv(symbol, '4h', since=since, limit=1000)
        if not batch:
            break
        all_data.extend(batch)
        since = batch[-1][0] + 1
        if len(batch) < 1000:
            break
        time.sleep(0.3)
    df = pd.DataFrame(all_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    df = df[~df.index.duplicated(keep='first')]
    return df


def fetch_daily(symbol: str, days: int = 260) -> pd.DataFrame:
    exchange = ccxt.bybit({'enableRateLimit': True})
    all_data = []
    since = exchange.parse8601((datetime.utcnow() - timedelta(days=days)).isoformat())
    while True:
        batch = exchange.fetch_ohlcv(symbol, '1d', since=since, limit=1000)
        if not batch:
            break
        all_data.extend(batch)
        since = batch[-1][0] + 1
        if len(batch) < 1000:
            break
        time.sleep(0.3)
    df = pd.DataFrame(all_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    df = df[~df.index.duplicated(keep='first')]
    return df


def add_daily_ema50_to_4h(df_4h, df_daily):
    df_daily = df_daily.copy()
    df_daily['daily_ema50'] = calc_ema(df_daily['close'], 50)
    daily_ema = df_daily['daily_ema50'].reindex(df_4h.index, method='ffill')
    df_4h['daily_ema50'] = daily_ema
    daily_ema50_dir = df_daily['daily_ema50'].diff(5)
    daily_dir = daily_ema50_dir.reindex(df_4h.index, method='ffill')
    df_4h['daily_ema50_up'] = daily_dir > 0
    return df_4h


def classify_regime(df):
    sma50 = df['close'].rolling(50).mean()
    sma50_slope = sma50.pct_change(12)
    regime = pd.Series('range', index=df.index)
    regime[sma50_slope > 0.02] = 'bull'
    regime[sma50_slope < -0.02] = 'bear'
    return regime


def add_indicators_with_ema(df, ema_fast_span, ema_slow_span):
    """添加指标，支持自定义EMA参数"""
    df = df.copy()
    # 基础指标
    from short_term_indicators import calc_rsi, calc_atr, calc_adx, detect_ema_cross
    df['ema_fast'] = calc_ema(df['close'], ema_fast_span)
    df['ema_slow'] = calc_ema(df['close'], ema_slow_span)
    df['ema50'] = calc_ema(df['close'], 50)
    df['rsi'] = calc_rsi(df['close'], 14)
    df['atr'] = calc_atr(df, 14)
    df['adx'] = calc_adx(df, 14)
    df['cross'] = detect_ema_cross(df['ema_fast'], df['ema_slow'])
    df['vol_sma20'] = df['volume'].rolling(20).mean()
    df['regime'] = classify_regime(df)
    return df


def run_single_backtest(df, symbol, sl_atr, tp_atr, adx_min,
                        start_idx=50, end_idx=None, partial_tp=True):
    """V3单次回测，支持分批止盈+最长持仓"""
    if end_idx is None:
        end_idx = len(df)

    capital = INITIAL_CAPITAL
    peak_capital = capital
    max_drawdown = 0
    trades = []
    position = None
    last_cross_bar = -999

    for i in range(start_idx, end_idx):
        row = df.iloc[i]
        price = row['close']

        if row['cross'] in ('golden_cross', 'death_cross'):
            last_cross_bar = i

        # ── 持仓管理 ──
        if position:
            atr_now = row['atr']
            bars_held = i - position['entry_idx']

            # Trailing stop更新
            if position['side'] == 'long':
                unrealized = row['high'] - position['entry']
                if unrealized >= TRAIL_TRIGGER_ATR * position['entry_atr']:
                    new_trail = row['high'] - TRAIL_ATR_MULT * atr_now
                    position['sl'] = max(position['sl'], new_trail)
            else:
                unrealized = position['entry'] - row['low']
                if unrealized >= TRAIL_TRIGGER_ATR * position['entry_atr']:
                    new_trail = row['low'] + TRAIL_ATR_MULT * atr_now
                    position['sl'] = min(position['sl'], new_trail)

            # 分批止盈: 盈利达到2x ATR时平半仓
            if partial_tp and not position.get('partial_taken', False):
                partial_target = 2.0 * position['entry_atr']
                if position['side'] == 'long' and row['high'] >= position['entry'] + partial_target:
                    partial_exit = position['entry'] + partial_target
                    slip = partial_exit * SLIPPAGE
                    partial_exit -= slip
                    pnl_pct = (partial_exit / position['entry']) - 1 - FEE_RATE
                    half_margin = position['margin'] / 2
                    pnl = half_margin * LEVERAGE * pnl_pct
                    capital += pnl + half_margin  # 返还半仓保证金
                    position['margin'] = half_margin
                    position['partial_taken'] = True
                    position['partial_pnl'] = pnl
                elif position['side'] == 'short' and row['low'] <= position['entry'] - partial_target:
                    partial_exit = position['entry'] - partial_target
                    slip = partial_exit * SLIPPAGE
                    partial_exit += slip
                    pnl_pct = 1 - (partial_exit / position['entry']) - FEE_RATE
                    half_margin = position['margin'] / 2
                    pnl = half_margin * LEVERAGE * pnl_pct
                    capital += pnl + half_margin
                    position['margin'] = half_margin
                    position['partial_taken'] = True
                    position['partial_pnl'] = pnl

            # 止损止盈检查
            hit_sl = (position['side'] == 'long' and row['low'] <= position['sl']) or \
                     (position['side'] == 'short' and row['high'] >= position['sl'])
            hit_tp = (position['side'] == 'long' and row['high'] >= position['tp']) or \
                     (position['side'] == 'short' and row['low'] <= position['tp'])
            reverse = (position['side'] == 'long' and row['cross'] == 'death_cross') or \
                      (position['side'] == 'short' and row['cross'] == 'golden_cross')
            timeout = bars_held >= MAX_HOLD_BARS

            if hit_sl or hit_tp or reverse or timeout:
                if hit_tp:
                    exit_price = position['tp']
                    reason = 'tp'
                elif hit_sl:
                    exit_price = position['sl']
                    reason = 'sl'
                elif timeout:
                    exit_price = price
                    reason = 'timeout'
                else:
                    exit_price = price
                    reason = 'reverse'

                slip = exit_price * SLIPPAGE
                if position['side'] == 'long':
                    exit_price -= slip
                    pnl_pct = (exit_price / position['entry']) - 1
                else:
                    exit_price += slip
                    pnl_pct = 1 - (exit_price / position['entry'])

                pnl_pct -= FEE_RATE
                remaining_margin = position['margin']
                pnl = remaining_margin * LEVERAGE * pnl_pct
                capital += pnl + remaining_margin  # 返还剩余保证金

                total_pnl = pnl + position.get('partial_pnl', 0)
                original_margin = INITIAL_CAPITAL * MAX_MARGIN_PCT  # approximate

                trades.append({
                    'symbol': symbol,
                    'side': position['side'],
                    'entry': position['entry'],
                    'exit': exit_price,
                    'pnl': total_pnl,
                    'pnl_pct': total_pnl / (original_margin * LEVERAGE) * 100,
                    'reason': reason,
                    'bars_held': bars_held,
                    'partial_taken': position.get('partial_taken', False),
                    'entry_time': df.index[position['entry_idx']],
                    'exit_time': df.index[i],
                })
                position = None

        # ── 开仓信号 ──
        if position is None:
            cross = row['cross']
            rsi = row['rsi']
            adx = row['adx']
            vol = row['volume']
            vol_sma = row['vol_sma20']

            bars_since_cross = i - last_cross_bar
            cross_confirmed = (cross in ('golden_cross', 'death_cross') and bars_since_cross == 0) or \
                              (bars_since_cross == COOLDOWN_BARS)

            if not cross_confirmed:
                peak_capital = max(peak_capital, capital)
                dd = (peak_capital - capital) / peak_capital
                max_drawdown = max(max_drawdown, dd)
                continue

            if bars_since_cross == COOLDOWN_BARS:
                cross_type = df.iloc[last_cross_bar]['cross']
            else:
                cross_type = cross

            if pd.isna(adx) or adx < adx_min:
                peak_capital = max(peak_capital, capital)
                dd = (peak_capital - capital) / peak_capital
                max_drawdown = max(max_drawdown, dd)
                continue

            if pd.isna(vol_sma) or vol_sma == 0 or vol < VOL_MULT * vol_sma:
                peak_capital = max(peak_capital, capital)
                dd = (peak_capital - capital) / peak_capital
                max_drawdown = max(max_drawdown, dd)
                continue

            daily_ema50_up = row.get('daily_ema50_up', None)
            atr = row['atr']

            if cross_type == 'golden_cross' and rsi > 50 and rsi < 70 and price > row['ema50']:
                if daily_ema50_up is not None and not daily_ema50_up:
                    pass
                else:
                    margin = capital * MAX_MARGIN_PCT
                    capital -= margin  # 冻结保证金
                    entry = price * (1 + SLIPPAGE)
                    capital -= margin * LEVERAGE * FEE_RATE  # 开仓手续费
                    position = {
                        'side': 'long', 'entry': entry,
                        'sl': entry - sl_atr * atr,
                        'tp': entry + tp_atr * atr,
                        'entry_atr': atr,
                        'margin': margin, 'entry_idx': i,
                        'partial_taken': False, 'partial_pnl': 0,
                    }

            elif cross_type == 'death_cross' and rsi < 50 and rsi > 30 and price < row['ema50']:
                if daily_ema50_up is not None and daily_ema50_up:
                    pass
                else:
                    margin = capital * MAX_MARGIN_PCT
                    capital -= margin
                    entry = price * (1 - SLIPPAGE)
                    capital -= margin * LEVERAGE * FEE_RATE
                    position = {
                        'side': 'short', 'entry': entry,
                        'sl': entry + sl_atr * atr,
                        'tp': entry - tp_atr * atr,
                        'entry_atr': atr,
                        'margin': margin, 'entry_idx': i,
                        'partial_taken': False, 'partial_pnl': 0,
                    }

        peak_capital = max(peak_capital, capital)
        dd = (peak_capital - capital) / peak_capital
        max_drawdown = max(max_drawdown, dd)

    # 平掉未关闭仓位
    if position:
        exit_price = df.iloc[end_idx - 1]['close']
        slip = exit_price * SLIPPAGE
        if position['side'] == 'long':
            exit_price -= slip
            pnl_pct = (exit_price / position['entry']) - 1
        else:
            exit_price += slip
            pnl_pct = 1 - (exit_price / position['entry'])
        pnl_pct -= FEE_RATE
        pnl = position['margin'] * LEVERAGE * pnl_pct
        capital += pnl + position['margin']
        total_pnl = pnl + position.get('partial_pnl', 0)
        trades.append({
            'symbol': symbol, 'side': position['side'],
            'entry': position['entry'], 'exit': exit_price,
            'pnl': total_pnl, 'pnl_pct': total_pnl / (INITIAL_CAPITAL * MAX_MARGIN_PCT * LEVERAGE) * 100,
            'reason': 'eod', 'bars_held': end_idx - 1 - position['entry_idx'],
            'partial_taken': position.get('partial_taken', False),
        })

    if not trades:
        return {
            'symbol': symbol, 'trades': 0, 'total_return': 0,
            'win_rate': 0, 'profit_factor': 0, 'max_drawdown': 0,
            'sharpe': 0, 'avg_win_loss_ratio': 0, 'trades_list': [],
        }

    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    total_return = (capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    avg_win = np.mean([t['pnl'] for t in wins]) if wins else 0
    avg_loss = abs(np.mean([t['pnl'] for t in losses])) if losses else 1

    returns = [t['pnl_pct'] / 100 for t in trades]
    sharpe = 0
    if len(returns) > 1 and np.std(returns) > 0:
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(max(len(trades), 1))

    reason_stats = {}
    for reason in ['tp', 'sl', 'reverse', 'timeout', 'eod']:
        rt = [t for t in trades if t['reason'] == reason]
        if rt:
            reason_stats[reason] = {
                'count': len(rt),
                'avg_pnl': round(np.mean([t['pnl_pct'] for t in rt]), 2),
            }

    return {
        'symbol': symbol,
        'trades': len(trades),
        'win_rate': round(len(wins) / len(trades) * 100, 1),
        'profit_factor': round(avg_win / avg_loss, 2) if avg_loss > 0 else float('inf'),
        'avg_win_loss_ratio': round(avg_win / avg_loss, 2) if avg_loss > 0 else 0,
        'total_return': round(total_return, 2),
        'max_drawdown': round(max_drawdown * 100, 2),
        'sharpe': round(sharpe, 2),
        'trades_list': trades,
        'reason_stats': reason_stats,
    }


def run_v2_backtest(df, symbol, start_idx=50, end_idx=None):
    """V2参数回测用于对比"""
    return run_single_backtest(df, symbol, sl_atr=2.5, tp_atr=5.0, adx_min=25,
                               start_idx=start_idx, end_idx=end_idx, partial_tp=False)


def run_v1_backtest(df, symbol, start_idx=50, end_idx=None):
    """V1参数回测: 1.5x SL, 3x TP, no ADX filter (adx_min=0)"""
    return run_single_backtest(df, symbol, sl_atr=1.5, tp_atr=3.0, adx_min=0,
                               start_idx=start_idx, end_idx=end_idx, partial_tp=False)


def grid_search(datasets, symbols):
    """参数网格搜索，在训练集上优化"""
    sl_range = [2.0, 2.5, 3.0]
    tp_range = [3.0, 3.5, 4.0]
    adx_range = [20, 22, 25]
    ema_range = [(9, 21), (8, 21), (12, 26)]

    results = []
    total_combos = len(sl_range) * len(tp_range) * len(adx_range) * len(ema_range)
    print(f"\n🔍 网格搜索: {total_combos} 组参数...")

    for idx, (sl, tp, adx, (ema_f, ema_s)) in enumerate(product(sl_range, tp_range, adx_range, ema_range)):
        if idx % 20 == 0:
            print(f"  进度: {idx}/{total_combos}...")

        combo_trades = 0
        combo_return = 0
        combo_dd = 0
        combo_wr = 0
        combo_pf = 0
        n_coins = 0

        for sym, (df_train, train_split) in zip(symbols, datasets):
            # Re-add indicators with custom EMA
            df_t = add_indicators_with_ema(df_train, ema_f, ema_s)
            r = run_single_backtest(df_t, sym, sl_atr=sl, tp_atr=tp, adx_min=adx,
                                    start_idx=50, end_idx=train_split, partial_tp=True)
            combo_trades += r['trades']
            combo_return += r['total_return']
            combo_dd += r['max_drawdown']
            if r['trades'] > 0:
                combo_wr += r['win_rate']
                combo_pf += r['profit_factor']
                n_coins += 1

        n = max(n_coins, 1)
        results.append({
            'sl_atr': sl, 'tp_atr': tp, 'adx_min': adx,
            'ema': f"{ema_f}/{ema_s}",
            'trades': combo_trades,
            'avg_return': round(combo_return / len(symbols), 2),
            'avg_dd': round(combo_dd / len(symbols), 2),
            'avg_wr': round(combo_wr / n, 1),
            'avg_pf': round(combo_pf / n, 2),
            # 综合评分: 收益/回撤 + 盈亏比权重
            'score': round((combo_return / len(symbols)) / max(combo_dd / len(symbols), 0.1) +
                          combo_pf / n * 0.5, 2) if n > 0 else -999,
        })

    results.sort(key=lambda x: x['score'], reverse=True)
    return results


def main():
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']

    # 获取数据
    all_data = {}
    for sym in symbols:
        print(f"📥 获取 {sym} 4H数据 (7个月)...")
        df_4h = fetch_historical(sym, days=210)
        print(f"  {len(df_4h)} 根K线: {df_4h.index[0]} → {df_4h.index[-1]}")

        print(f"📥 获取 {sym} 日线数据...")
        df_daily = fetch_daily(sym, days=260)

        # 默认EMA(9,21)指标
        df_4h = add_all_indicators(df_4h)
        df_4h = add_daily_ema50_to_4h(df_4h, df_daily)
        df_4h['regime'] = classify_regime(df_4h)
        all_data[sym] = (df_4h, df_daily)

    # 训练/验证分割: 前73%训练, 后27%验证 (约4个月 vs 1.5个月+)
    datasets = []
    for sym in symbols:
        df_4h, _ = all_data[sym]
        n = len(df_4h)
        train_split = int(n * 0.73)
        datasets.append((df_4h, train_split))
        print(f"  {sym}: 训练 {df_4h.index[50]} → {df_4h.index[train_split-1]} | "
              f"验证 {df_4h.index[train_split]} → {df_4h.index[-1]}")

    # ═══ 网格搜索 ═══
    grid_results = grid_search(datasets, symbols)

    print("\n" + "="*80)
    print("📊 网格搜索 TOP 10")
    print("="*80)
    print(f"{'SL':>4} {'TP':>4} {'ADX':>4} {'EMA':>6} {'Trades':>7} {'Return%':>8} {'DD%':>6} {'WR%':>6} {'PF':>5} {'Score':>6}")
    print("-"*60)
    for r in grid_results[:10]:
        print(f"{r['sl_atr']:>4} {r['tp_atr']:>4} {r['adx_min']:>4} {r['ema']:>6} "
              f"{r['trades']:>7} {r['avg_return']:>8} {r['avg_dd']:>6} {r['avg_wr']:>6} {r['avg_pf']:>5} {r['score']:>6}")

    best = grid_results[0]
    ema_f, ema_s = map(int, best['ema'].split('/'))
    print(f"\n✅ 最优参数: SL={best['sl_atr']}x ATR, TP={best['tp_atr']}x ATR, "
          f"ADX≥{best['adx_min']}, EMA({ema_f},{ema_s})")

    # ═══ 用最优参数做完整回测(训练+验证分开报告) ═══
    print("\n" + "="*80)
    print("📊 V1 vs V2 vs V3 对比 (全量数据)")
    print("="*80)

    report_lines = []
    report_lines.append("📊 **4H短线策略V3回测报告**\n")
    report_lines.append("═══════════════════════════\n")

    # 网格搜索top 5
    report_lines.append("**🔍 网格搜索Top 5 (训练集)**\n")
    report_lines.append("```")
    report_lines.append(f"{'SL':>4} {'TP':>4} {'ADX':>4} {'EMA':>6} {'#':>3} {'Ret%':>7} {'DD%':>6} {'WR%':>5} {'PF':>5}")
    for r in grid_results[:5]:
        report_lines.append(f"{r['sl_atr']:>4} {r['tp_atr']:>4} {r['adx_min']:>4} {r['ema']:>6} "
                           f"{r['trades']:>3} {r['avg_return']:>7} {r['avg_dd']:>6} {r['avg_wr']:>5} {r['avg_pf']:>5}")
    report_lines.append("```\n")
    report_lines.append(f"✅ **最优**: SL={best['sl_atr']}x, TP={best['tp_atr']}x, ADX≥{best['adx_min']}, EMA({ema_f},{ema_s})\n")

    # V1 vs V2 vs V3 各币种
    v1_all, v2_all, v3_all = [], [], []
    v3_train_all, v3_val_all = [], []

    for sym in symbols:
        df_4h, df_daily = all_data[sym]
        n = len(df_4h)
        train_split = int(n * 0.73)

        # V1 (全量, 默认EMA 9/21)
        v1 = run_v1_backtest(df_4h, sym)
        v1_all.append(v1)

        # V2 (全量, 默认EMA 9/21)
        v2 = run_v2_backtest(df_4h, sym)
        v2_all.append(v2)

        # V3 (需要重算指标如果EMA不同)
        df_v3 = add_indicators_with_ema(df_4h, ema_f, ema_s)
        df_v3 = add_daily_ema50_to_4h(df_v3, df_daily)
        df_v3['regime'] = classify_regime(df_v3)

        v3_full = run_single_backtest(df_v3, sym, sl_atr=best['sl_atr'], tp_atr=best['tp_atr'],
                                       adx_min=best['adx_min'], partial_tp=True)
        v3_all.append(v3_full)

        # V3 训练集/验证集分离
        v3_train = run_single_backtest(df_v3, sym, sl_atr=best['sl_atr'], tp_atr=best['tp_atr'],
                                        adx_min=best['adx_min'], start_idx=50, end_idx=train_split, partial_tp=True)
        v3_val = run_single_backtest(df_v3, sym, sl_atr=best['sl_atr'], tp_atr=best['tp_atr'],
                                      adx_min=best['adx_min'], start_idx=train_split, end_idx=n, partial_tp=True)
        v3_train_all.append(v3_train)
        v3_val_all.append(v3_val)

    # V1/V2/V3对比表
    report_lines.append("**📈 V1 vs V2 vs V3 三版对比**\n")
    report_lines.append("```")
    report_lines.append(f"{'Coin':<10} {'Ver':<4} {'#':>3} {'Ret%':>7} {'DD%':>6} {'WR%':>5} {'PF':>5} {'Sharpe':>6}")
    report_lines.append("-" * 50)

    for i, sym in enumerate(symbols):
        for label, data in [('V1', v1_all[i]), ('V2', v2_all[i]), ('V3', v3_all[i])]:
            report_lines.append(f"{sym:<10} {label:<4} {data['trades']:>3} {data['total_return']:>7.2f} "
                               f"{data['max_drawdown']:>6.2f} {data['win_rate']:>5.1f} "
                               f"{data['profit_factor']:>5.2f} {data['sharpe']:>6.2f}")
        report_lines.append("")
    report_lines.append("```\n")

    # 汇总平均
    def avg_metric(results, key):
        vals = [r[key] for r in results if r['trades'] > 0]
        return round(np.mean(vals), 2) if vals else 0

    report_lines.append("**📊 平均指标**\n")
    report_lines.append("```")
    report_lines.append(f"{'Ver':<4} {'#':>4} {'Ret%':>7} {'DD%':>6} {'WR%':>5} {'PF':>5}")
    for label, data in [('V1', v1_all), ('V2', v2_all), ('V3', v3_all)]:
        total_t = sum(r['trades'] for r in data)
        report_lines.append(f"{label:<4} {total_t:>4} {avg_metric(data,'total_return'):>7.2f} "
                           f"{avg_metric(data,'max_drawdown'):>6.2f} {avg_metric(data,'win_rate'):>5.1f} "
                           f"{avg_metric(data,'profit_factor'):>5.2f}")
    report_lines.append("```\n")

    # V3退出原因分析
    all_v3_trades = []
    for r in v3_all:
        all_v3_trades.extend(r['trades_list'])

    if all_v3_trades:
        report_lines.append("**🎯 V3退出原因分析**\n")
        report_lines.append("```")
        for reason in ['tp', 'sl', 'reverse', 'timeout']:
            rt = [t for t in all_v3_trades if t['reason'] == reason]
            if rt:
                w = sum(1 for t in rt if t['pnl'] > 0)
                report_lines.append(f"{reason:>8}: {len(rt)}笔 WR={w/len(rt)*100:.0f}% "
                                   f"avg={np.mean([t['pnl_pct'] for t in rt]):.2f}%")
        partial_count = sum(1 for t in all_v3_trades if t.get('partial_taken'))
        report_lines.append(f"分批止盈: {partial_count}/{len(all_v3_trades)}笔触发")
        report_lines.append("```\n")

    # 过拟合评估
    report_lines.append("**⚠️ 过拟合评估 (训练 vs 验证)**\n")
    report_lines.append("```")
    report_lines.append(f"{'Coin':<10} {'Set':<6} {'#':>3} {'Ret%':>7} {'DD%':>6} {'WR%':>5} {'PF':>5}")
    for i, sym in enumerate(symbols):
        for label, data in [('Train', v3_train_all[i]), ('Valid', v3_val_all[i])]:
            report_lines.append(f"{sym:<10} {label:<6} {data['trades']:>3} {data['total_return']:>7.2f} "
                               f"{data['max_drawdown']:>6.2f} {data['win_rate']:>5.1f} "
                               f"{data['profit_factor']:>5.2f}")
    report_lines.append("```\n")

    # 过拟合风险判断
    train_avg_ret = avg_metric(v3_train_all, 'total_return')
    val_avg_ret = avg_metric(v3_val_all, 'total_return')
    train_avg_wr = avg_metric(v3_train_all, 'win_rate')
    val_avg_wr = avg_metric(v3_val_all, 'win_rate')

    if val_avg_ret < train_avg_ret * 0.5:
        overfit_risk = "🔴 高风险 — 验证集收益显著低于训练集"
    elif val_avg_ret < train_avg_ret * 0.7:
        overfit_risk = "🟡 中等风险 — 验证集表现有衰减"
    else:
        overfit_risk = "🟢 低风险 — 验证集表现稳定"

    report_lines.append(f"训练集平均收益: {train_avg_ret:.2f}% | WR: {train_avg_wr:.1f}%")
    report_lines.append(f"验证集平均收益: {val_avg_ret:.2f}% | WR: {val_avg_wr:.1f}%")
    report_lines.append(f"**过拟合风险: {overfit_risk}**\n")

    # 参数敏感性
    report_lines.append("**📐 参数敏感性 (Top 5 vs Bottom 5 得分差)**\n")
    top5_avg = np.mean([r['score'] for r in grid_results[:5]])
    bot5_avg = np.mean([r['score'] for r in grid_results[-5:]])
    report_lines.append(f"Top5均分: {top5_avg:.2f} | Bottom5均分: {bot5_avg:.2f}")
    if top5_avg > bot5_avg * 3:
        report_lines.append("⚠️ 参数敏感性高，最优参数可能不稳定")
    else:
        report_lines.append("✅ 参数敏感性适中，结果相对稳健")

    report_text = "\n".join(report_lines)
    print(report_text)

    # 保存报告
    os.makedirs('/Users/zhilongzheng/Projects/alpha-crypto-skill/scripts/backtest/results', exist_ok=True)
    with open('/Users/zhilongzheng/Projects/alpha-crypto-skill/scripts/backtest/results/v3_report.md', 'w') as f:
        f.write(report_text)

    # 保存网格搜索完整结果
    with open('/Users/zhilongzheng/Projects/alpha-crypto-skill/scripts/backtest/results/v3_grid_search.json', 'w') as f:
        json.dump(grid_results, f, indent=2)

    return report_text


if __name__ == '__main__':
    report = main()
