# Backtest Results — Aggressive vs G vs H

## Methodology
- Data: BTC/USDT, ETH/USDT, SOL/USDT daily candles (~4 years)
- Fee: 0.1% per trade
- Starting capital: $10,000
- USDT.D: Simulated via inverse BTC correlation

## System Descriptions
| System | Type | Position Sizing | Thresholds |
|--------|------|----------------|------------|
| E (Adaptive) | Full position | 100% in/out | Bull: buy≥50/sell≤25, Bear: buy≥75/sell≤50 |
| G (Sizing) | Graduated | 10-100% by count | Fixed by confirmation count |
| H (E+G Hybrid) | Graduated + Regime | 0-50% by count+regime | Bull: max 50%, Bear: max 30% |

## Conservative Position Sizing
| Regime | 4/4 Bullish | 3/4 | 2/4 | 1/4 | 0/4 |
|--------|-------------|-----|-----|-----|-----|
| Bull (SMA200↑) | 50% | 30% | 15% | 0% | 0% |
| Bear (SMA200↓) | 30% | 15% | 0% | 0% | 0% |

## Key Findings
- **Aggressive**: Best raw returns in strong trends, but larger drawdowns
- **Conservative**: Best risk-adjusted returns (Sharpe, Calmar), lower drawdowns
- **Conservative** recommended for live trading due to conservative sizing and regime awareness

## Notes
- USDT.D is simulated (inverse BTC correlation) — real USDT.D data would improve accuracy
- Backtest does not account for slippage beyond the 0.1% fee
- Past performance does not guarantee future results
- Run `python scripts/backtest.py --system both --coin BTC --years 5` to regenerate
