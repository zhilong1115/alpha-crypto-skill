# Trading Rules (CORE Group)

Based on 3 years of trading experience (2023-2026) from the CORE group.

## 10 Core Rules

### 1. 现货为王，远离合约 — Spot Only
No leverage, no futures, no contracts. "做合约没人保证活着" (No one guarantees survival with contracts). All major crypto funds trade spot only.

### 2. 右侧建仓 — Right-Side Entry
Enter after breakout confirmation, never bottom-fish. Wait for price to reclaim key moving averages (4H MA120, daily EMA21) before entering.

### 3. 止损纪律 — Stop-Loss Discipline
Every position must have a stop-loss. Maximum 5% loss per trade. "亏5%博赚几十%" (Risk 5% to potentially gain tens of percent).

### 4. 不格局 — Don't Diamond-Hand
Take profits at targets. The group's #1 lesson: "一格局就往死里亏" (Diamond-handing leads to devastating losses). Do wave trading, not holding forever.

### 5. 大饼引领 — BTC Leads
Don't buy altcoins if BTC is weak. "大饼不给信号，山寨庄家不敢拉" (If BTC doesn't signal, altcoin market makers won't pump).

### 6. 40天周期 — ~40 Day Cycle
Markets tend to move in ~40-day cycles. Uptrends last 40-57 days, downtrends 12-27 days. Be cautious when approaching cycle limits.

### 7. MA120硬止损 — MA120 Hard Stop
If price closes below the 4-hour MA120, exit immediately. Non-negotiable. This is the bull/bear dividing line on shorter timeframes.

### 8. 三大交易所 — Top 3 Exchanges
Only trade coins listed on all three: Binance, Coinbase, and OKX. This ensures liquidity, legitimacy, and reduces rug-pull risk.

### 9. 无线性解锁 — No Linear Unlocks
Avoid tokens with heavy linear vesting/unlock schedules. Daily token unlocks dilute value continuously (e.g., OP had 4M daily unlocks).

### 10. 最大仓位50% — Max 50% Position
Never allocate more than 50% of portfolio to a single position. Always keep dry powder for opportunities or to average down.

## Additional Wisdom

- **震荡不操作**: Don't trade during consolidation/chop. "不操作就是最好的操作" (Not trading is the best trading).
- **买点可以，卖点不行**: Entries are usually good; it's the exits that need work. Focus on sell signals and stop-losses.
- **只有机器人能不带感情**: Only bots can trade without emotion — the ultimate reason for algorithmic trading.

## Risk Management Parameters
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
