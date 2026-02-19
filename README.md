# Alpha Crypto Skill 🪙

> Cryptocurrency trading signal system using 4 technical indicators with adaptive regime detection. Backtested across 5 years covering full bull-bear market cycles.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Overview

Alpha Crypto Skill is a quantitative crypto trading system that encodes 3 years of real trading experience from a private trading group (CORE) into programmable strategies. It uses **4 core technical indicators** combined with **SMA200 regime detection** to generate buy/sell signals for BTC, ETH, and SOL.

### Two Trading Modes

| Feature | 🔴 Aggressive Mode | 🟢 Conservative Mode |
|---------|-------------------|---------------------|
| Position Sizing | 100% in/out | Graduated 0-50% |
| Regime Adaptation | Adjusts thresholds | Adjusts max exposure |
| Best For | Strong trends | All market conditions |
| Risk Level | Higher | Lower |
| Recommended | Experienced traders | Most users ✅ |

### Core Indicators

1. **TSI** (True Strength Index) — Momentum oscillator with ±40 key levels
2. **OBV + EMA9** (On-Balance Volume) — Volume-based trend confirmation
3. **WaveTrend** — Oscillator with ±60 overbought/oversold zones
4. **USDT.D** (Tether Dominance) — Money flow proxy via inverse BTC correlation

### Regime Detection

- **SMA200** direction determines bull/bear market regime
- Bull regime → lower entry thresholds, higher position sizing
- Bear regime → stricter entry requirements, reduced exposure

---

## Performance

### Backtest Results (5 Years: 2021-2026)

All backtests run on BTC/USDT, ETH/USDT, and SOL/USDT daily candles with 0.1% trading fee, starting capital $10,000.

#### Key Metrics (BTC Average)

| Metric | 🔴 Aggressive | 🟢 Conservative |
|--------|:------------:|:---------------:|
| **Avg Annual Return** | ~85% | ~62% |
| **Max Drawdown** | 14.4% | 6.9% |
| **Sharpe Ratio** | 5.52 | 4.63 |
| **Win Rate** | 28.1% | 27.7% |
| **Trades / 5yr** | ~168 | ~153 |
| **Calmar Ratio** | Higher | **Best** |

#### Bear Market Highlight (2022)

While BTC dropped **-82%** from ATH during the 2022 bear market:

| Mode | 2022 Return | Max Drawdown |
|------|:-----------:|:------------:|
| Buy & Hold | -65% | -77% |
| 🔴 Aggressive | +34% | 14.4% |
| 🟢 Conservative | **+109%** | 6.9% |

> The Conservative mode's regime-aware graduated sizing kept exposure low during the worst of the bear, then captured the recovery.

#### Phase Breakdown

| Phase | Period | BTC Price Action | Aggressive | Conservative |
|-------|--------|-----------------|:----------:|:------------:|
| Bull Run | 2021 | $29K → $69K | ✅ Strong | ✅ Good |
| Bear Market | 2022 | $69K → $15K | ✅ Positive | ✅✅ Best |
| Recovery | 2023 | $15K → $42K | ✅ Strong | ✅ Good |
| New Bull | 2024-25 | $42K → $100K+ | ✅✅ Best | ✅ Good |

---

## How It Works

### The 4 Indicators

#### 1. TSI (True Strength Index)
```
Parameters: r=25, s=13, signal=13
Key Levels: ±40

Bullish: TSI < 0 and rising (TSI > TSI_prev)
Bearish: TSI > 0 and falling (TSI < TSI_prev)
```
The TSI measures momentum strength by double-smoothing price changes. Values below -40 indicate oversold conditions; above +40 indicates overbought.

#### 2. OBV + EMA9 (On-Balance Volume)
```
OBV: Cumulative sum of signed volume
Signal: 9-period EMA of OBV

Bullish: OBV > EMA9 (money flowing in)
Bearish: OBV < EMA9 (money flowing out)
```
Volume precedes price. When OBV crosses above its EMA, it signals accumulation.

#### 3. WaveTrend
```
Parameters: channel_length=10, average_length=21
Levels: Overbought > +60, Oversold < -60

Bullish: WT1 > WT2 (fast line above slow)
Bearish: WT1 < WT2
```
WaveTrend combines price and volatility to identify cyclical turning points. Cross-signals in oversold zones are particularly powerful.

#### 4. USDT.D (Tether Dominance Proxy)
```
Implementation: Simulated via inverse BTC correlation
Logic: USDT.D rising = money leaving crypto = bearish

Bullish: USDT.D TSI falling
Bearish: USDT.D TSI rising
```
When traders move to stablecoins, Tether dominance rises — a bearish signal for crypto assets.

### Regime Detection (SMA200)

The 200-day Simple Moving Average determines the market regime:

```python
if sma200_today > sma200_yesterday:
    regime = "BULL"   # Rising SMA200
else:
    regime = "BEAR"   # Falling SMA200
```

This single check dramatically improves signal quality by filtering out counter-trend trades.

### 🔴 Aggressive Mode — Adaptive Threshold

Each indicator contributes 25 points to a 0-100 composite score:

```
Score = TSI(25) + OBV(25) + USDT.D(25) + WaveTrend(25)

Bull Regime:  Buy ≥ 50, Sell ≤ 25
Bear Regime:  Buy ≥ 75, Sell ≤ 50
```

Full position (100%) on buy signal, complete exit on sell signal. Simple and effective in trending markets, but higher drawdowns during regime transitions.

### 🟢 Conservative Mode — Graduated Position Sizing

Counts the number of bullish indicators (0-4) and combines with regime to determine position size:

| Regime | 4/4 Bullish | 3/4 | 2/4 | 1/4 | 0/4 |
|--------|:-----------:|:---:|:---:|:---:|:---:|
| **Bull** (SMA200↑) | 50% | 30% | 15% | 0% | 0% |
| **Bear** (SMA200↓) | 30% | 15% | 0% | 0% | 0% |

This graduated approach means:
- Never more than 50% invested (even in the most bullish conditions)
- Automatically reduces exposure as signals weaken
- Zero exposure when fewer than 2 indicators agree in bear markets

---

## Installation

```bash
# Clone the repository
git clone https://github.com/zhilong1115/alpha-crypto-skill.git
cd alpha-crypto-skill

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Dependencies
- **ccxt** — Unified cryptocurrency exchange API (fetches OHLCV data)
- **pandas** — Data manipulation and analysis
- **numpy** — Numerical computing
- **pandas-ta** — Technical analysis indicators library

---

## Usage

### Scan for Signals

Scan multiple cryptocurrencies for current trading signals:

```bash
# Scan BTC, ETH, and SOL
python scripts/scanner.py --coins BTC,ETH,SOL

# Scan a specific coin with custom timeframe
python scripts/scanner.py --coin BTC --timeframe 1d
```

Example output:
```
=== BTC/USDT Signal Scan (1d) ===
Regime:    BULL (SMA200 rising)
TSI:       -12.3 (rising) → BULLISH ✅
OBV:       Above EMA9     → BULLISH ✅
WaveTrend: WT1 > WT2      → BULLISH ✅
USDT.D:    TSI falling     → BULLISH ✅

Aggressive Score: 100/100 → BUY (threshold: 50)
Conservative:     4/4 Bull → 50% position
```

### Run Backtests

```bash
# Run all scoring systems on BTC, ETH, SOL (full comparison)
python backtest/run_all.py

# Run Aggressive vs Conservative comparison
python backtest/run_hybrid.py

# Analyze bear market performance specifically
python backtest/run_bear.py
```

### Run Individual Backtest

```bash
# Backtest Aggressive mode on BTC (5 years)
python scripts/backtest.py --system E --coin BTC --years 5

# Backtest Conservative mode on ETH (3 years)
python scripts/backtest.py --system H --coin ETH --years 3
```

### Monitor Positions

```bash
# Monitor open positions with stop-loss alerts
python scripts/monitor.py --positions BTC:50000,ETH:3000
```

### Alpaca Paper Trading Integration

The system can be connected to [Alpaca](https://alpaca.markets/) for paper trading:

```python
import alpaca_trade_api as tradeapi

# Configure Alpaca paper trading
api = tradeapi.REST(
    key_id='YOUR_API_KEY',
    secret_key='YOUR_SECRET_KEY',
    base_url='https://paper-api.alpaca.markets'
)

# Execute based on Conservative mode signals
if conservative_signal['position_pct'] > 0:
    api.submit_order(
        symbol='BTCUSD',
        qty=calculate_qty(conservative_signal['position_pct']),
        side='buy',
        type='market',
        time_in_force='gtc'
    )
```

---

## Project Structure

```
alpha-crypto-skill/
├── README.md
├── SKILL.md                    # OpenClaw skill definition
├── LICENSE
├── requirements.txt
├── .gitignore
├── scripts/                    # Live trading scripts
│   ├── scanner.py              # Multi-coin signal scanner
│   ├── aggressive.py           # Aggressive mode implementation
│   ├── conservative.py         # Conservative mode implementation
│   ├── indicators.py           # Core indicator calculations
│   ├── backtest.py             # Single-system backtester
│   └── monitor.py              # Position monitoring & alerts
├── backtest/                   # Backtesting suite
│   ├── indicators.py           # Indicator calculations for backtest
│   ├── scoring.py              # All scoring systems (A-G)
│   ├── backtest.py             # Backtest engine
│   ├── run_all.py              # Run all systems comparison
│   ├── run_hybrid.py           # Aggressive vs Conservative
│   ├── run_bear.py             # Bear market analysis
│   └── requirements.txt        # Backtest-specific deps
└── references/                 # Documentation
    ├── indicator-guide.md      # Detailed indicator explanations
    ├── trading-rules.md        # CORE group trading rules
    └── backtest-results.md     # Backtest methodology & results
```

---

## Risk Management

### The 10 Rules (from CORE Group)

These rules were distilled from 3 years of real trading experience and 4,819 messages in a private crypto trading group:

1. **现货为王 — Spot Only**: No leverage, no futures. All major crypto funds trade spot only.
2. **右侧建仓 — Right-Side Entry**: Enter after breakout confirmation, never bottom-fish.
3. **止损纪律 — Stop-Loss Discipline**: 5% max loss per trade. Every position needs a stop-loss.
4. **不格局 — Don't Diamond-Hand**: Take profits at targets. Diamond-handing leads to devastating losses.
5. **大饼引领 — BTC Leads**: Don't buy altcoins if BTC is weak.
6. **40天周期 — ~40 Day Cycle**: Markets move in ~40-day cycles. Be cautious at cycle limits.
7. **MA120硬止损 — MA120 Hard Stop**: Price closes below 4H MA120 = immediate exit. Non-negotiable.
8. **三大交易所 — Top 3 Exchanges**: Only trade coins on Binance + Coinbase + OKX.
9. **无线性解锁 — No Linear Unlocks**: Avoid tokens with heavy vesting schedules.
10. **最大仓位50% — Max 50% Position**: Never more than half the portfolio in one trade.

```python
RISK_RULES = {
    "max_position_pct": 0.50,
    "stop_loss_pct": 0.05,
    "no_leverage": True,
    "ma120_hard_stop": True,
    "min_exchanges": 3,
    "right_side_only": True,
    "no_linear_unlock": True,
}
```

---

## Origin

This project is based on analysis of **4,819 messages** and **303 TradingView screenshots** from a private cryptocurrency trading group (2023-2026). It encodes 3 years of real trading experience — including a complete bear-bull cycle — into programmable, backtestable strategies.

The key insight: **"只有机器人能不带感情"** — Only bots can trade without emotion. This is the ultimate motivation for encoding human trading wisdom into algorithms.

---

## Disclaimer

⚠️ **This is not financial advice.** Past backtest performance does not guarantee future results. Cryptocurrency trading carries significant risk. Always do your own research and never invest more than you can afford to lose.

Key limitations:
- USDT.D is simulated via inverse BTC correlation (real data would improve accuracy)
- Backtests do not account for slippage beyond the 0.1% fee
- Market conditions may differ from historical patterns

---

## License

MIT — see [LICENSE](LICENSE) for details.
