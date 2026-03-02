#!/usr/bin/env python3
"""4H短线策略技术指标模块 V2
EMA交叉 + RSI过滤 + ATR止损止盈 + ADX趋势强度 + 成交量确认
"""
import numpy as np
import pandas as pd


def calc_ema(series: pd.Series, span: int) -> pd.Series:
    """指数移动平均线"""
    return series.ewm(span=span, adjust=False).mean()


def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI相对强弱指标"""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR平均真实波幅，需要OHLC列"""
    high, low, close_prev = df['high'], df['low'], df['close'].shift(1)
    tr = pd.concat([
        high - low,
        (high - close_prev).abs(),
        (low - close_prev).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def calc_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ADX平均方向性指数"""
    high, low, close = df['high'], df['low'], df['close']
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    atr = calc_atr(df, period)
    plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(span=period, adjust=False).mean()
    return adx


def detect_ema_cross(ema_fast: pd.Series, ema_slow: pd.Series) -> pd.Series:
    """检测EMA交叉信号，返回Series: golden_cross / death_cross / none"""
    prev_diff = (ema_fast.shift(1) - ema_slow.shift(1))
    curr_diff = (ema_fast - ema_slow)
    result = pd.Series('none', index=ema_fast.index)
    result[(prev_diff <= 0) & (curr_diff > 0)] = 'golden_cross'
    result[(prev_diff >= 0) & (curr_diff < 0)] = 'death_cross'
    return result


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """给4H OHLCV DataFrame添加所有策略所需指标（V2含ADX+成交量）"""
    df = df.copy()
    df['ema9'] = calc_ema(df['close'], 9)
    df['ema21'] = calc_ema(df['close'], 21)
    df['ema50'] = calc_ema(df['close'], 50)
    df['rsi'] = calc_rsi(df['close'], 14)
    df['atr'] = calc_atr(df, 14)
    df['adx'] = calc_adx(df, 14)
    df['cross'] = detect_ema_cross(df['ema9'], df['ema21'])
    df['vol_sma20'] = df['volume'].rolling(20).mean()
    return df
