# Research with Claude — Stock Trend Analysis

Two tools for analyzing stock trends and predicting short-term direction.
**Neither one trades or touches real money — they're informational only.**

## 1. Browser extension (recommended)

`extension/` — overlays live trend analysis and next-candle UP/DOWN
predictions directly on Yahoo Finance charts, using data fetched from inside
your own browser session (no API keys, no scraping blocks).

See [extension/README.md](extension/README.md) for install steps.

## 2. Streamlit dashboard

`dashboard.py` + `analysis.py` — a standalone web dashboard with candlestick
charts, indicators, a probability gauge, and a watchlist.

```bash
pip install -r requirements.txt
streamlit run dashboard.py
```

Data via yfinance (Yahoo Finance). If tickers fail to load, upgrade first:
`pip install --upgrade yfinance`.

## How the prediction works

Both tools share the same engine (Python in `analysis.py`, JS port in
`extension/indicators.js`):

- **Bullish probability (0–100%)** — weighted ensemble of six signals:
  EMA 9/21/50 trend stack (25%), RSI (20%), MACD (20%), Bollinger position
  (15%), volume confirmation (10%), VWAP (10%). Mean-reversion signals are
  dampened when they oppose a strong trend.
- **Next-candle prediction** — five short-term features (regression slope,
  EMA 5/10 micro-trend, RSI shift, MACD histogram acceleration, recent candle
  bodies) combined through a sigmoid into an UP/DOWN call with confidence.
- **Hit-rate tracking (extension)** — predictions are scored against the
  candle that actually printed, so accuracy is measured, not assumed.

## Disclaimer

Short-horizon price direction is mostly noise; even good signals are only
right slightly more often than a coin flip. Use these tools to inform your
own judgment, never as a reason to trade.
