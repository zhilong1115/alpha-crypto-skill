# Indicator Guide

## 1. TSI (True Strength Index)
- **Parameters**: r=25 (long EMA), s=13 (short EMA), signal=13
- **Calculation**: 100 × EMA(EMA(momentum, r), s) / EMA(EMA(|momentum|, r), s)
- **Key Levels**: ±40
  - TSI ≤ -40 and turning up → oversold, potential buy
  - TSI ≥ +40 and turning down → overbought, potential sell
- **Timeframes**: Daily (primary), 3-day, 5-day for macro signals
- **For scoring**: Bullish = TSI < 0 and rising (TSI > TSI_prev)

## 2. OBV + EMA9 (On-Balance Volume)
- **OBV**: Cumulative sum of signed volume (+ on up days, - on down days)
- **EMA9**: 9-period EMA of OBV
- **Signal**: OBV > EMA9 = bullish (money flowing in), OBV < EMA9 = bearish
- **Multi-timeframe**: 4H → 12H → Daily confirmation strengthens signal

## 3. WaveTrend
- **Parameters**: channel_length=10, average_length=21
- **Calculation**:
  - AP = (H + L + C) / 3
  - ESA = EMA(AP, 10)
  - D = EMA(|AP - ESA|, 10)
  - CI = (AP - ESA) / (0.015 × D)
  - WT1 = EMA(CI, 21)
  - WT2 = SMA(WT1, 4)
- **Levels**: Overbought > +60, Oversold < -60
- **Signals**: WT1 crosses above WT2 in oversold zone = strong buy
- **For scoring**: Bullish = WT1 > WT2

## 4. USDT.D (Tether Dominance)
- **What**: USDT market share percentage
- **Logic**: USDT.D rising = money leaving crypto = bearish; falling = bullish
- **Implementation**: We simulate via inverse BTC price correlation (actual USDT.D data not available via exchange APIs)
- **Signal**: USDT.D TSI falling = bullish for crypto
- **Note**: This is a proxy — real USDT.D from TradingView would be more accurate

## 5. SMA200 (Simple Moving Average)
- **Period**: 200 daily candles
- **Use**: Regime detection for Aggressive and H
  - SMA200 rising (today > yesterday) = Bull regime
  - SMA200 falling = Bear regime
- **Mayer Multiple**: Price / SMA200
  - < 0.8 = significantly undervalued (buy signal)
  - < 0.6 = extremely undervalued (strong buy)
  - > 2.4 = overheated

## 6. MA120 (4H)
- **Period**: 120 on 4-hour chart
- **Use**: Hard stop-loss line — close below = immediate exit
- **CORE group rule**: "MA120硬止损" — non-negotiable risk management
