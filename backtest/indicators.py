"""Calculate all 4 indicators from OHLCV data."""
import numpy as np
import pandas as pd


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def calc_tsi(close: pd.Series, r=25, s=13) -> pd.Series:
    mom = close.diff(1)
    num = ema(ema(mom, r), s)
    den = ema(ema(mom.abs(), r), s)
    return 100 * num / den.replace(0, np.nan)


def calc_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    sign = np.sign(close.diff())
    sign.iloc[0] = 0
    return (sign * volume).cumsum()


def calc_obv_ema9(close: pd.Series, volume: pd.Series):
    obv = calc_obv(close, volume)
    return obv, ema(obv, 9)


def calc_wavetrend(high: pd.Series, low: pd.Series, close: pd.Series,
                   ch_len=10, avg_len=21):
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

    # USDT.D TSI - use provided or simulate inverse BTC
    if usdt_d_close is not None:
        df['usdt_d_tsi'] = calc_tsi(usdt_d_close.reindex(df.index, method='ffill'))
    else:
        # Simulate: inverse correlation with price
        inv = 1 / df['close']
        df['usdt_d_tsi'] = calc_tsi(inv)
    df['usdt_d_tsi_prev'] = df['usdt_d_tsi'].shift(1)

    # SMA 200 for adaptive system
    df['sma200'] = sma(df['close'], 200)
    df['sma200_prev'] = df['sma200'].shift(1)

    return df


# Binary signals
def tsi_bullish(row):
    return row['tsi'] <= -40 and row['tsi'] > row['tsi_prev']  # turning up

def tsi_bearish(row):
    return row['tsi'] >= 40 and row['tsi'] < row['tsi_prev']  # turning down

def obv_bullish(row):
    return row['obv'] > row['obv_ema9']

def obv_bearish(row):
    return row['obv'] < row['obv_ema9']

def usdt_d_bullish(row):
    # USDT.D falling = bullish for crypto
    return row['usdt_d_tsi'] < row['usdt_d_tsi_prev']

def usdt_d_bearish(row):
    return row['usdt_d_tsi'] > row['usdt_d_tsi_prev']

def wt_bullish(row):
    # Golden cross in oversold
    cross_up = row['wt1'] > row['wt2'] and row['wt1_prev'] <= row['wt2_prev']
    return cross_up and row['wt1'] < -60

def wt_bearish(row):
    cross_down = row['wt1'] < row['wt2'] and row['wt1_prev'] >= row['wt2_prev']
    return cross_down and row['wt1'] > 60
