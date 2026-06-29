"""
Technical analysis engine.
Returns a probability score (0–100) for bullish movement and a breakdown of signals.
"""

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class SignalResult:
    name: str
    value: float       # raw indicator value
    score: float       # 0–100, higher = more bullish
    weight: float
    label: str         # human-readable summary


@dataclass
class AnalysisResult:
    symbol: str
    price: float
    change_pct: float
    probability: float          # 0–100 weighted bullish probability
    signals: list[SignalResult]
    trend: str                  # "Bullish" / "Bearish" / "Neutral"
    bars: pd.DataFrame


# ── Indicator helpers ────────────────────────────────────────────────────────

def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    gain = d.clip(lower=0).ewm(com=n - 1, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(com=n - 1, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def macd(s: pd.Series, fast=12, slow=26, signal=9):
    m = ema(s, fast) - ema(s, slow)
    sig = ema(m, signal)
    return m, sig, m - sig


def bollinger(s: pd.Series, n: int = 20, k: float = 2.0):
    mid = s.rolling(n).mean()
    std = s.rolling(n).std()
    return mid + k * std, mid, mid - k * std


def vwap(bars: pd.DataFrame) -> pd.Series:
    tp = (bars["high"] + bars["low"] + bars["close"]) / 3
    return (tp * bars["volume"]).cumsum() / bars["volume"].cumsum()


def atr(bars: pd.DataFrame, n: int = 14) -> pd.Series:
    tr = pd.concat([
        bars["high"] - bars["low"],
        (bars["high"] - bars["close"].shift()).abs(),
        (bars["low"] - bars["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(com=n - 1, adjust=False).mean()


# ── Signal scorers ───────────────────────────────────────────────────────────

def score_ema_trend(bars: pd.DataFrame) -> SignalResult:
    """Three-EMA stack: 9 > 21 > 50 = fully bullish (100), inverse = 0."""
    c = bars["close"]
    e9, e21, e50 = ema(c, 9).iloc[-1], ema(c, 21).iloc[-1], ema(c, 50).iloc[-1]
    price = c.iloc[-1]

    # Count bullish conditions (price > each EMA, EMAs in order)
    conditions = [price > e9, price > e21, price > e50, e9 > e21, e21 > e50]
    score = sum(conditions) / len(conditions) * 100

    stacked = "bullish stack" if score == 100 else "bearish stack" if score == 0 else "mixed"
    return SignalResult("EMA Trend", price, score, weight=0.25,
                        label=f"9/21/50 EMA {stacked}")


def score_rsi(bars: pd.DataFrame) -> SignalResult:
    val = rsi(bars["close"]).iloc[-1]
    # 50 = neutral (50), 30 = oversold (bullish, 85), 70 = overbought (bearish, 15)
    if val <= 30:
        score = 85
        label = f"RSI {val:.1f} — oversold (potential reversal up)"
    elif val <= 45:
        score = 65
        label = f"RSI {val:.1f} — mild bullish momentum"
    elif val <= 55:
        score = 50
        label = f"RSI {val:.1f} — neutral"
    elif val <= 70:
        score = 35
        label = f"RSI {val:.1f} — mild bearish momentum"
    else:
        score = 15
        label = f"RSI {val:.1f} — overbought (potential reversal down)"
    return SignalResult("RSI", val, score, weight=0.20, label=label)


def score_macd(bars: pd.DataFrame) -> SignalResult:
    m, sig, hist = macd(bars["close"])
    h = hist.iloc[-1]
    prev_h = hist.iloc[-2]
    m_val = m.iloc[-1]

    if m_val > 0 and h > 0 and h > prev_h:
        score, label = 85, f"MACD bullish & accelerating (hist={h:.3f})"
    elif m_val > 0 and h > 0:
        score, label = 65, f"MACD bullish (hist={h:.3f})"
    elif m_val > 0 and h < 0:
        score, label = 45, f"MACD above zero but losing momentum"
    elif m_val < 0 and h > 0:
        score, label = 55, f"MACD below zero but recovering"
    else:
        score, label = 20, f"MACD bearish (hist={h:.3f})"
    return SignalResult("MACD", m_val, score, weight=0.20, label=label)


def score_bollinger(bars: pd.DataFrame) -> SignalResult:
    upper, mid, lower = bollinger(bars["close"])
    price = bars["close"].iloc[-1]
    u, m, l = upper.iloc[-1], mid.iloc[-1], lower.iloc[-1]
    band_width = u - l

    # Position within bands: 0 = at lower, 1 = at upper
    position = (price - l) / band_width if band_width > 0 else 0.5

    if position < 0.1:
        score, label = 80, f"Price near lower band — potential bounce"
    elif position < 0.35:
        score, label = 62, f"Price in lower half of bands"
    elif position < 0.65:
        score, label = 50, f"Price mid-band — neutral"
    elif position < 0.9:
        score, label = 38, f"Price in upper half of bands"
    else:
        score, label = 20, f"Price near upper band — potential pullback"
    return SignalResult("Bollinger Bands", position, score, weight=0.15,
                        label=label)


def score_volume(bars: pd.DataFrame) -> SignalResult:
    vol = bars["volume"]
    avg_vol = vol.rolling(20).mean().iloc[-1]
    curr_vol = vol.iloc[-1]
    price_change = bars["close"].iloc[-1] - bars["close"].iloc[-2]
    ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0

    if ratio > 1.5 and price_change > 0:
        score, label = 80, f"High volume ({ratio:.1f}x avg) on up move"
    elif ratio > 1.5 and price_change < 0:
        score, label = 20, f"High volume ({ratio:.1f}x avg) on down move"
    elif ratio > 1.0:
        score, label = 55, f"Above-average volume ({ratio:.1f}x)"
    else:
        score, label = 45, f"Below-average volume ({ratio:.1f}x)"
    return SignalResult("Volume", ratio, score, weight=0.10, label=label)


def score_vwap(bars: pd.DataFrame) -> SignalResult:
    vwap_line = vwap(bars)
    price = bars["close"].iloc[-1]
    v = vwap_line.iloc[-1]
    pct = (price - v) / v * 100

    if pct > 1.0:
        score, label = 70, f"Price {pct:.2f}% above VWAP"
    elif pct > 0:
        score, label = 58, f"Price {pct:.2f}% above VWAP"
    elif pct > -1.0:
        score, label = 42, f"Price {pct:.2f}% below VWAP"
    else:
        score, label = 30, f"Price {pct:.2f}% below VWAP"
    return SignalResult("VWAP", pct, score, weight=0.10, label=label)


# ── Main entry point ─────────────────────────────────────────────────────────

def analyze(symbol: str, bars: pd.DataFrame) -> AnalysisResult:
    """Run all signals and return a combined bullish probability."""
    price = bars["close"].iloc[-1]
    prev_close = bars["close"].iloc[-2]
    change_pct = (price - prev_close) / prev_close * 100

    scorers = [
        score_ema_trend,
        score_rsi,
        score_macd,
        score_bollinger,
        score_volume,
        score_vwap,
    ]
    signals = [fn(bars) for fn in scorers]

    total_weight = sum(s.weight for s in signals)
    probability = sum(s.score * s.weight for s in signals) / total_weight

    if probability >= 60:
        trend = "Bullish"
    elif probability <= 40:
        trend = "Bearish"
    else:
        trend = "Neutral"

    return AnalysisResult(
        symbol=symbol,
        price=price,
        change_pct=change_pct,
        probability=probability,
        signals=signals,
        trend=trend,
        bars=bars,
    )
