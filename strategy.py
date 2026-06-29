import pandas as pd
import numpy as np
from enum import Enum


class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_signal(
    bars: pd.DataFrame,
    ema_short: int,
    ema_long: int,
    rsi_period: int,
    rsi_overbought: float,
    rsi_oversold: float,
) -> Signal:
    """
    Returns BUY when short EMA crosses above long EMA and RSI is not overbought.
    Returns SELL when short EMA crosses below long EMA and RSI is not oversold.
    Otherwise HOLD.

    bars: DataFrame with at least a 'close' column, sorted oldest-first.
    """
    if len(bars) < max(ema_long, rsi_period) + 2:
        return Signal.HOLD

    close = bars["close"]
    ema_s = ema(close, ema_short)
    ema_l = ema(close, ema_long)
    rsi_vals = rsi(close, rsi_period)

    # Current and previous bar
    prev_s, curr_s = ema_s.iloc[-2], ema_s.iloc[-1]
    prev_l, curr_l = ema_l.iloc[-2], ema_l.iloc[-1]
    curr_rsi = rsi_vals.iloc[-1]

    bullish_cross = prev_s <= prev_l and curr_s > curr_l
    bearish_cross = prev_s >= prev_l and curr_s < curr_l

    if bullish_cross and curr_rsi < rsi_overbought:
        return Signal.BUY
    if bearish_cross and curr_rsi > rsi_oversold:
        return Signal.SELL
    return Signal.HOLD
