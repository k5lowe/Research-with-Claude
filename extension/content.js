// Overlay orchestrator: detects the symbol, fetches bars for three timeframes,
// runs the analysis engine (window.STA from indicators.js), renders the panel,
// and tracks how past next-candle predictions actually resolved.

(function () {
  "use strict";

  const REFRESH_MS = 30_000;
  const TIMEFRAMES = {
    "1m":  { interval: "1m",  range: "1d", sec: 60 },
    "5m":  { interval: "5m",  range: "5d", sec: 300 },
    "15m": { interval: "15m", range: "5d", sec: 900 },
  };
  const TF_KEYS = Object.keys(TIMEFRAMES);

  const state = {
    symbol: null,
    primaryTf: localStorage.getItem("sta.tf") || "1m",
    collapsed: localStorage.getItem("sta.collapsed") === "1",
    pos: JSON.parse(localStorage.getItem("sta.pos") || "null"),
    timer: null,
    fetching: false,
  };

  // ── Symbol detection ───────────────────────────────────────────────────────

  function symbolFromUrl() {
    const m = location.pathname.match(/^\/(?:chart|quote)\/([^/?#]+)/);
    return m ? decodeURIComponent(m[1]).toUpperCase() : null;
  }

  // ── Data fetch (via background service worker) ────────────────────────────

  function fetchChart(symbol, tf) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage(
        { type: "fetchChart", symbol, interval: tf.interval, range: tf.range },
        (resp) => {
          if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
          if (!resp?.ok) return reject(new Error(resp?.error || "no response"));
          resolve(resp.data);
        }
      );
    });
  }

  function toBars(chartJson) {
    const res = chartJson?.chart?.result?.[0];
    if (!res?.timestamp) return null;
    const q = res.indicators?.quote?.[0];
    if (!q) return null;
    const bars = { t: [], o: [], h: [], l: [], c: [], v: [] };
    for (let i = 0; i < res.timestamp.length; i++) {
      if (q.close[i] == null || q.open[i] == null) continue;
      bars.t.push(res.timestamp[i]);
      bars.o.push(q.open[i]);
      bars.h.push(q.high[i]);
      bars.l.push(q.low[i]);
      bars.c.push(q.close[i]);
      bars.v.push(q.volume[i] || 0);
    }
    return bars.c.length ? { bars, meta: res.meta } : null;
  }

  // ── Prediction accuracy tracker ───────────────────────────────────────────
  // Every refresh records the current prediction keyed by its last-closed bar,
  // then scores older predictions against the bar that actually followed.

  function loadHistory() {
    try { return JSON.parse(localStorage.getItem("sta.history") || "[]"); }
    catch { return []; }
  }

  function saveHistory(h) {
    localStorage.setItem("sta.history", JSON.stringify(h.slice(-300)));
  }

  function trackPrediction(symbol, tfKey, analysis) {
    if (!analysis?.nextCandle) return;
    const history = loadHistory();
    const key = `${symbol}|${tfKey}|${analysis.lastBarTs}`;
    if (!history.some((p) => p.key === key)) {
      history.push({
        key,
        symbol,
        tf: tfKey,
        madeAt: analysis.lastBarTs,
        base: analysis.price,
        dir: analysis.nextCandle.direction,
        scored: false,
        correct: null,
      });
    }
    saveHistory(history);
  }

  function scorePredictions(symbol, tfKey, bars) {
    const tfSec = TIMEFRAMES[tfKey].sec;
    const history = loadHistory();
    const nowSec = Date.now() / 1000;
    let changed = false;

    for (const p of history) {
      if (p.scored || p.symbol !== symbol || p.tf !== tfKey) continue;
      // Find the first bar that opened after the prediction was made
      const idx = bars.t.findIndex((t) => t > p.madeAt);
      if (idx === -1) continue;
      // Only score once that bar has fully closed
      const barClosed = idx < bars.t.length - 1 || nowSec > bars.t[idx] + tfSec;
      if (!barClosed) continue;
      const close = bars.c[idx];
      p.scored = true;
      p.correct = close === p.base ? null : (close > p.base) === (p.dir === "UP");
      changed = true;
    }
    if (changed) saveHistory(history);
  }

  function accuracyStats() {
    const scored = loadHistory().filter((p) => p.scored && p.correct !== null);
    const hits = scored.filter((p) => p.correct).length;
    return {
      total: scored.length,
      hits,
      rate: scored.length ? (hits / scored.length) * 100 : null,
      recent: scored.slice(-10).map((p) => p.correct),
    };
  }

  // ── Overlay DOM ───────────────────────────────────────────────────────────

  let root = null;

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function buildOverlay() {
    if (root) root.remove();
    root = el("div", "sta-root");
    if (state.collapsed) root.classList.add("sta-collapsed");
    if (state.pos) {
      root.style.left = state.pos.x + "px";
      root.style.top = state.pos.y + "px";
      root.style.right = "auto";
    }

    const header = el("div", "sta-header");
    header.append(
      el("span", "sta-title", "Trend Overlay"),
      el("span", "sta-sym", ""),
      el("button", "sta-toggle", state.collapsed ? "+" : "–")
    );
    root.append(header);

    const body = el("div", "sta-body");
    body.append(
      el("div", "sta-hero"),
      el("div", "sta-meter-wrap"),
      el("div", "sta-tfs"),
      el("div", "sta-signals"),
      el("div", "sta-accuracy"),
      el("div", "sta-footer"),
      el("div", "sta-note", "Informational only — not financial advice.")
    );
    root.append(body);
    document.body.append(root);

    header.querySelector(".sta-toggle").addEventListener("click", (e) => {
      e.stopPropagation();
      state.collapsed = !state.collapsed;
      localStorage.setItem("sta.collapsed", state.collapsed ? "1" : "0");
      root.classList.toggle("sta-collapsed", state.collapsed);
      e.target.textContent = state.collapsed ? "+" : "–";
    });

    makeDraggable(header);
  }

  function makeDraggable(handle) {
    let sx, sy, ox, oy, dragging = false;
    handle.addEventListener("mousedown", (e) => {
      if (e.target.tagName === "BUTTON") return;
      dragging = true;
      sx = e.clientX; sy = e.clientY;
      const r = root.getBoundingClientRect();
      ox = r.left; oy = r.top;
      e.preventDefault();
    });
    window.addEventListener("mousemove", (e) => {
      if (!dragging) return;
      const x = Math.max(0, Math.min(window.innerWidth - 60, ox + e.clientX - sx));
      const y = Math.max(0, Math.min(window.innerHeight - 40, oy + e.clientY - sy));
      root.style.left = x + "px";
      root.style.top = y + "px";
      root.style.right = "auto";
      state.pos = { x, y };
    });
    window.addEventListener("mouseup", () => {
      if (dragging) localStorage.setItem("sta.pos", JSON.stringify(state.pos));
      dragging = false;
    });
  }

  function dirClass(dir) { return dir === "UP" ? "sta-up" : "sta-down"; }
  function dirArrow(dir) { return dir === "UP" ? "▲" : "▼"; }

  function renderError(message) {
    if (!root) return;
    const hero = root.querySelector(".sta-hero");
    hero.innerHTML = "";
    hero.append(el("div", "sta-error", message));
  }

  function render(symbol, results, marketNote) {
    const primary = results[state.primaryTf];
    const a = primary?.analysis;
    root.querySelector(".sta-sym").textContent = symbol;

    // Hero: direction of the next candle
    const hero = root.querySelector(".sta-hero");
    hero.innerHTML = "";
    if (a?.nextCandle) {
      const nc = a.nextCandle;
      const row = el("div", `sta-hero-row ${dirClass(nc.direction)}`);
      row.append(
        el("span", "sta-hero-arrow", dirArrow(nc.direction)),
        el("span", "sta-hero-dir", nc.direction),
        el("span", "sta-hero-conf", `${nc.confidence.toFixed(0)}%`)
      );
      hero.append(row);
      hero.append(el("div", "sta-hero-sub",
        `next ${state.primaryTf} candle · driven by ${nc.driver} · ` +
        `target $${nc.predictedClose.toFixed(2)}`));
      const priceRow = el("div", "sta-price-row");
      const chg = a.changePct;
      priceRow.append(
        el("span", "sta-price", `$${a.price.toFixed(2)}`),
        el("span", `sta-chg ${chg >= 0 ? "sta-up" : "sta-down"}`,
          `${chg >= 0 ? "+" : ""}${chg.toFixed(2)}% last bar`)
      );
      hero.append(priceRow);
    } else {
      hero.append(el("div", "sta-error", "Not enough data to analyze."));
    }

    // Meter: overall bullish probability (0–100, 50 = neutral)
    const meterWrap = root.querySelector(".sta-meter-wrap");
    meterWrap.innerHTML = "";
    if (a) {
      const p = a.probability;
      const labelRow = el("div", "sta-meter-labels");
      labelRow.append(
        el("span", "sta-muted", "Bearish"),
        el("span", "sta-meter-value", `${p.toFixed(0)}% · ${a.trend}`),
        el("span", "sta-muted", "Bullish")
      );
      const track = el("div", "sta-meter-track");
      const fill = el("div", "sta-meter-fill");
      fill.style.width = `${Math.max(2, Math.min(100, p))}%`;
      fill.classList.add(p >= 55 ? "sta-fill-up" : p <= 45 ? "sta-fill-down" : "sta-fill-flat");
      const mid = el("div", "sta-meter-mid");
      track.append(fill, mid);
      meterWrap.append(labelRow, track);
    }

    // Timeframe consensus
    const tfs = root.querySelector(".sta-tfs");
    tfs.innerHTML = "";
    const dirs = [];
    for (const key of TF_KEYS) {
      const r = results[key];
      const cell = el("button", "sta-tf-cell");
      if (key === state.primaryTf) cell.classList.add("sta-tf-active");
      cell.append(el("span", "sta-tf-name", key));
      if (r?.analysis?.nextCandle) {
        const nc = r.analysis.nextCandle;
        dirs.push(nc.direction);
        const d = el("span", `sta-tf-dir ${dirClass(nc.direction)}`);
        d.textContent = `${dirArrow(nc.direction)} ${nc.confidence.toFixed(0)}%`;
        cell.append(d);
      } else {
        cell.append(el("span", "sta-muted", "—"));
      }
      cell.addEventListener("click", () => {
        state.primaryTf = key;
        localStorage.setItem("sta.tf", key);
        refresh();
      });
      tfs.append(cell);
    }
    const ups = dirs.filter((d) => d === "UP").length;
    let consensus = "Mixed timeframes";
    if (dirs.length === 3 && ups === 3) consensus = "All timeframes point UP";
    else if (dirs.length === 3 && ups === 0) consensus = "All timeframes point DOWN";
    else if (ups >= 2) consensus = "Leaning UP";
    else if (dirs.length - ups >= 2) consensus = "Leaning DOWN";
    tfs.append(el("div", "sta-consensus", consensus));

    // Signal breakdown
    const sigWrap = root.querySelector(".sta-signals");
    sigWrap.innerHTML = "";
    if (a) {
      for (const s of a.signals) {
        const row = el("div", "sta-sig-row");
        const top = el("div", "sta-sig-top");
        top.append(el("span", "sta-sig-name", s.name), el("span", "sta-sig-score", s.score.toFixed(0)));
        const track = el("div", "sta-sig-track");
        const fill = el("div", "sta-sig-fill");
        fill.style.width = `${Math.max(2, s.score)}%`;
        fill.classList.add(s.score >= 55 ? "sta-fill-up" : s.score <= 45 ? "sta-fill-down" : "sta-fill-flat");
        track.append(fill);
        row.append(top, track, el("div", "sta-sig-label", s.label));
        sigWrap.append(row);
      }
    }

    // Accuracy of past predictions
    const accWrap = root.querySelector(".sta-accuracy");
    accWrap.innerHTML = "";
    const stats = accuracyStats();
    if (stats.total > 0) {
      const line = el("div", "sta-acc-line");
      line.append(
        el("span", null, "Prediction hit rate: "),
        el("strong", null, `${stats.rate.toFixed(0)}%`),
        el("span", "sta-muted", ` (${stats.hits}/${stats.total} scored)`)
      );
      const strip = el("div", "sta-acc-strip");
      for (const ok of stats.recent) {
        strip.append(el("span", ok ? "sta-acc-hit" : "sta-acc-miss", ok ? "✓" : "✗"));
      }
      accWrap.append(line, strip);
    } else {
      accWrap.append(el("div", "sta-muted", "Hit rate appears after predictions resolve."));
    }

    // Footer
    const footer = root.querySelector(".sta-footer");
    footer.innerHTML = "";
    const t = new Date().toLocaleTimeString();
    footer.append(el("span", "sta-muted", `Updated ${t} · refreshes every 30s`));
    if (marketNote) footer.append(el("span", "sta-market-note", marketNote));
  }

  // ── Refresh loop ──────────────────────────────────────────────────────────

  async function refresh() {
    const symbol = state.symbol;
    if (!symbol || state.fetching || document.hidden) return;
    state.fetching = true;
    try {
      const settled = await Promise.allSettled(
        TF_KEYS.map((k) => fetchChart(symbol, TIMEFRAMES[k]))
      );
      const results = {};
      let meta = null;
      TF_KEYS.forEach((k, i) => {
        if (settled[i].status !== "fulfilled") { results[k] = null; return; }
        const parsed = toBars(settled[i].value);
        if (!parsed) { results[k] = null; return; }
        meta = meta || parsed.meta;
        results[k] = { bars: parsed.bars, analysis: window.STA.analyze(parsed.bars) };
      });

      if (symbol !== state.symbol) return; // user navigated away mid-fetch

      const primary = results[state.primaryTf];
      if (!primary?.analysis) {
        const firstErr = settled.find((s) => s.status === "rejected");
        renderError(firstErr ? `Data error: ${firstErr.reason.message}` : "No data for this symbol.");
        return;
      }

      // Score old predictions first, then record the new one
      scorePredictions(symbol, state.primaryTf, primary.bars);
      trackPrediction(symbol, state.primaryTf, primary.analysis);

      let marketNote = null;
      const ageSec = Date.now() / 1000 - primary.analysis.lastBarTs;
      if (ageSec > TIMEFRAMES[state.primaryTf].sec * 5) {
        marketNote = "Market closed — showing last session";
      }

      render(symbol, results, marketNote);
    } catch (e) {
      renderError(`Error: ${e.message}`);
    } finally {
      state.fetching = false;
    }
  }

  function setSymbol(symbol) {
    state.symbol = symbol;
    if (!symbol) {
      if (root) root.style.display = "none";
      return;
    }
    if (!root) buildOverlay();
    root.style.display = "";
    root.querySelector(".sta-sym").textContent = symbol;
    refresh();
  }

  // Yahoo Finance is a SPA — watch the URL for symbol changes.
  let lastHref = "";
  setInterval(() => {
    if (location.href !== lastHref) {
      lastHref = location.href;
      const sym = symbolFromUrl();
      if (sym !== state.symbol) setSymbol(sym);
    }
  }, 1000);

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refresh();
  });

  setSymbol(symbolFromUrl());
  state.timer = setInterval(refresh, REFRESH_MS);
})();
