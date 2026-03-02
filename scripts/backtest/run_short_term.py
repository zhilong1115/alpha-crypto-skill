#!/usr/bin/env python3
"""4H短线策略V2回测引擎
改进: 2.5ATR止损, 5ATR止盈, trailing stop, ADX过滤, 成交量确认, 信号冷却, 日线MTF
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ccxt
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from short_term_indicators import add_all_indicators, calc_ema

# ── 参数 ──
FEE_RATE = 0.0006
SLIPPAGE = 0.0005
LEVERAGE = 3
MAX_MARGIN_PCT = 0.15
INITIAL_CAPITAL = 10000

# V2参数
SL_ATR_MULT = 2.5
TP_ATR_MULT = 5.0
TRAIL_TRIGGER_ATR = 2.0   # 盈利超过2x ATR后启动trailing
TRAIL_ATR_MULT = 1.5       # trailing距离1.5x ATR
ADX_MIN = 25               # ADX最低开仓阈值
COOLDOWN_BARS = 2          # 信号冷却期(2根4H K线=8小时)
VOL_MULT = 1.2             # 成交量须超过均量的倍数


def fetch_historical(symbol: str, days: int = 210) -> pd.DataFrame:
    """获取历史4H K线"""
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
    df = pd.DataFrame(all_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    df = df[~df.index.duplicated(keep='first')]
    return df


def fetch_daily(symbol: str, days: int = 260) -> pd.DataFrame:
    """获取日线数据用于多时间框架过滤"""
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
    df = pd.DataFrame(all_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    df = df[~df.index.duplicated(keep='first')]
    return df


def add_daily_ema50_to_4h(df_4h: pd.DataFrame, df_daily: pd.DataFrame) -> pd.DataFrame:
    """将日线EMA50映射到4H数据"""
    df_daily = df_daily.copy()
    df_daily['daily_ema50'] = calc_ema(df_daily['close'], 50)
    # 前向填充到4H时间框架
    daily_ema = df_daily['daily_ema50'].reindex(df_4h.index, method='ffill')
    df_4h['daily_ema50'] = daily_ema
    # 日线EMA50方向: 用5日变化判断
    daily_ema50_dir = df_daily['daily_ema50'].diff(5)
    daily_dir = daily_ema50_dir.reindex(df_4h.index, method='ffill')
    df_4h['daily_ema50_up'] = daily_dir > 0
    return df_4h


def classify_regime(df: pd.DataFrame) -> pd.Series:
    sma50 = df['close'].rolling(50).mean()
    sma50_slope = sma50.pct_change(12)
    regime = pd.Series('range', index=df.index)
    regime[sma50_slope > 0.02] = 'bull'
    regime[sma50_slope < -0.02] = 'bear'
    return regime


def run_backtest(df: pd.DataFrame, symbol: str) -> dict:
    """V2单币种回测"""
    df = add_all_indicators(df)
    df['regime'] = classify_regime(df)

    capital = INITIAL_CAPITAL
    peak_capital = capital
    max_drawdown = 0
    trades = []
    position = None
    equity_curve = []
    last_cross_bar = -999  # 上次交叉的bar index，用于冷却

    for i in range(50, len(df)):
        row = df.iloc[i]
        price = row['close']

        # 记录交叉发生位置
        if row['cross'] in ('golden_cross', 'death_cross'):
            last_cross_bar = i

        # ── 持仓管理 ──
        if position:
            atr_now = row['atr']

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

            # 止损止盈检查
            hit_sl = (position['side'] == 'long' and row['low'] <= position['sl']) or \
                     (position['side'] == 'short' and row['high'] >= position['sl'])
            hit_tp = (position['side'] == 'long' and row['high'] >= position['tp']) or \
                     (position['side'] == 'short' and row['low'] <= position['tp'])

            reverse = (position['side'] == 'long' and row['cross'] == 'death_cross') or \
                      (position['side'] == 'short' and row['cross'] == 'golden_cross')

            if hit_sl or hit_tp or reverse:
                if hit_tp:
                    exit_price = position['tp']
                elif hit_sl:
                    exit_price = position['sl']
                else:
                    exit_price = price

                slip = exit_price * SLIPPAGE
                if position['side'] == 'long':
                    exit_price -= slip
                    pnl_pct = (exit_price / position['entry']) - 1
                else:
                    exit_price += slip
                    pnl_pct = 1 - (exit_price / position['entry'])

                pnl_pct -= FEE_RATE * 2
                pnl = position['margin'] * LEVERAGE * pnl_pct
                capital += pnl

                trades.append({
                    'symbol': symbol,
                    'side': position['side'],
                    'entry': position['entry'],
                    'exit': exit_price,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct * LEVERAGE * 100,
                    'regime': df.iloc[position['entry_idx']]['regime'],
                    'reason': 'tp' if hit_tp else ('sl' if hit_sl else 'reverse'),
                    'entry_time': df.index[position['entry_idx']],
                    'exit_time': df.index[i],
                })
                position = None

        # ── 开仓信号 (V2过滤) ──
        if position is None:
            cross = row['cross']
            rsi = row['rsi']
            adx = row['adx']
            vol = row['volume']
            vol_sma = row['vol_sma20']

            # 冷却期检查: 交叉必须发生在cooldown之前或当前bar
            bars_since_cross = i - last_cross_bar
            cross_confirmed = (cross in ('golden_cross', 'death_cross') and bars_since_cross == 0) or \
                              (bars_since_cross == COOLDOWN_BARS)

            if not cross_confirmed:
                equity_curve.append(capital)
                peak_capital = max(peak_capital, capital)
                dd = (peak_capital - capital) / peak_capital
                max_drawdown = max(max_drawdown, dd)
                continue

            # 获取冷却期开始时的交叉类型
            if bars_since_cross == COOLDOWN_BARS:
                cross_type = df.iloc[last_cross_bar]['cross']
            else:
                cross_type = cross

            # ADX过滤
            if pd.isna(adx) or adx < ADX_MIN:
                equity_curve.append(capital)
                peak_capital = max(peak_capital, capital)
                dd = (peak_capital - capital) / peak_capital
                max_drawdown = max(max_drawdown, dd)
                continue

            # 成交量过滤
            if pd.isna(vol_sma) or vol_sma == 0 or vol < VOL_MULT * vol_sma:
                equity_curve.append(capital)
                peak_capital = max(peak_capital, capital)
                dd = (peak_capital - capital) / peak_capital
                max_drawdown = max(max_drawdown, dd)
                continue

            # 日线EMA50多时间框架过滤
            daily_ema50_up = row.get('daily_ema50_up', None)

            atr = row['atr']

            if cross_type == 'golden_cross' and rsi > 50 and rsi < 70 and price > row['ema50']:
                # 做多需要日线EMA50向上
                if daily_ema50_up is not None and not daily_ema50_up:
                    pass  # 日线不支持做多，跳过
                else:
                    margin = capital * MAX_MARGIN_PCT
                    entry = price * (1 + SLIPPAGE)
                    position = {
                        'side': 'long', 'entry': entry,
                        'sl': entry - SL_ATR_MULT * atr,
                        'tp': entry + TP_ATR_MULT * atr,
                        'entry_atr': atr,
                        'margin': margin, 'entry_idx': i
                    }
                    capital -= margin * FEE_RATE * LEVERAGE

            elif cross_type == 'death_cross' and rsi < 50 and rsi > 30 and price < row['ema50']:
                # 做空需要日线EMA50向下
                if daily_ema50_up is not None and daily_ema50_up:
                    pass  # 日线不支持做空，跳过
                else:
                    margin = capital * MAX_MARGIN_PCT
                    entry = price * (1 - SLIPPAGE)
                    position = {
                        'side': 'short', 'entry': entry,
                        'sl': entry + SL_ATR_MULT * atr,
                        'tp': entry - TP_ATR_MULT * atr,
                        'entry_atr': atr,
                        'margin': margin, 'entry_idx': i
                    }
                    capital -= margin * FEE_RATE * LEVERAGE

        equity_curve.append(capital)
        peak_capital = max(peak_capital, capital)
        dd = (peak_capital - capital) / peak_capital
        max_drawdown = max(max_drawdown, dd)

    # 统计
    if not trades:
        return {'symbol': symbol, 'trades': 0, 'total_return': 0, 'win_rate': 0,
                'profit_factor': 0, 'max_drawdown': 0, 'sharpe': 0,
                'buy_hold': 0, 'trades_list': [], 'equity': equity_curve}

    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    total_return = (capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100

    avg_win = np.mean([t['pnl'] for t in wins]) if wins else 0
    avg_loss = abs(np.mean([t['pnl'] for t in losses])) if losses else 1

    returns = [t['pnl_pct'] / 100 for t in trades]
    sharpe = 0
    if len(returns) > 1 and np.std(returns) > 0:
        trades_per_year = len(trades) / (len(df) / 2190) if len(df) > 0 else 1
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(trades_per_year)

    buy_hold = (df['close'].iloc[-1] / df['close'].iloc[50] - 1) * 100

    # 按exit reason统计
    reason_stats = {}
    for reason in ['tp', 'sl', 'reverse']:
        rt = [t for t in trades if t['reason'] == reason]
        if rt:
            reason_stats[reason] = {
                'count': len(rt),
                'pct': round(len(rt) / len(trades) * 100, 1),
                'avg_pnl': round(np.mean([t['pnl_pct'] for t in rt]), 2),
            }

    return {
        'symbol': symbol,
        'trades': len(trades),
        'win_rate': len(wins) / len(trades) * 100,
        'profit_factor': round(avg_win / avg_loss, 2) if avg_loss > 0 else float('inf'),
        'total_return': round(total_return, 2),
        'max_drawdown': round(max_drawdown * 100, 2),
        'sharpe': round(sharpe, 2),
        'buy_hold': round(buy_hold, 2),
        'trades_list': trades,
        'equity': equity_curve,
        'reason_stats': reason_stats,
        'period_start': str(df.index[50].date()),
        'period_end': str(df.index[-1].date()),
    }


def regime_breakdown(trades: list) -> dict:
    result = {}
    for regime in ['bull', 'bear', 'range']:
        rt = [t for t in trades if t['regime'] == regime]
        if rt:
            wins = [t for t in rt if t['pnl'] > 0]
            result[regime] = {
                'trades': len(rt),
                'win_rate': round(len(wins) / len(rt) * 100, 1),
                'avg_pnl': round(np.mean([t['pnl_pct'] for t in rt]), 2),
            }
    return result


if __name__ == '__main__':
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    results = []

    for sym in symbols:
        print(f"📥 获取 {sym} 4H历史数据...")
        df = fetch_historical(sym, days=210)
        print(f"  {len(df)} 根4H K线, {df.index[0]} — {df.index[-1]}")

        print(f"📥 获取 {sym} 日线数据...")
        df_daily = fetch_daily(sym, days=260)
        print(f"  {len(df_daily)} 根日线")

        # 添加指标 + 日线MTF
        df = add_all_indicators(df)
        df = add_daily_ema50_to_4h(df, df_daily)

        print(f"⏳ 回测 {sym} (V2)...")
        result = run_backtest(df, sym)
        results.append(result)
        print(f"  ✅ {result['trades']}笔交易, 收益{result['total_return']:+.2f}%, 胜率{result['win_rate']:.1f}%")

    # 打印汇总
    print("\n" + "="*60)
    total_trades = sum(r['trades'] for r in results)
    all_trades = []
    for r in results:
        all_trades.extend(r['trades_list'])

    if all_trades:
        wins = [t for t in all_trades if t['pnl'] > 0]
        losses = [t for t in all_trades if t['pnl'] <= 0]
        avg_win = np.mean([t['pnl'] for t in wins]) if wins else 0
        avg_loss = abs(np.mean([t['pnl'] for t in losses])) if losses else 1
        avg_return = np.mean([r['total_return'] for r in results])
        avg_dd = np.mean([r['max_drawdown'] for r in results])
        avg_sharpe = np.mean([r['sharpe'] for r in results])

        print(f"📊 V2汇总: {total_trades}笔 | 胜率{len(wins)/len(all_trades)*100:.1f}% | 盈亏比{avg_win/avg_loss:.2f}:1 | 收益{avg_return:.2f}% | 回撤{avg_dd:.2f}% | 夏普{avg_sharpe:.2f}")

    for r in results:
        print(f"  {r['symbol']}: {r['trades']}笔 | 胜率{r['win_rate']:.1f}% | 收益{r['total_return']:+.2f}% | 回撤{r['max_drawdown']:.2f}% | Sharpe{r['sharpe']:.2f}")
        if r.get('reason_stats'):
            for reason, stats in r['reason_stats'].items():
                print(f"    {reason}: {stats['count']}笔({stats['pct']}%) avg_pnl={stats['avg_pnl']}%")
