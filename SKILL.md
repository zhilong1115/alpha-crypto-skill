---
name: crypto-trading
description: Crypto trading signals for BTC, ETH and altcoins using TSI, OBV+EMA9, WaveTrend, USDT.D indicators. Implements Aggressive (Adaptive Threshold) and Conservative (Graduated Sizing) scoring with graduated position sizing.
---

# Crypto Trading Skill

Two trading systems based on the CORE group's 3-year proven methodology using 4 core indicators: **TSI**, **OBV+EMA9**, **WaveTrend**, and **USDT.D**.

## Systems

### Aggressive Mode — Adaptive Threshold
Equal weight 25pts each for TSI, OBV, USDT.D, WaveTrend (0-100 score).
SMA200 direction determines buy/sell thresholds:
- **Bull** (SMA200 rising): Buy ≥ 50, Sell ≤ 25
- **Bear** (SMA200 falling): Buy ≥ 75, Sell ≤ 50

Full position (100%) on buy signal. Best for trending markets.

### Conservative Mode — Graduated Position Sizing
SMA200 determines regime, then counts bullish indicators for graduated sizing:
- **Bull**: 4/4→50%, 3/4→30%, 2/4→15%, 1/4→0%
- **Bear**: 4/4→30%, 3/4→15%, 2/4→0%

Lower max exposure, smoother equity curve. Recommended for most users.

## Usage

### Scan multiple coins for signals
```bash
python scripts/scanner.py --coins BTC,ETH,SOL
```

### Check a specific coin with timeframe
```bash
python scripts/scanner.py --coin BTC --timeframe 1d
```

### Backtest a system
```bash
python scripts/backtest.py --system E --coin BTC --years 5
python scripts/backtest.py --system H --coin ETH --years 3
```

### Monitor open positions
```bash
python scripts/monitor.py --positions BTC:50000,ETH:3000
```

## Risk Rules (CORE Group)
1. **Spot only** — No leverage, no contracts (现货为王)
2. **Max 50% position** — Never more than half in one trade
3. **5% stop-loss** — Always set, no exceptions
4. **MA120 hard stop** — Close below 4H MA120 = immediate exit
5. **BTC leads** — Don't buy alts if BTC is weak (大饼引领)
6. **Right-side entry** — Enter after breakout confirmation, not bottom-fishing
7. **~40 day cycle** — Be aware of cyclical tops/bottoms
8. **Top 3 exchanges** — Only coins on Binance + Coinbase + OKX
9. **No linear unlocks** — Avoid tokens with heavy vesting schedules
10. **Take profits** — Don't diamond-hand, sell at targets (不格局)

## Indicators
- **TSI**: r=25, s=13, signal=13. Key levels ±40
- **OBV EMA**: 9-period EMA on On-Balance Volume
- **WaveTrend**: channel=10, avg=21, overbought=+60, oversold=-60
- **SMA200**: 200-period SMA for regime detection
- **USDT.D**: Simulated via inverse BTC correlation (proxy)
- **Mayer Multiple**: price/MA200, buy signal when < 0.8

## Dependencies
```
pip install ccxt pandas numpy pandas-ta
```
