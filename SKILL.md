---
name: crypto-trading
description: |
  Agent-driven crypto trading on Hyperliquid mainnet. Real money. BTC/ETH/SOL only.
  The agent IS the trader — reads raw indicators, judges market conditions, executes,
  sets dynamic trailing stops, and manages risk. 24/7 monitoring via cron.

  Use when: crypto trading, checking positions, analyzing indicators,
  managing stops, or any crypto market task.
---

# Crypto Trading — Agent Skill

You are a crypto trader on Hyperliquid mainnet. Real money. You make the calls.

## Quick Start (Restore from Scratch)

```bash
cd /Users/zhilongzheng/Projects/us-stock-trading
source .venv/bin/activate
```

Check cron is running:
```bash
openclaw cron list
```

Expected cron:
- `217d7f96` — Crypto Agent 15min Monitor, every 15min 24/7

If missing, recreate with the **Cron Prompt** below.

Check current state:
```python
PYTHONPATH=. python -c "from scripts.crypto.agent_tools import portfolio_summary; import json; print(json.dumps(portfolio_summary(), indent=2, default=str))"
```

## Account Details

- **Exchange**: Hyperliquid mainnet
- **Address**: `0xDf5031d5DF19FF6cB6fc4Fd9f55DcE5eed236a03`
- **Proxy**: `0x9f3220a8676c2Af258BfFA90d46DceeB737Fd161`
- **Coins**: BTC, ETH, SOL (szDecimals: BTC=5, ETH=4, SOL=2)
- **Max leverage**: 3x

## Agent Tools

All tools in `scripts/crypto/agent_tools.py`:

```python
PYTHONPATH=. python -c "from scripts.crypto.agent_tools import *; ..."
```

### Account & Positions
| Function | Returns |
|----------|---------|
| `hl_account()` | `{withdrawable, margin_used, free_margin}` |
| `hl_positions()` | All open positions |
| `hl_position("BTC")` | Single position or None |
| `portfolio_summary()` | Full snapshot: account + positions + prices + uPnL |
| `hl_recent_fills(hours=1)` | Recent fills — detect stop triggers |

### Market Data & Indicators
| Function | Returns |
|----------|---------|
| `hl_price("BTC")` | Latest price |
| `hl_prices()` | BTC/ETH/SOL prices |
| `get_indicators("BTC")` | Raw: TSI, OBV, WaveTrend, USDT.D, SMA200, ATR, regime |
| `get_support_resistance("BTC")` | Key S/R levels |
| `get_funding_rates()` | Current funding rates |
| `get_ohlcv("BTC", timeframe="4h", days=30)` | OHLCV DataFrame |

### Dynamic Stop
| Function | Returns |
|----------|---------|
| `suggest_stop("BTC", entry, current_price=mark)` | Trailing stop recommendation |

Trailing tiers (long positions):
- ROE < 10%: stop = entry − 1.5x ATR (protect capital)
- ROE 10–20%: stop = entry − 0.5x ATR (near breakeven)
- ROE 20–40%: stop = entry + 0.5x ATR (lock profit)
- ROE > 40%: stop = entry + 1.0x ATR (trail aggressively)

### Execution
| Function | Returns |
|----------|---------|
| `hl_open("BTC", margin_usd, leverage=3)` | Open position |
| `hl_close("BTC")` | Close entire position |
| `hl_reduce("BTC", size)` | Partial close |
| `hl_set_stop("BTC", price)` | Set stop (cancels old first) |
| `hl_cancel_orders("BTC")` | Cancel all orders for symbol |
| `hl_open_orders()` | List all open orders |

## Indicators (4-signal system)

| Indicator | Bullish When |
|-----------|-------------|
| **TSI** | TSI < 0 AND rising (depth matters: -40 > -5) |
| **OBV** | OBV > 9-period EMA |
| **USDT.D** | USDT.D TSI falling (money leaving stables) |
| **WaveTrend** | WT1 > WT2 (golden cross; stronger if < -60 oversold) |

## Hard Constraint

**ALWAYS set stop after opening any position.** Use `suggest_stop()` as minimum distance. Never leave a position without a stop.

## Agent Judgment (everything else)

Read raw indicator values and decide with conviction:
- TSI at -40 rising ≠ TSI at -5 rising
- WT cross at -60 (oversold) >> WT cross at -20 (neutral)
- OBV missing doesn't veto entry if other 3 signals are strong
- BEAR regime = more selective, not no-trade
- SOL is more volatile — size smaller or require stronger signals
- Total exposure: if >70% margin used, be very selective on new entries

## Telegram Reporting

**Always use**: `message(action='send', target='-5119023195', channel='telegram', message='...')`  
Never use usernames. Never use other targets.

- Trade executed OR unexpected fill → report immediately
- 4H window (:10 of hours 0,4,8,12,16,20 PST) → full portfolio report
- Otherwise → HEARTBEAT_OK (silent)

## Cron Prompt (217d7f96 — every 15min, 24/7)

```
You are running a crypto monitoring cycle. BTC/ETH/SOL, Hyperliquid mainnet, real money. 24/7.

⚠️ TELEGRAM: message(action='send', target='-5119023195', channel='telegram', message='...')

EVERY CYCLE:

STEP 1 — Recent fills:
  from scripts.crypto.agent_tools import hl_recent_fills
  fills = hl_recent_fills(hours=1)
  If Close fills found → report to Telegram immediately

STEP 2 — State:
  from scripts.crypto.agent_tools import portfolio_summary
  ps = portfolio_summary()

STEP 3 — Read raw indicators for ALL THREE coins:
  from scripts.crypto.agent_tools import get_indicators
  for coin in ['BTC', 'ETH', 'SOL']:
      ind = get_indicators(coin)

STEP 4 — YOUR JUDGMENT:
  Read actual indicator values — TSI depth, WT position, OBV conviction, USDT.D trend.
  For existing positions: hold, trail stop, reduce, or close?
  For new entries: signal quality worth the risk given regime + exposure?

STEP 5 — EXECUTE if conviction is there:
  from scripts.crypto.agent_tools import hl_open, hl_close, hl_reduce, hl_set_stop, suggest_stop
  HARD RULE: After any open → immediately set stop using suggest_stop() as minimum distance
  After any action → verify with portfolio_summary() + hl_open_orders()

REPORTING:
  - Trade executed OR fill detected → report immediately to '-5119023195'
  - 4H window (:10 of hours 0,4,8,12,16,20 PST) → post full report to '-5119023195'
  - Otherwise → HEARTBEAT_OK
```

## Architecture

```
scripts/crypto/
├── agent_tools.py         # Agent tool functions (use this)
├── hyperliquid.py         # HL SDK wrapper
├── hyperliquid_trader.py  # Legacy trading logic
└── crypto_trader.py       # Legacy signal counting

/Users/zhilongzheng/Projects/alpha-crypto-skill/scripts/
├── indicators.py          # TSI, OBV, WaveTrend, USDT.D
├── scanner.py             # Multi-coin scanner
└── backtest.py            # Backtesting
```
