"""Backtest engine."""
import numpy as np
import pandas as pd


def run_backtest(df: pd.DataFrame, score_fn, system_name: str, fee=0.001):
    """Run backtest. Returns metrics dict."""
    capital = 10000.0
    position = 0.0  # fraction of capital in market
    entry_price = 0.0
    equity = [capital]
    trades = []
    current_trade = None

    for i in range(1, len(df)):
        row = df.iloc[i]
        if any(np.isnan(row.get(c, np.nan)) for c in ['tsi', 'obv_ema9', 'wt1', 'wt2', 'usdt_d_tsi']):
            equity.append(equity[-1])
            continue

        score, buy_thresh, sell_thresh = score_fn(row)

        # System G: position sizing by confirmation count
        if system_name == 'G':
            count = score
            target_pos = {4: 1.0, 3: 0.5, 2: 0.25, 1: 0.1, 0: 0.0}.get(int(count), 0)

            if target_pos > position:
                # Buy more
                buy_frac = target_pos - position
                cost = equity[-1] * buy_frac * fee
                equity[-1] -= cost
                position = target_pos
                entry_price = row['close']
                if current_trade is None:
                    current_trade = {'entry': row['close'], 'entry_idx': i}
            elif target_pos < position:
                # Sell some
                sell_frac = position - target_pos
                pnl = sell_frac * equity[-1] * (row['close'] / entry_price - 1) if entry_price > 0 else 0
                cost = equity[-1] * sell_frac * fee
                equity[-1] += pnl - cost
                position = target_pos
                if position == 0 and current_trade:
                    ret = row['close'] / current_trade['entry'] - 1
                    trades.append(ret)
                    current_trade = None

            # Update equity with position PnL
            if position > 0 and i > 1:
                price_ret = df.iloc[i]['close'] / df.iloc[i-1]['close'] - 1
                equity.append(equity[-1] * (1 + position * price_ret))
            else:
                equity.append(equity[-1])
        else:
            # Standard systems
            if position == 0 and score >= buy_thresh:
                # Buy
                position = 1.0
                entry_price = row['close']
                cost = equity[-1] * fee
                equity[-1] -= cost
                current_trade = {'entry': row['close']}
            elif position > 0 and score <= sell_thresh:
                # Sell
                ret = row['close'] / entry_price - 1
                cost = equity[-1] * fee
                equity[-1] -= cost
                trades.append(ret)
                position = 0
                current_trade = None

            # Update equity
            if position > 0 and i > 1:
                price_ret = row['close'] / df.iloc[i-1]['close'] - 1
                equity.append(equity[-1] * (1 + price_ret))
            else:
                equity.append(equity[-1])

    # Close any open position
    if position > 0 and len(df) > 1:
        ret = df.iloc[-1]['close'] / entry_price - 1
        trades.append(ret)

    equity = np.array(equity)
    return calc_metrics(equity, trades)


def calc_metrics(equity, trades):
    total_return = (equity[-1] / equity[0] - 1) * 100

    # Max drawdown
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    max_dd = abs(dd.min()) * 100

    # Daily returns for Sharpe
    daily_ret = np.diff(equity) / equity[:-1]
    sharpe = np.sqrt(365) * np.nanmean(daily_ret) / (np.nanstd(daily_ret) + 1e-10)

    # Win rate
    if trades:
        wins = sum(1 for t in trades if t > 0)
        win_rate = wins / len(trades) * 100
        gross_profit = sum(t for t in trades if t > 0)
        gross_loss = abs(sum(t for t in trades if t < 0))
        profit_factor = gross_profit / (gross_loss + 1e-10)
    else:
        win_rate = 0
        profit_factor = 0

    calmar = total_return / (max_dd + 1e-10)

    return {
        'Total Return %': round(total_return, 2),
        'Max Drawdown %': round(max_dd, 2),
        'Sharpe': round(sharpe, 2),
        'Win Rate %': round(win_rate, 1),
        'Trades': len(trades),
        'Profit Factor': round(profit_factor, 2),
        'Calmar': round(calmar, 2),
    }
