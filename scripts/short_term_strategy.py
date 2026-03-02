#!/usr/bin/env python3
"""4H短线策略模块 — EMA交叉 + RSI过滤 + ATR止损
用ccxt从Bybit获取4H K线，生成交易信号
"""
import ccxt
import pandas as pd
from short_term_indicators import add_all_indicators


def fetch_4h_ohlcv(symbol: str, limit: int = 200) -> pd.DataFrame:
    """从Bybit获取4H K线数据"""
    exchange = ccxt.bybit({'enableRateLimit': True})
    raw = exchange.fetch_ohlcv(symbol, '4h', limit=limit)
    df = pd.DataFrame(raw, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    return df


def get_4h_signal(symbol: str) -> dict:
    """
    获取4H交易信号
    返回: {signal: BUY/SELL/HOLD, price, stop_loss, take_profit, rsi, atr, cross}
    """
    df = fetch_4h_ohlcv(symbol)
    df = add_all_indicators(df)
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    price = last['close']
    atr = last['atr']
    rsi = last['rsi']
    cross = last['cross']
    
    signal = 'HOLD'
    stop_loss = None
    take_profit = None
    
    # 做多: EMA9上穿EMA21 + RSI>50 + 价格>EMA50 + RSI<70
    if cross == 'golden_cross' and rsi > 50 and rsi < 70 and price > last['ema50']:
        signal = 'BUY'
        stop_loss = price - 1.5 * atr
        take_profit = price + 3.0 * atr
    
    # 做空: EMA9下穿EMA21 + RSI<50 + 价格<EMA50 + RSI>30
    elif cross == 'death_cross' and rsi < 50 and rsi > 30 and price < last['ema50']:
        signal = 'SELL'
        stop_loss = price + 1.5 * atr
        take_profit = price - 3.0 * atr
    
    return {
        'symbol': symbol,
        'signal': signal,
        'price': round(price, 2),
        'stop_loss': round(stop_loss, 2) if stop_loss else None,
        'take_profit': round(take_profit, 2) if take_profit else None,
        'rsi': round(rsi, 2),
        'atr': round(atr, 2),
        'cross': cross,
    }


if __name__ == '__main__':
    for sym in ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']:
        result = get_4h_signal(sym)
        print(f"{sym}: {result['signal']} @ {result['price']} | RSI={result['rsi']} | ATR={result['atr']}")
        if result['signal'] != 'HOLD':
            print(f"  SL={result['stop_loss']} TP={result['take_profit']}")
