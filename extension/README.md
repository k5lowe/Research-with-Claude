# Stock Trend Overlay for Yahoo Finance

A Chrome extension that overlays live trend analysis and a next-candle
direction prediction on any Yahoo Finance chart or quote page — including the
advanced chart. Because the data is fetched from inside your own browser
session, it avoids the blocking problems that server-side scrapers (like
yfinance) run into.

**Informational only. Not financial advice. No trading, no money involved.**

## Install (Chrome / Edge / Brave)

1. Open `chrome://extensions` (or `edge://extensions`)
2. Turn on **Developer mode** (toggle, top-right)
3. Click **Load unpacked**
4. Select this `extension/` folder
5. Go to any chart, e.g. https://finance.yahoo.com/chart/AAPL — the panel
   appears in the top-right

## What the panel shows

- **Next-candle direction** — ▲ UP / ▼ DOWN with confidence %, target price,
  and which signal is driving the call
- **Bullish probability meter** — 0–100% weighted ensemble of six signals
  (EMA trend stack, RSI, MACD, Bollinger position, volume, VWAP), with
  mean-reversion signals dampened when they fight a strong trend
- **Timeframe consensus** — the same prediction run on 1m, 5m, and 15m bars;
  click a cell to switch the primary timeframe
- **Signal breakdown** — each signal's score and a plain-English reading
- **Prediction hit rate** — every prediction is stored and later scored
  against the candle that actually printed, so you can see how accurate it
  has really been (✓/✗ strip shows the last 10)

The panel is draggable (grab the header), collapsible (– button), refreshes
every 30 seconds, and follows you as you navigate between symbols.

## Notes

- Data comes from Yahoo's own chart API (`query1.finance.yahoo.com`), the
  same source the page itself uses. Real-time-ness matches what Yahoo shows.
- When the market is closed, the panel analyzes the last session and says so.
- Prediction history is stored locally in your browser (nothing leaves your
  machine).
- Short-horizon direction prediction is inherently noisy — a hit rate in the
  mid-50s is realistic. Watch the hit-rate line before trusting any signal.
