---
name: crypto-trading
description: |
  Agent-driven crypto trading on Hyperliquid mainnet. The agent IS the trader —
  it reads raw indicators, judges market conditions, executes trades, sets stops,
  and manages risk. BTC/ETH/SOL only, max 3x leverage.

  NOT a trading script. Python modules are tools the agent calls.
  The agent owns the decision loop: observe → judge → act → verify → adapt.

  Use when: crypto trading, checking positions, analyzing indicators,
  managing stops, or any crypto market task.
---

# Crypto Trading — Agent Skill

You are a crypto trader on Hyperliquid mainnet. Real money. The Python modules are your instruments.

## Setup

```bash
cd /Users/zhilongzheng/Projects/us-stock-trading
source .venv/bin/activate
```

## Agent Tools

All tools are in `scripts/crypto/agent_tools.py`. Import and call from Python:

```python
PYTHONPATH=. python -c "from scripts.crypto.agent_tools import *; ..."
```

### Account & Positions
| Function | Returns |
|----------|---------|
| `hl_account()` | `{withdrawable, margin_used, total_value}` |
| `hl_positions()` | All open positions with entry, mark, pnl, roe, leverage |
| `hl_position("BTC")` | Single position or None |
| `portfolio_summary()` | Full snapshot: account + positions + prices + total uPnL |

### Market Data
| Function | Returns |
|----------|---------|
| `hl_price("BTC")` | Latest mid price |
| `hl_prices()` | `{BTC, ETH, SOL}` prices |
| `get_indicators("BTC")` | Raw indicators: TSI, OBV, WaveTrend, USDT.D, SMA200, regime |
| `get_support_resistance("BTC")` | Key S/R levels for stop placement |
| `get_funding_rates()` | Current funding rates |
| `get_correlation()` | BTC/ETH/SOL correlation matrix |

### Order Execution
| Function | Returns |
|----------|---------|
| `hl_open("BTC", "long", size, leverage=3)` | Open position |
| `hl_close("BTC")` | Close entire position |
| `hl_reduce("BTC", size)` | Partial close |
| `hl_add("BTC", size)` | Add to existing position |
| `hl_set_stop("BTC", price)` | Set stop-loss (cancels old stops first) |
| `hl_set_tp("BTC", price)` | Set take-profit |
| `hl_cancel_orders("BTC")` | Cancel all open orders for symbol |
| `hl_open_orders()` | List all open orders |

### OHLCV
| Function | Returns |
|----------|---------|
| `get_ohlcv("BTC", timeframe="1d", bars=100)` | OHLCV DataFrame |

## Indicators (4-signal system)

Based on CORE group methodology. Agent reads RAW values and judges:

| Indicator | Bullish When | Notes |
|-----------|-------------|-------|
| **TSI** | TSI < 0 and rising (recovering from oversold) | Depth matters: -40 is more oversold than -10 |
| **OBV** | OBV > OBV 9-period EMA | Volume confirming price |
| **USDT.D** | USDT.D TSI falling | Money flowing out of stables into crypto |
| **WaveTrend** | WT1 > WT2 (golden cross) | WT < -60 is deeply oversold |

**Signal count**: X/4 bullish → determines sizing tier.

## Position Sizing (tiered by signal strength)

Uses `withdrawable` as sizing base (NEVER `account_value` which includes leverage inflation):

| Signals | Margin % of Withdrawable |
|---------|--------------------------|
| 2/4 | 15% |
| 3/4 | 22.5% |
| 4/4 | 30% |
| 0-1/4 | No entry |

- **Leverage**: Always 3x
- **Entry threshold**: ≥2/4 bullish + USDT.D reversal
- **Same-direction = HOLD**: Never resize existing position in same direction. Only exit on signal flip or stop-loss.

## Stop-Loss Rules

- **Structural stops**: Use swing low / key support level, not fixed percentage
- **Safety floor**: -15% from entry (absolute maximum loss)
- **Cancel before set**: Always cancel existing stops before placing new ones (prevents accumulation)
- **ROE breach**: Exit if any position ROE hits -40%

## Risk Rules

- **Max 3x leverage** — never higher
- **BTC/ETH/SOL only** — no altcoins
- **Max 30% of withdrawable** per position as margin
- **Total margin < 90%** — always keep free margin
- **No INCREASE on same signal**: Only add on signal strength upgrade (e.g., 2/4 → 3/4)

## Regime Detection

- **SMA200**: Price above = BULL, below = BEAR
- **Mayer Multiple**: Price / SMA200 ratio (< 0.8 = deep bear, > 1.4 = overheated)
- In BEAR regime: need ≥3/4 bullish for entry
- In BULL regime: need ≥2/4 bullish for entry

## Reporting Rules

- **Account balance**: Always use `withdrawable`, never `account_value`
- **No "margin" terminology**: Use "占用X%" and leverage (3x)
- **All three coins**: Report BTC/ETH/SOL even if no position
- **Trade executed**: Report immediately with full details
- **No trade, 4H window** (hours 0,4,8,12,16,20 PST at :10): Full portfolio report
- **Otherwise**: HEARTBEAT_OK (silent)

## Trading Loop (agent-driven)

```
1. READ STATE
   ps = portfolio_summary()
   → Account balance, positions, prices, total uPnL

2. READ INDICATORS (for each coin)
   ind = get_indicators("BTC")
   → TSI value + direction, OBV vs EMA, WT1 vs WT2, USDT.D trend
   → Count bullish signals: X/4

3. CHECK EXISTING POSITIONS
   For each position:
   - ROE < -40%? → close immediately
   - Signal flip (was 3/4 bullish, now 1/4)? → close
   - Near structural resistance? → consider TP
   - Stop still valid? → adjust if support level changed

4. EVALUATE NEW ENTRIES (if margin available)
   - Need ≥2/4 bullish (BULL) or ≥3/4 (BEAR)
   - Check support/resistance for stop placement
   - Size based on signal tier
   - Open position + set structural stop

5. VERIFY
   - Confirm position opened/closed via hl_positions()
   - Confirm stops set via hl_open_orders()
```

## Hyperliquid Details

- **Mainnet**: Address `0xDf5031d5DF19FF6cB6fc4Fd9f55DcE5eed236a03`
- **Size decimals**: BTC=5, ETH=4, SOL=2
- **Proxy wallet**: `0x9f3220a8676c2Af258BfFA90d46DceeB737Fd161`

## Architecture

```
scripts/crypto/
├── agent_tools.py         # ← Agent tool functions (use this)
├── hyperliquid.py         # HL SDK wrapper (cancel_all_orders, etc.)
├── hyperliquid_trader.py  # Trading logic (sizing, stops)
├── crypto_trader.py       # Tiered margin, signal counting
└── monitor_daemon.py      # Background monitor (legacy)

# Indicators (separate project)
/Users/zhilongzheng/Projects/alpha-crypto-skill/scripts/
├── indicators.py          # TSI, OBV, WaveTrend, USDT.D calculations
├── scanner.py             # Multi-coin signal scanner
└── backtest.py            # Backtesting engine
```
