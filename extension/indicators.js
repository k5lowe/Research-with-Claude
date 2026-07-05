// Technical-analysis engine (JS port of analysis.py).
// Bars are parallel arrays: { t, o, h, l, c, v } — oldest first, no nulls.

(function () {
  "use strict";

  // ── Math helpers ──────────────────────────────────────────────────────────

  function ema(arr, n) {
    const alpha = 2 / (n + 1);
    const out = new Array(arr.length);
    let prev = arr[0];
    for (let i = 0; i < arr.length; i++) {
      prev = i === 0 ? arr[0] : alpha * arr[i] + (1 - alpha) * prev;
      out[i] = prev;
    }
    return out;
  }

  // Wilder smoothing (pandas ewm(com=n-1): alpha = 1/n)
  function wilder(arr, n) {
    const alpha = 1 / n;
    const out = new Array(arr.length);
    let prev = arr[0];
    for (let i = 0; i < arr.length; i++) {
      prev = i === 0 ? arr[0] : alpha * arr[i] + (1 - alpha) * prev;
      out[i] = prev;
    }
    return out;
  }

  function rsi(close, n) {
    n = n || 14;
    const gains = [0], losses = [0];
    for (let i = 1; i < close.length; i++) {
      const d = close[i] - close[i - 1];
      gains.push(Math.max(d, 0));
      losses.push(Math.max(-d, 0));
    }
    const avgG = wilder(gains, n);
    const avgL = wilder(losses, n);
    return close.map((_, i) => {
      if (avgL[i] === 0) return avgG[i] === 0 ? 50 : 100;
      const rs = avgG[i] / avgL[i];
      return 100 - 100 / (1 + rs);
    });
  }

  function macd(close, fast, slow, signal) {
    fast = fast || 12; slow = slow || 26; signal = signal || 9;
    const ef = ema(close, fast), es = ema(close, slow);
    const line = ef.map((v, i) => v - es[i]);
    const sig = ema(line, signal);
    const hist = line.map((v, i) => v - sig[i]);
    return { line, sig, hist };
  }

  function rollingMeanStd(arr, n) {
    const mean = new Array(arr.length).fill(NaN);
    const std = new Array(arr.length).fill(NaN);
    for (let i = n - 1; i < arr.length; i++) {
      let s = 0;
      for (let j = i - n + 1; j <= i; j++) s += arr[j];
      const m = s / n;
      let v = 0;
      for (let j = i - n + 1; j <= i; j++) v += (arr[j] - m) * (arr[j] - m);
      mean[i] = m;
      std[i] = Math.sqrt(v / (n - 1)); // sample std, matches pandas default
    }
    return { mean, std };
  }

  function bollingerLast(close, n, k) {
    n = n || 20; k = k || 2;
    const { mean, std } = rollingMeanStd(close, n);
    const i = close.length - 1;
    return { upper: mean[i] + k * std[i], mid: mean[i], lower: mean[i] - k * std[i] };
  }

  function vwapLast(bars) {
    let pv = 0, vv = 0;
    for (let i = 0; i < bars.c.length; i++) {
      const tp = (bars.h[i] + bars.l[i] + bars.c[i]) / 3;
      pv += tp * bars.v[i];
      vv += bars.v[i];
    }
    return vv > 0 ? pv / vv : bars.c[bars.c.length - 1];
  }

  function atrLast(bars, n) {
    n = n || 14;
    const tr = [bars.h[0] - bars.l[0]];
    for (let i = 1; i < bars.c.length; i++) {
      tr.push(Math.max(
        bars.h[i] - bars.l[i],
        Math.abs(bars.h[i] - bars.c[i - 1]),
        Math.abs(bars.l[i] - bars.c[i - 1])
      ));
    }
    const sm = wilder(tr, n);
    return sm[sm.length - 1];
  }

  function linregSlope(arr) {
    const n = arr.length;
    if (n < 2) return 0;
    const xm = (n - 1) / 2;
    let ym = 0;
    for (const y of arr) ym += y;
    ym /= n;
    let num = 0, den = 0;
    for (let i = 0; i < n; i++) {
      num += (i - xm) * (arr[i] - ym);
      den += (i - xm) * (i - xm);
    }
    return den === 0 ? 0 : num / den;
  }

  function safe(v) {
    return Number.isFinite(v) ? v : 0;
  }

  const last = (a) => a[a.length - 1];

  // ── Signal scorers (each returns {name, score 0-100 bullish, weight, label}) ──

  function scoreEmaTrend(bars) {
    const c = bars.c;
    const e9 = last(ema(c, 9)), e21 = last(ema(c, 21)), e50 = last(ema(c, 50));
    const price = last(c);
    const conds = [price > e9, price > e21, price > e50, e9 > e21, e21 > e50];
    const score = (conds.filter(Boolean).length / conds.length) * 100;
    const stacked = score === 100 ? "bullish stack" : score === 0 ? "bearish stack" : "mixed";
    return { name: "EMA Trend", score, weight: 0.25, label: `9/21/50 EMA ${stacked}` };
  }

  function scoreRsi(bars) {
    const val = last(rsi(bars.c, 14));
    let score, label;
    if (val <= 30)      { score = 85; label = `RSI ${val.toFixed(1)} — oversold`; }
    else if (val <= 45) { score = 65; label = `RSI ${val.toFixed(1)} — mild bullish`; }
    else if (val <= 55) { score = 50; label = `RSI ${val.toFixed(1)} — neutral`; }
    else if (val <= 70) { score = 35; label = `RSI ${val.toFixed(1)} — mild bearish`; }
    else                { score = 15; label = `RSI ${val.toFixed(1)} — overbought`; }
    return { name: "RSI", score, weight: 0.20, label };
  }

  function scoreMacd(bars) {
    const { line, hist } = macd(bars.c);
    const m = last(line);
    const h = last(hist);
    const hPrev = hist.length >= 2 ? hist[hist.length - 2] : 0;
    let score, label;
    if (m > 0 && h > 0 && h > hPrev) { score = 85; label = "MACD bullish, accelerating"; }
    else if (m > 0 && h > 0)         { score = 65; label = "MACD bullish"; }
    else if (m > 0 && h < 0)         { score = 45; label = "MACD losing momentum"; }
    else if (m < 0 && h > 0)         { score = 55; label = "MACD recovering"; }
    else                             { score = 20; label = "MACD bearish"; }
    return { name: "MACD", score, weight: 0.20, label };
  }

  function scoreBollinger(bars) {
    const { upper, lower } = bollingerLast(bars.c, 20, 2);
    const price = last(bars.c);
    const width = upper - lower;
    const pos = width > 0 && Number.isFinite(width) ? (price - lower) / width : 0.5;
    let score, label;
    if (pos < 0.10)      { score = 80; label = "Near lower band — bounce zone"; }
    else if (pos < 0.35) { score = 62; label = "Lower half of bands"; }
    else if (pos < 0.65) { score = 50; label = "Mid-band — neutral"; }
    else if (pos < 0.90) { score = 38; label = "Upper half of bands"; }
    else                 { score = 20; label = "Near upper band — pullback zone"; }
    return { name: "Bollinger", score, weight: 0.15, label };
  }

  function scoreVolume(bars) {
    const v = bars.v;
    const n = Math.min(20, v.length);
    let s = 0;
    for (let i = v.length - n; i < v.length; i++) s += v[i];
    const avg = s / n;
    const ratio = avg > 0 ? last(v) / avg : 1;
    const priceUp = last(bars.c) >= bars.c[bars.c.length - 2];
    let score, label;
    if (ratio > 1.5 && priceUp)  { score = 80; label = `High volume (${ratio.toFixed(1)}x) on up move`; }
    else if (ratio > 1.5)        { score = 20; label = `High volume (${ratio.toFixed(1)}x) on down move`; }
    else if (ratio > 1.0)        { score = 55; label = `Above-average volume (${ratio.toFixed(1)}x)`; }
    else                         { score = 45; label = `Below-average volume (${ratio.toFixed(1)}x)`; }
    return { name: "Volume", score, weight: 0.10, label };
  }

  function scoreVwap(bars) {
    const vw = vwapLast(bars);
    const pct = ((last(bars.c) - vw) / vw) * 100;
    let score;
    if (pct > 1.0)       score = 70;
    else if (pct > 0)    score = 58;
    else if (pct > -1.0) score = 42;
    else                 score = 30;
    return {
      name: "VWAP", score, weight: 0.10,
      label: `Price ${pct >= 0 ? "+" : ""}${pct.toFixed(2)}% vs VWAP`,
    };
  }

  // ── Next-candle direction prediction ──────────────────────────────────────

  function predictNextCandle(bars) {
    const c = bars.c;
    if (c.length < 20) return null;
    const price = last(c);

    // 1. Regression slope over recent bars, as % per bar
    const recent = c.slice(-20);
    const normSlope = (linregSlope(recent) / price) * 100;

    // 2. EMA 5/10 micro-trend
    const e5 = last(ema(c, 5)), e10 = last(ema(c, 10));
    const emaMicro = ((e5 - e10) / e10) * 100;

    // 3. RSI momentum (now vs 3 bars ago)
    const r = rsi(c, 14);
    const rsiDelta = r.length >= 4 ? last(r) - r[r.length - 4] : 0;

    // 4. MACD histogram acceleration
    const { hist } = macd(c);
    const histAccel = last(hist) - (hist.length >= 2 ? hist[hist.length - 2] : 0);

    // 5. Net candle body over last 3 bars
    const n = c.length;
    const bodySum =
      (c[n - 1] - bars.o[n - 1]) + (c[n - 2] - bars.o[n - 2]) + (c[n - 3] - bars.o[n - 3]);
    const bodySignal = (bodySum / price) * 100;

    const rawScore =
      safe(normSlope) * 2.5 +
      safe(emaMicro) * 3.0 +
      safe(rsiDelta) * 0.3 +
      safe((histAccel / price) * 100) * 2.0 +
      safe(bodySignal) * 1.5;

    let probUp = 100 / (1 + Math.exp(-rawScore * 0.8));
    probUp = Math.min(95, Math.max(5, probUp));

    const direction = probUp >= 50 ? "UP" : "DOWN";
    const confidence = direction === "UP" ? probUp : 100 - probUp;

    const atrRaw = atrLast(bars, 14);
    const atr = Number.isFinite(atrRaw) && atrRaw > 0 ? atrRaw : price * 0.01;
    const sign = direction === "UP" ? 1 : -1;

    const drivers = {
      "price momentum":     Math.abs(safe(normSlope)),
      "EMA micro-trend":    Math.abs(safe(emaMicro)) * 1.2,
      "RSI shift":          Math.abs(safe(rsiDelta)) * 0.3,
      "MACD acceleration":  Math.abs(safe((histAccel / price) * 100)) * 2,
      "candle bodies":      Math.abs(safe(bodySignal)) * 1.5,
    };
    let dominant = "price momentum", best = -1;
    for (const k in drivers) if (drivers[k] > best) { best = drivers[k]; dominant = k; }

    return {
      direction,
      confidence,
      predictedClose: price + sign * atr * 0.5 * (confidence / 100),
      predictedHigh: price + atr * (direction === "UP" ? 0.7 : 0.3),
      predictedLow: price - atr * (direction === "UP" ? 0.3 : 0.7),
      driver: dominant,
    };
  }

  // ── Main entry point ──────────────────────────────────────────────────────

  function analyze(bars) {
    const n = bars.c.length;
    if (n < 30) return null;
    const price = last(bars.c);
    const prev = bars.c[n - 2];
    const changePct = ((price - prev) / prev) * 100;

    const signals = [
      scoreEmaTrend(bars), scoreRsi(bars), scoreMacd(bars),
      scoreBollinger(bars), scoreVolume(bars), scoreVwap(bars),
    ];
    for (const s of signals) s.score = safe(s.score);

    // Regime adjustment: in a strong trend, mean-reversion signals (RSI,
    // Bollinger) that oppose the trend get dampened toward neutral — otherwise
    // "oversold = bullish" cancels out a clear downtrend and everything reads
    // as a useless ~50%.
    const trendBias = (signals[0].score - 50) / 50; // EMA Trend, -1..1
    if (Math.abs(trendBias) > 0.6) {
      for (const s of signals) {
        if ((s.name === "RSI" || s.name === "Bollinger") &&
            (s.score - 50) * trendBias < 0) {
          s.score = 50 + (s.score - 50) * 0.4;
          s.label += " (dampened: strong trend)";
        }
      }
    }

    let wSum = 0, pSum = 0;
    for (const s of signals) { wSum += s.weight; pSum += s.score * s.weight; }
    const probability = pSum / wSum;

    const trend = probability >= 57 ? "Bullish" : probability <= 43 ? "Bearish" : "Neutral";

    return {
      price, changePct, probability, trend, signals,
      nextCandle: predictNextCandle(bars),
      lastBarTs: last(bars.t),
    };
  }

  const STA = { ema, rsi, macd, analyze, predictNextCandle };
  if (typeof window !== "undefined") window.STA = STA;
  if (typeof module !== "undefined" && module.exports) module.exports = STA;
})();
