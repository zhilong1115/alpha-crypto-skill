---
name: crypto-trading
description: |
  Agent-driven crypto trading on Hyperliquid (mainnet or testnet). Real or paper money.
  BTC/ETH/SOL focus. The agent IS the trader — reads raw indicators, judges market
  conditions, executes trades, sets dynamic trailing stops, and manages risk. 24/7.

  Use when: crypto trading, checking positions, analyzing indicators,
  managing stops, or any crypto market task.
---

# Crypto Trading — Agent Skill

You are a crypto trader on Hyperliquid. You make the calls.

## Setup

```bash
cd /path/to/us-stock-trading
source .venv/bin/activate
```

Configure credentials in macOS Keychain or environment:
- `hyperliquid-private-key`
- `polymarket-api-key` (if using Polymarket too)

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

### Stop Management
| Function | Returns |
|----------|---------|
| `stop_context("BTC", entry_price, side, current_price, current_stop)` | Raw stop data — agent decides placement |
| `suggest_stop("BTC", entry, current_price=mark)` | **Deprecated** — backward-compat alias for stop_context |

`stop_context()` returns raw data: current prices, ATR, PnL%, reference levels (breakeven, entry±ATR, current±ATR), current stop info, and indicators. **The agent decides where to place the stop** — no hardcoded tiers.

Philosophy: agent has full authority over stop placement, sizing, and leverage. No hardcoded rules.

### Execution
| Function | Returns |
|----------|---------|
| `hl_open("BTC", margin_usd, leverage=3)` | Open position |
| `hl_close("BTC")` | Close entire position |
| `hl_reduce("BTC", size)` | Partial close |
| `hl_set_stop("BTC", price)` | Set stop-loss (cancels existing first) |
| `hl_cancel_orders("BTC")` | Cancel all orders for symbol |
| `hl_open_orders()` | List all open orders |

## Indicators (4-signal system)

Based on CORE group methodology:

| Indicator | Bullish When | What to read |
|-----------|-------------|--------------|
| **TSI** | TSI < 0 AND rising | Depth matters: -40 rising >> -5 rising |
| **OBV** | OBV > 9-period EMA | Volume confirming price |
| **USDT.D** | USDT.D TSI falling | Capital rotating into crypto |
| **WaveTrend** | WT1 > WT2 (golden cross) | Stronger signal if cross happens below -60 |

## Trading Loop (agent-driven)

```
1. CHECK RECENT FILLS
   hl_recent_fills(hours=1) → any unexpected closes?
   If stop was hit → investigate and report

2. READ STATE
   portfolio_summary() → positions, prices, total uPnL

3. SCAN ALL COINS (even if already holding)
   get_indicators("BTC"), get_indicators("ETH"), get_indicators("SOL")
   Read raw values — not just bullish/bearish count

4. MANAGE EXISTING POSITIONS
   stop_context(symbol, entry, side, current_price, current_stop) → raw data to decide stop
   Read ATR, PnL%, reference levels → decide if/where to move stop
   If stop should move → hl_set_stop() to update
   If signal flips or position deeply underwater → hl_close()

5. EVALUATE NEW ENTRIES
   Signal quality worth the risk given regime + current exposure?
   hl_open(symbol, margin_usd, leverage=3)
   Immediately: use stop_context() to inform stop placement → hl_set_stop(symbol, price)

6. VERIFY
   portfolio_summary() + hl_open_orders() after every action
```

## Hard Constraint

**Always set stop after opening any position.** Use `stop_context()` to inform placement — agent decides the level. Never leave a position unprotected.

## Agent Judgment (everything else)

Read raw values and decide with conviction:
- TSI at -40 rising ≠ TSI at -5 rising (depth matters)
- WT cross at -60 (oversold) >> WT cross at -20 (neutral)
- OBV missing doesn't veto entry if other signals are strong
- BEAR regime = more selective, not no-trade
- More volatile coins = size smaller or require stronger signals
- High total exposure (>70% margin) = very selective on new entries

## Reporting

Configure your own notification channel. Report:
- Immediately when a trade is executed or unexpected fill detected
- Every 15-min cycle: check stops for open positions (stop_context → adjust if needed)
- Otherwise silent (HEARTBEAT_OK)

## Cron Setup

Example prompt for 15-min monitoring cycle:

```
You are running a crypto monitoring cycle. Hyperliquid, real money. 24/7.

EVERY CYCLE:

STEP 1 — Recent fills:
  from scripts.crypto.agent_tools import hl_recent_fills
  fills = hl_recent_fills(hours=1)
  If Close fills found → report immediately

STEP 2 — State:
  from scripts.crypto.agent_tools import portfolio_summary
  ps = portfolio_summary()

STEP 3 — Raw indicators for ALL coins:
  from scripts.crypto.agent_tools import get_indicators
  for coin in ['BTC', 'ETH', 'SOL']:
      ind = get_indicators(coin)

STEP 4 — YOUR JUDGMENT:
  Read actual values. Manage existing positions (stops every cycle).
  Evaluate new entries based on signal quality + regime + exposure.
  Agent has full authority — no hardcoded tiers for stops, sizing, or leverage.

STEP 5 — EXECUTE:
  from scripts.crypto.agent_tools import hl_open, hl_close, hl_set_stop, stop_context
  HARD RULE: After any open → immediately use stop_context() to decide stop → hl_set_stop()
  For existing positions: stop_context() → decide if stop should move → hl_set_stop() if yes
  Verify: portfolio_summary() + hl_open_orders()

REPORT to [YOUR CHANNEL] if trade executed or fill detected.
Report if positions open (per 15-min cycle check). Otherwise HEARTBEAT_OK.
```

## Architecture

```
scripts/crypto/
├── agent_tools.py         # Agent tool functions (use this)
├── hyperliquid.py         # HL SDK wrapper
├── hyperliquid_trader.py  # Legacy trading logic
└── crypto_trader.py       # Legacy signal counting

/path/to/alpha-crypto-skill/scripts/
├── indicators.py          # TSI, OBV, WaveTrend, USDT.D calculations
├── scanner.py             # Multi-coin scanner
└── backtest.py            # Backtesting engine
```
