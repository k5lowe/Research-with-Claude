"""
Stock trend analysis dashboard.
Run with: streamlit run dashboard.py
"""

import time
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from analysis import analyze, ema, rsi, macd, bollinger, vwap

# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Stock Trend Analyzer",
    page_icon="📈",
    layout="wide",
)

st.title("📈 Stock Trend Analyzer")
st.caption("Technical analysis dashboard — no trading, no real money. Purely informational.")

# ── Sidebar controls ─────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Settings")

    symbol = st.text_input("Ticker symbol", value="AAPL").upper().strip()

    timeframe = st.selectbox(
        "Timeframe",
        options=["1d", "5d", "1mo", "3mo"],
        index=1,
        format_func=lambda x: {
            "1d": "1 Day (5-min bars)",
            "5d": "5 Days (15-min bars)",
            "1mo": "1 Month (1-hr bars)",
            "3mo": "3 Months (1-day bars)",
        }[x],
    )

    interval_map = {"1d": "5m", "5d": "15m", "1mo": "1h", "3mo": "1d"}
    interval = interval_map[timeframe]

    watchlist_raw = st.text_area(
        "Watchlist (one per line)",
        value="AAPL\nMSFT\nNVDA\nTSLA\nSPY",
    )
    watchlist = [s.strip().upper() for s in watchlist_raw.splitlines() if s.strip()]

    auto_refresh = st.toggle("Auto-refresh (60s)", value=False)
    show_vwap = st.toggle("Show VWAP", value=True)
    show_bollinger = st.toggle("Show Bollinger Bands", value=True)

    st.divider()
    st.caption("Data via Yahoo Finance. Delays may apply.")

# ── Data fetching ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def fetch_bars(sym: str, period: str, interval: str) -> pd.DataFrame:
    try:
        df = yf.download(
            sym,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
        )
    except Exception as e:
        st.warning(f"Download error for {sym}: {e}")
        return pd.DataFrame()

    if df.empty:
        return df

    # yf.download returns MultiIndex columns when downloading a single ticker
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df.columns = [c.lower() for c in df.columns]
    needed = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    df = df[needed].dropna()
    return df


def probability_color(p: float) -> str:
    if p >= 65:
        return "green"
    if p >= 55:
        return "lightgreen"
    if p >= 45:
        return "orange"
    if p >= 35:
        return "salmon"
    return "red"


def trend_emoji(trend: str) -> str:
    return {"Bullish": "🟢", "Bearish": "🔴", "Neutral": "🟡"}.get(trend, "⚪")


# ── Main chart ────────────────────────────────────────────────────────────────

def render_chart(result):
    bars = result.bars
    close = bars["close"]
    pred = result.next_candle

    e9 = ema(close, 9)
    e21 = ema(close, 21)
    e50 = ema(close, 50)
    rsi_line = rsi(close, 14)
    _, _, macd_hist = macd(close)
    upper_bb, mid_bb, lower_bb = bollinger(close)
    vwap_line = vwap(bars)

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.6, 0.2, 0.2],
        vertical_spacing=0.03,
        subplot_titles=("Price", "RSI (14)", "MACD Histogram"),
    )

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=bars.index, open=bars["open"], high=bars["high"],
        low=bars["low"], close=bars["close"],
        name="Price", showlegend=False,
    ), row=1, col=1)

    # ── Predicted next candle ──────────────────────────────────────────────
    if pred is not None:
        # Estimate the timestamp for the next candle by inferring bar spacing
        if len(bars.index) >= 2:
            bar_delta = bars.index[-1] - bars.index[-2]
        else:
            bar_delta = pd.Timedelta(minutes=5)
        next_ts = bars.index[-1] + bar_delta

        candle_color = "#00e676" if pred.direction == "UP" else "#ff1744"
        current_open = close.iloc[-1]

        fig.add_trace(go.Candlestick(
            x=[next_ts],
            open=[current_open],
            high=[pred.predicted_high],
            low=[pred.predicted_low],
            close=[pred.predicted_close],
            name="Predicted",
            increasing_line_color=candle_color,
            increasing_fillcolor=candle_color,
            decreasing_line_color=candle_color,
            decreasing_fillcolor=candle_color,
            opacity=0.55,
        ), row=1, col=1)

        # Dashed vertical line separating actual from predicted
        fig.add_vline(
            x=bars.index[-1].value / 1e6,  # plotly wants ms timestamps
            line_dash="dash",
            line_color="rgba(255,255,255,0.25)",
            row=1, col=1,
        )

        # Annotation arrow on the predicted candle
        arrow_color = "#00e676" if pred.direction == "UP" else "#ff1744"
        arrow_symbol = "▲" if pred.direction == "UP" else "▼"
        fig.add_annotation(
            x=next_ts,
            y=pred.predicted_high if pred.direction == "UP" else pred.predicted_low,
            text=f"{arrow_symbol} {pred.confidence:.0f}%",
            showarrow=True,
            arrowhead=2,
            arrowcolor=arrow_color,
            font=dict(color=arrow_color, size=13, family="monospace"),
            bgcolor="rgba(0,0,0,0.6)",
            bordercolor=arrow_color,
            borderwidth=1,
            ax=0,
            ay=-30 if pred.direction == "UP" else 30,
            row=1, col=1,
        )

    # EMAs
    for series, name, color in [(e9, "EMA 9", "#f0a500"), (e21, "EMA 21", "#e05c00"), (e50, "EMA 50", "#9b59b6")]:
        fig.add_trace(go.Scatter(x=bars.index, y=series, name=name,
                                 line=dict(color=color, width=1.2)), row=1, col=1)

    if show_bollinger:
        for series, name, dash in [(upper_bb, "BB Upper", "dot"), (mid_bb, "BB Mid", "dash"), (lower_bb, "BB Lower", "dot")]:
            fig.add_trace(go.Scatter(x=bars.index, y=series, name=name,
                                     line=dict(color="#4a90d9", width=1, dash=dash)), row=1, col=1)

    if show_vwap:
        fig.add_trace(go.Scatter(x=bars.index, y=vwap_line, name="VWAP",
                                 line=dict(color="#00bcd4", width=1.5, dash="dashdot")), row=1, col=1)

    # RSI
    fig.add_trace(go.Scatter(x=bars.index, y=rsi_line, name="RSI",
                             line=dict(color="#e67e22", width=1.5), showlegend=False), row=2, col=1)
    fig.add_hline(y=70, line_dash="dot", line_color="red", opacity=0.5, row=2, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="green", opacity=0.5, row=2, col=1)
    fig.add_hline(y=50, line_dash="dot", line_color="gray", opacity=0.3, row=2, col=1)

    # MACD histogram
    hist_colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in macd_hist]
    fig.add_trace(go.Bar(x=bars.index, y=macd_hist, name="MACD Hist",
                         marker_color=hist_colors, showlegend=False), row=3, col=1)
    fig.add_hline(y=0, line_color="gray", opacity=0.5, row=3, col=1)

    fig.update_layout(
        height=650,
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
    )
    fig.update_yaxes(title_text="RSI", row=2, col=1, range=[0, 100])
    fig.update_yaxes(title_text="Hist", row=3, col=1)

    st.plotly_chart(fig, use_container_width=True)


# ── Probability gauge ─────────────────────────────────────────────────────────

def render_gauge(probability: float, trend: str):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=probability,
        number={"suffix": "%", "font": {"size": 36}},
        title={"text": f"{trend_emoji(trend)} {trend}", "font": {"size": 20}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1},
            "bar": {"color": probability_color(probability), "thickness": 0.3},
            "steps": [
                {"range": [0, 35], "color": "#2c1010"},
                {"range": [35, 45], "color": "#2c1f10"},
                {"range": [45, 55], "color": "#252520"},
                {"range": [55, 65], "color": "#102c10"},
                {"range": [65, 100], "color": "#0a1f0a"},
            ],
            "threshold": {
                "line": {"color": "white", "width": 2},
                "thickness": 0.8,
                "value": 50,
            },
        },
    ))
    fig.update_layout(
        height=220,
        margin=dict(l=20, r=20, t=30, b=10),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Signal breakdown table ────────────────────────────────────────────────────

def render_signals(result):
    st.subheader("Signal Breakdown")
    for sig in result.signals:
        col1, col2, col3 = st.columns([2, 5, 1])
        with col1:
            st.markdown(f"**{sig.name}**")
        with col2:
            st.markdown(sig.label)
        with col3:
            color = probability_color(sig.score)
            st.markdown(
                f"<span style='color:{color}; font-weight:bold'>{sig.score:.0f}</span>",
                unsafe_allow_html=True,
            )
        bar_val = int(sig.score)
        st.progress(bar_val)


# ── Watchlist panel ───────────────────────────────────────────────────────────

def render_watchlist(symbols: list[str], period: str, interval: str):
    st.subheader("Watchlist")
    cols = st.columns(len(symbols))
    for i, sym in enumerate(symbols):
        bars = fetch_bars(sym, period, interval)
        if bars.empty or len(bars) < 30:
            cols[i].warning(sym)
            continue
        result = analyze(sym, bars)
        with cols[i]:
            delta_color = "normal" if result.change_pct >= 0 else "inverse"
            st.metric(
                label=f"{trend_emoji(result.trend)} {sym}",
                value=f"${result.price:.2f}",
                delta=f"{result.change_pct:+.2f}%",
            )
            color = probability_color(result.probability)
            st.markdown(
                f"<div style='text-align:center; font-size:18px; color:{color}'>"
                f"<b>{result.probability:.0f}%</b> bullish</div>",
                unsafe_allow_html=True,
            )


# ── Main render ───────────────────────────────────────────────────────────────

bars = fetch_bars(symbol, timeframe, interval)

if bars.empty or len(bars) < 30:
    st.error(f"Could not load data for **{symbol}**. Check the ticker and try again.")
    st.stop()

result = analyze(symbol, bars)

# ── Next-candle prediction banner ────────────────────────────────────────────
pred = result.next_candle
if pred is not None:
    up = pred.direction == "UP"
    bg = "rgba(0, 180, 80, 0.15)" if up else "rgba(220, 30, 60, 0.15)"
    border = "#00e676" if up else "#ff1744"
    arrow = "▲" if up else "▼"
    label = "UP" if up else "DOWN"
    st.markdown(
        f"""
        <div style="
            background:{bg};
            border-left: 4px solid {border};
            border-radius: 6px;
            padding: 14px 20px;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 24px;
        ">
            <span style="font-size:42px; color:{border}; line-height:1">{arrow}</span>
            <div>
                <div style="font-size:22px; font-weight:700; color:{border}">
                    Next candle predicted: {label}
                </div>
                <div style="font-size:14px; color:#ccc; margin-top:4px">
                    {pred.reason} &nbsp;|&nbsp;
                    Target close: <b>${pred.predicted_close:.2f}</b> &nbsp;|&nbsp;
                    Range: ${pred.predicted_low:.2f} – ${pred.predicted_high:.2f}
                </div>
            </div>
            <div style="margin-left:auto; text-align:center">
                <div style="font-size:34px; font-weight:800; color:{border}">{pred.confidence:.0f}%</div>
                <div style="font-size:12px; color:#aaa">confidence</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── Top row: price stats + gauge ─────────────────────────────────────────────
col_price, col_gauge = st.columns([2, 1])

with col_price:
    st.subheader(f"{symbol}")
    m1, m2, m3 = st.columns(3)
    m1.metric("Price", f"${result.price:.2f}", f"{result.change_pct:+.2f}%")
    m2.metric("Bullish probability", f"{result.probability:.1f}%")
    m3.metric("Trend", f"{trend_emoji(result.trend)} {result.trend}")

    render_chart(result)

with col_gauge:
    st.subheader("Signal strength")
    render_gauge(result.probability, result.trend)
    render_signals(result)

st.divider()
render_watchlist(watchlist, timeframe, interval)

# Auto-refresh
if auto_refresh:
    time.sleep(60)
    st.rerun()
