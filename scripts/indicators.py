#!/usr/bin/env python3
"""Calculate all 4 core indicators from OHLCV data.
Dependencies: pandas, numpy
"""
import numpy as np
import pandas as pd


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def calc_tsi(close: pd.Series, r=25, s=13) -> pd.Series:
    """True Strength Index. Key levels: ±40."""
    mom = close.diff(1)
    num = ema(ema(mom, r), s)
    den = ema(ema(mom.abs(), r), s)
    return 100 * num / den.replace(0, np.nan)


def calc_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume."""
    sign = np.sign(close.diff())
    sign.iloc[0] = 0
    return (sign * volume).cumsum()


def calc_obv_ema9(close: pd.Series, volume: pd.Series):
    """OBV with 9-period EMA. OBV > EMA9 = bullish."""
    obv = calc_obv(close, volume)
    return obv, ema(obv, 9)


def calc_wavetrend(high: pd.Series, low: pd.Series, close: pd.Series,
                   ch_len=10, avg_len=21):
    """WaveTrend oscillator. Overbought: +60, Oversold: -60."""
    ap = (high + low + close) / 3
    esa_val = ema(ap, ch_len)
    d = ema((ap - esa_val).abs(), ch_len)
    ci = (ap - esa_val) / (0.015 * d.replace(0, np.nan))
    wt1 = ema(ci, avg_len)
    wt2 = sma(wt1, 4)
    return wt1, wt2


def calc_all_indicators(df: pd.DataFrame, usdt_d_close: pd.Series = None):
    """Add all indicator columns to df. df must have open,high,low,close,volume."""
    df = df.copy()
    df['tsi'] = calc_tsi(df['close'])
    df['tsi_prev'] = df['tsi'].shift(1)

    obv, obv_ema = calc_obv_ema9(df['close'], df['volume'])
    df['obv'] = obv
    df['obv_ema9'] = obv_ema

    wt1, wt2 = calc_wavetrend(df['high'], df['low'], df['close'])
    df['wt1'] = wt1
    df['wt2'] = wt2
    df['wt1_prev'] = wt1.shift(1)
    df['wt2_prev'] = wt2.shift(1)

    # USDT.D TSI — use provided series or simulate via inverse BTC correlation
    if usdt_d_close is not None:
        df['usdt_d_tsi'] = calc_tsi(usdt_d_close.reindex(df.index, method='ffill'))
    else:
        inv = 1 / df['close']
        df['usdt_d_tsi'] = calc_tsi(inv)
    df['usdt_d_tsi_prev'] = df['usdt_d_tsi'].shift(1)

    # SMA200 for regime detection
    df['sma200'] = sma(df['close'], 200)
    df['sma200_prev'] = df['sma200'].shift(1)

    # Mayer Multiple
    df['mayer'] = df['close'] / df['sma200']

    return df


# Binary signal functions
def _binary_signals(row):
    """Return dict of bullish/bearish state for each indicator."""
    tsi_bull = row['tsi'] < 0 and row['tsi'] > row['tsi_prev']
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


if __name__ == '__main__':
    print("Indicators module. Import and use calc_all_indicators(df).")
    print("Parameters: TSI(25,13), OBV EMA(9), WaveTrend(10,21), SMA(200)")
