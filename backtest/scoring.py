"""7 scoring systems (A-G)."""
import numpy as np
from indicators import (tsi_bullish, tsi_bearish, obv_bullish, obv_bearish,
                         usdt_d_bullish, usdt_d_bearish, wt_bullish, wt_bearish)


def _binary_signals(row):
    """Return dict of bullish/bearish for each indicator.
    For non-crossover indicators, we use state (above/below threshold) rather than single-bar events.
    """
    # TSI: bullish if <= -40 and turning up OR if previously triggered and still < 0
    # Simplified: use level-based for scoring
    tsi_bull = row['tsi'] < 0 and row['tsi'] > row['tsi_prev']  # below zero and rising
    tsi_bear = row['tsi'] > 0 and row['tsi'] < row['tsi_prev']  # above zero and falling

    obv_bull = row['obv'] > row['obv_ema9']
    obv_bear = row['obv'] < row['obv_ema9']

    usdt_bull = row['usdt_d_tsi'] < row['usdt_d_tsi_prev']  # falling = good
    usdt_bear = row['usdt_d_tsi'] > row['usdt_d_tsi_prev']

    wt_bull = row['wt1'] > row['wt2']  # wt1 above wt2
    wt_bear = row['wt1'] < row['wt2']

    return {
        'tsi_bull': tsi_bull, 'tsi_bear': tsi_bear,
        'obv_bull': obv_bull, 'obv_bear': obv_bear,
        'usdt_bull': usdt_bull, 'usdt_bear': usdt_bear,
        'wt_bull': wt_bull, 'wt_bear': wt_bear,
    }


def score_A(row):
    """Equal Weight 25 each. Buy>=75, Sell<=25."""
    s = _binary_signals(row)
    score = (s['tsi_bull']*25 + s['obv_bull']*25 + s['usdt_bull']*25 + s['wt_bull']*25)
    return score, 75, 25


def score_B(row):
    """Layered. USDT.D is gate."""
    s = _binary_signals(row)
    usdt_score = 30 if s['usdt_bull'] else 0
    other = s['tsi_bull']*30 + s['obv_bull']*20 + s['wt_bull']*20
    if not s['usdt_bull']:
        other = min(other, 30)
    score = usdt_score + other
    return score, 70, 20


def score_C(row):
    """TSI-Heavy."""
    s = _binary_signals(row)
    score = s['tsi_bull']*40 + s['obv_bull']*20 + s['usdt_bull']*25 + s['wt_bull']*15
    return score, 70, 20


def score_D(row):
    """Momentum-Heavy."""
    s = _binary_signals(row)
    score = s['tsi_bull']*20 + s['obv_bull']*30 + s['usdt_bull']*20 + s['wt_bull']*30
    return score, 70, 20


def score_E(row):
    """Adaptive Threshold."""
    s = _binary_signals(row)
    score = s['tsi_bull']*25 + s['obv_bull']*25 + s['usdt_bull']*25 + s['wt_bull']*25
    bull_regime = row['sma200'] > row['sma200_prev'] if not np.isnan(row.get('sma200', np.nan)) else True
    if bull_regime:
        return score, 50, 25
    else:
        return score, 75, 50


def score_F(row):
    """Continuous Scoring — generous thresholds."""
    # TSI: map [-20,0] -> [25,0], below -20 = 25pts
    tsi = row['tsi']
    if np.isnan(tsi):
        tsi_score = 0
    elif tsi <= -20:
        tsi_score = 25
    elif tsi <= 0:
        tsi_score = 25 * (-tsi / 20)
    elif tsi <= 10:
        tsi_score = 5  # small credit for mildly positive
    else:
        tsi_score = 0

    # OBV: % distance from EMA9. 1% above = 12pts, 3%+ = 25pts
    if row['obv_ema9'] != 0 and not np.isnan(row['obv_ema9']):
        obv_pct = (row['obv'] - row['obv_ema9']) / abs(row['obv_ema9']) * 100
        if obv_pct >= 3:
            obv_score = 25
        elif obv_pct >= 0:
            obv_score = 12 * (obv_pct / 1.0)  # 1% = 12pts, linear to 3%=36 capped at 25
            obv_score = np.clip(obv_score, 0, 25)
        else:
            obv_score = 0
    else:
        obv_score = 0

    # USDT.D TSI: more negative = more bullish for crypto (more generous)
    usdt_tsi = row['usdt_d_tsi']
    if np.isnan(usdt_tsi):
        usdt_score = 0
    else:
        usdt_score = np.clip((-usdt_tsi / 20) * 25, 0, 25)

    # WaveTrend: more negative wt1 = more oversold (more generous)
    wt1 = row['wt1']
    if np.isnan(wt1):
        wt_score = 0
    else:
        wt_score = np.clip((-wt1 / 30) * 25, 0, 25)

    score = tsi_score + obv_score + usdt_score + wt_score
    return score, 50, 25


def score_G(row):
    """Confirmation Count with relaxed signals + rolling lookback via looser thresholds."""
    # Relaxed binary signals for G
    tsi_bull = row['tsi'] < 10 and row['tsi'] > row['tsi_prev']  # TSI below 10 and rising
    obv_bull = row['obv'] > row['obv_ema9']
    usdt_bull = row['usdt_d_tsi'] < row['usdt_d_tsi_prev']
    wt_bull = row['wt1'] > row['wt2']

    count = int(tsi_bull) + int(obv_bull) + int(usdt_bull) + int(wt_bull)
    return count, None, None  # special


SYSTEMS = {
    'A': score_A, 'B': score_B, 'C': score_C, 'D': score_D,
    'E': score_E, 'F': score_F, 'G': score_G,
}
