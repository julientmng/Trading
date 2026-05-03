import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, timedelta
import time

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(layout="wide")
st.title("🐋 Institutional Flow Tracker (RSI · MACD · Dark Pools)")

# =========================
# USER INPUTS
# =========================
# --- Polygon.io API key ---
with st.sidebar:
    st.subheader("🔑 Polygon.io API Key")
    api_key = st.text_input("API Key", type="password",
                            help="Get a free key at polygon.io — free tier supports daily data.")
    if not api_key:
        st.warning("Enter your Polygon.io API key to load data.")

# --- Real-time refresh controls ---
with st.sidebar:
    st.divider()
    st.subheader("⏱ Real-Time Refresh")
    realtime_on = st.toggle("Enable auto-refresh", value=False)
    refresh_interval = st.selectbox(
        "Refresh every",
        [30, 60, 120, 300],
        format_func=lambda x: f"{x}s" if x < 60 else f"{x//60}min",
        index=1,
        disabled=not realtime_on
    )
    if realtime_on:
        st.caption(f"🟢 Live — refreshing every {refresh_interval}s")
        last_refresh_placeholder = st.empty()
    else:
        st.caption("⚪ Paused")

col_a, col_b, col_c, col_d = st.columns(4)
with col_a:
    ticker = st.text_input("Ticker (AAPL, SPY, GC=F → X:XAUUSD, BTC → X:BTCUSD)", "SPY")
with col_b:
    interval = st.selectbox("Interval", ["1d", "1wk", "1h", "30m", "15m", "5m"])
with col_c:
    # Polygon free tier: unlimited daily/weekly, intraday limited to ~2y on paid
    PERIOD_OPTIONS = {
        "1d":  ["5d", "1mo", "3mo", "6mo", "1y", "2y", "5y"],
        "1wk": ["1mo", "3mo", "6mo", "1y", "2y", "5y"],
        "1h":  ["5d", "1mo", "3mo", "6mo", "1y", "2y"],
        "30m": ["5d", "1mo", "3mo"],
        "15m": ["5d", "1mo", "3mo"],
        "5m":  ["5d", "1mo"],
    }
    period = st.selectbox("Period", PERIOD_OPTIONS[interval])
with col_d:
    currency = st.selectbox("Currency", ["USD", "CAD"])

currency_symbol = "$" if currency == "USD" else "CA$"

# Warn user if intraday + short period may have sparse whale signals
if interval in ["5m", "15m", "30m"]:
    st.info("⚠️ Intraday intervals use a 20-bar rolling window — select at least 1mo for reliable whale signals.")

# =========================
# POLYGON.IO FETCH HELPERS
# =========================

def period_to_dates(period: str):
    """Convert a period string to (from_date, to_date) strings."""
    end = datetime.today()
    mapping = {
        "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180,
        "1y": 365, "2y": 730, "5y": 1825,
    }
    days = mapping.get(period, 365)
    start = end - timedelta(days=days)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

def interval_to_polygon(interval: str):
    """Map app interval strings to Polygon multiplier + timespan."""
    return {
        "5m":  (5,  "minute"),
        "15m": (15, "minute"),
        "30m": (30, "minute"),
        "1h":  (1,  "hour"),
        "1d":  (1,  "day"),
        "1wk": (1,  "week"),
    }.get(interval, (1, "day"))

@st.cache_data(ttl=30)
def fetch_polygon(ticker: str, period: str, interval: str, key: str) -> pd.DataFrame:
    """Fetch OHLCV bars from Polygon.io Aggregates endpoint."""
    multiplier, timespan = interval_to_polygon(interval)
    from_date, to_date = period_to_dates(period)
    # Polygon uses plain stock tickers — crypto uses X:BTCUSD format
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{ticker.upper()}/range"
        f"/{multiplier}/{timespan}/{from_date}/{to_date}"
        f"?adjusted=true&sort=asc&limit=50000&apiKey={key}"
    )
    resp = requests.get(url, timeout=15)
    data = resp.json()
    if data.get("status") == "ERROR" or not data.get("results"):
        return pd.DataFrame()
    results = data["results"]
    df = pd.DataFrame(results)
    df["Date"] = pd.to_datetime(df["t"], unit="ms", utc=True).dt.tz_convert("America/New_York")
    df = df.set_index("Date")
    df = df.rename(columns={"o": "Open", "h": "High", "l": "Low",
                             "c": "Close", "v": "Volume", "vw": "VWAP_Raw"})
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()

@st.cache_data(ttl=3600)
def fetch_usdcad(key: str) -> float:
    """Fetch latest USD/CAD rate from Polygon forex endpoint."""
    try:
        url = f"https://api.polygon.io/v2/aggs/ticker/C:USDCAD/range/1/day/2020-01-01/{datetime.today().strftime('%Y-%m-%d')}?adjusted=true&sort=desc&limit=1&apiKey={key}"
        data = requests.get(url, timeout=10).json()
        return float(data["results"][0]["c"])
    except Exception:
        return 1.36  # fallback

# =========================
# DATA DOWNLOAD
# =========================
if not api_key:
    st.stop()

with st.spinner("Fetching data from Polygon.io…"):
    df = fetch_polygon(ticker, period, interval, api_key)

if df.empty:
    st.error(
        f"No data returned for **{ticker}**. "
        "Check the ticker symbol and your API key. "
        "Note: commodities use Polygon format e.g. `C:XAUUSD` (gold), `C:WTIUSD` (oil). "
        "Crypto uses `X:BTCUSD`."
    )
    st.stop()

# =========================
# CURRENCY CONVERSION
# =========================
if currency == "CAD":
    usdcad_rate = fetch_usdcad(api_key)
    for col in ["Open", "High", "Low", "Close"]:
        df[col] = df[col] * usdcad_rate
else:
    usdcad_rate = 1.0

# =========================
# RSI
# =========================
delta = df["Close"].diff()
gain = delta.clip(lower=0)
loss = -delta.clip(upper=0)
rs = gain.rolling(14).mean() / loss.rolling(14).mean()
df["RSI"] = 100 - (100 / (1 + rs))

# =========================
# MACD
# =========================
df["EMA12"] = df["Close"].ewm(span=12, adjust=False).mean()
df["EMA26"] = df["Close"].ewm(span=26, adjust=False).mean()
df["MACD"] = df["EMA12"] - df["EMA26"]
df["Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
df["Hist"] = df["MACD"] - df["Signal"]

# =========================
# VWAP (Institutional Price)
# =========================
tp = (df["High"] + df["Low"] + df["Close"]) / 3
df["VWAP"] = (tp * df["Volume"]).cumsum() / df["Volume"].cumsum()

# =========================
# OBV (Flow)
# =========================
df["OBV"] = np.where(
    df["Close"] > df["Close"].shift(1),
    df["Volume"],
    np.where(df["Close"] < df["Close"].shift(1), -df["Volume"], 0)
).cumsum()

# =========================
# WHALE VOLUME — ENHANCED
# =========================

# --- Rolling stats ---
df["Vol_Avg"] = df["Volume"].rolling(20).mean()
df["Vol_Std"] = df["Volume"].rolling(20).std()
df["Vol_Z"] = (df["Volume"] - df["Vol_Avg"]) / df["Vol_Std"]

# --- Tier classification (0–3) ---
# Vol_Z is NaN for the first 19 rows (rolling window warmup); fill those as tier 0
df["Whale_Tier"] = pd.cut(
    df["Vol_Z"].fillna(0),
    bins=[-np.inf, 1, 2, 3, np.inf],
    labels=[0, 1, 2, 3]
).astype(int)

TIER_LABELS = {0: "Normal", 1: "Elevated", 2: "🐋 Whale", 3: "🔴 Mega-whale"}
TIER_COLORS = {0: "gray", 1: "#EF9F27", 2: "#D85A30", 3: "#A32D2D"}
TIER_SIZES  = {0: 0,       1: 8,         2: 13,       3: 20}

# --- Dark pool proxy signals ---
df["Body"] = abs(df["Close"] - df["Open"])
df["Range"] = df["High"] - df["Low"]
df["Body_Ratio"] = df["Body"] / df["Range"].replace(0, np.nan)
df["VWAP_Diff"] = abs(df["Close"] - df["VWAP"]) / df["VWAP"]
df["OBV_Slope"] = df["OBV"].diff()

# --- Composite whale score (0–100) ---
def compute_whale_score(df):
    scores = pd.DataFrame(index=df.index)
    scores["vol_s"]  = (df["Vol_Z"].clip(0, 3) / 3 * 30).fillna(0)          # 30 pts
    scores["body_s"] = ((1 - df["Body_Ratio"].clip(0, 1)) * 20).fillna(0)   # 20 pts — tight body
    scores["vwap_s"] = ((1 - df["VWAP_Diff"].clip(0, 0.01) / 0.01) * 20).fillna(0)  # 20 pts — close near VWAP
    scores["obv_s"]  = np.where(df["OBV_Slope"] > 0, 15, 0)                 # 15 pts — OBV rising
    scores["rsi_s"]  = ((1 - (df["RSI"].clip(50, 80) - 50) / 30) * 15).fillna(0)    # 15 pts — RSI not OB
    df["Whale_Score"] = scores.sum(axis=1).clip(0, 100)
    return df

df = compute_whale_score(df)

# --- Whale streak (consecutive days of tier ≥ 2) ---
streak, count = [], 0
for val in df["Whale_Tier"] >= 2:
    count = count + 1 if val else 0
    streak.append(count)
df["Whale_Streak"] = streak

# --- Buy / sell pressure decomposition ---
df["Buy_Pct"] = (df["Close"] - df["Low"]) / (df["High"] - df["Low"] + 1e-9)
df["Buy_Vol"]  = df["Volume"] * df["Buy_Pct"]
df["Sell_Vol"] = df["Volume"] * (1 - df["Buy_Pct"])

# --- Dark pool accumulation / distribution (boolean) ---
df["DarkPool_Accum"] = (
    (df["Volume"] > df["Vol_Avg"] * 1.8) &
    (df["Body_Ratio"] < 0.35) &
    (df["VWAP_Diff"] < 0.003) &
    (df["OBV_Slope"] > 0)
)
df["DarkPool_Dist"] = (
    (df["Volume"] > df["Vol_Avg"] * 1.8) &
    (df["Body_Ratio"] < 0.35) &
    (df["VWAP_Diff"] < 0.003) &
    (df["RSI"] > 65)
)

# =========================
# WHALE SUMMARY METRICS (sidebar)
# =========================
with st.sidebar:
    st.divider()
    st.subheader("🐋 Whale Summary")
    whale_days = (df["Whale_Tier"] >= 2).sum()
    mega_days  = (df["Whale_Tier"] == 3).sum()
    max_streak = df["Whale_Streak"].max()
    avg_score  = df.loc[df["Whale_Tier"] >= 2, "Whale_Score"].mean()
    net_whale_vol = (
        df.loc[df["Whale_Tier"] >= 2, "Buy_Vol"].sum() -
        df.loc[df["Whale_Tier"] >= 2, "Sell_Vol"].sum()
    )
    st.metric("Whale days (tier 2+)", int(whale_days))
    st.metric("Mega-whale days (tier 3)", int(mega_days))
    st.metric("Longest whale streak", f"{int(max_streak)}d")
    st.metric("Avg whale score", f"{avg_score:.0f}/100" if not np.isnan(avg_score) else "—")
    direction = "🟢 Net Accumulation" if net_whale_vol > 0 else "🔴 Net Distribution"
    st.metric("Whale net pressure", direction)
    st.divider()
    if currency == "CAD":
        st.caption(f"💱 USD/CAD rate used: {usdcad_rate:.4f}")
    else:
        st.caption("💱 Prices in USD")

# =========================
# PRICE CHART
# =========================
fig_price = go.Figure()

fig_price.add_candlestick(
    x=df.index,
    open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
    name="Price"
)

fig_price.add_trace(go.Scatter(
    x=df.index, y=df["VWAP"],
    name="VWAP (Institutional)",
    line=dict(width=2, dash="dot")
))

# Dark pool markers
fig_price.add_trace(go.Scatter(
    x=df[df["DarkPool_Accum"]].index,
    y=df[df["DarkPool_Accum"]]["Low"] * 0.997,
    mode="markers",
    marker=dict(size=14, symbol="triangle-up", color="#1D9E75"),
    name="🟢 Dark Pool Accumulation"
))

fig_price.add_trace(go.Scatter(
    x=df[df["DarkPool_Dist"]].index,
    y=df[df["DarkPool_Dist"]]["High"] * 1.003,
    mode="markers",
    marker=dict(size=14, symbol="triangle-down", color="#D85A30"),
    name="🔴 Dark Pool Distribution"
))

# Whale tier markers (tiers 1, 2, 3)
# Tiers 1 & 2 use fixed tier color.
# Tier 3 (mega-whale) is color-coded green (buying) or red (selling) by Buy_Pct.
for tier in [1, 2, 3]:
    mask = df["Whale_Tier"] == tier
    if mask.sum() == 0:
        continue

    if tier == 3:
        # Split mega-whale bars into buy-dominated vs sell-dominated
        for direction, dir_mask, dir_color, dir_label in [
            ("Buy",  df[mask]["Buy_Pct"] >= 0.5, "#1D9E75", "🟢 Mega-whale — Buying"),
            ("Sell", df[mask]["Buy_Pct"] <  0.5, "#A32D2D", "🔴 Mega-whale — Selling"),
        ]:
            sub = df[mask][dir_mask]
            if sub.empty:
                continue
            fig_price.add_trace(go.Scatter(
                x=sub.index,
                y=sub["High"] * 1.004,
                mode="markers",
                marker=dict(
                    size=TIER_SIZES[tier],
                    color=dir_color,
                    symbol="circle",
                    line=dict(width=2, color="white")
                ),
                customdata=np.stack([
                    sub["Whale_Score"].round(0),
                    sub["Volume"],
                    sub["Vol_Avg"],
                    sub["Whale_Streak"],
                    (sub["Buy_Pct"] * 100).round(0),
                    sub.index.strftime("%Y-%m-%d")
                ], axis=-1),
                hovertemplate=(
                    f"<b>{dir_label}</b><br>"
                    "Date: %{customdata[5]}<br>"
                    f"Price: {currency_symbol}%{{y:,.2f}}<br>"
                    "Score: %{customdata[0]:.0f}/100<br>"
                    "Volume: %{customdata[1]:,.0f}<br>"
                    "20d Avg: %{customdata[2]:,.0f}<br>"
                    "Streak: %{customdata[3]:.0f}d<br>"
                    "Buy pressure: %{customdata[4]:.0f}%<extra></extra>"
                ),
                name=dir_label
            ))
    else:
        # Split tiers 1 & 2 into buy / sell just like tier 3
        for direction, dir_mask, dir_color, dir_label in [
            ("Buy",  df[mask]["Buy_Pct"] >= 0.5, "#1D9E75", f"{TIER_LABELS[tier]} — Buying"),
            ("Sell", df[mask]["Buy_Pct"] <  0.5, "#D85A30", f"{TIER_LABELS[tier]} — Selling"),
        ]:
            sub = df[mask][dir_mask]
            if sub.empty:
                continue
            fig_price.add_trace(go.Scatter(
                x=sub.index,
                y=sub["High"] * 1.004,
                mode="markers",
                marker=dict(
                    size=TIER_SIZES[tier],
                    color=dir_color,
                    symbol="circle",
                    line=dict(width=1.5, color="white")
                ),
                customdata=np.stack([
                    sub["Whale_Score"].round(0),
                    sub["Volume"],
                    sub["Vol_Avg"],
                    sub["Whale_Streak"],
                    (sub["Buy_Pct"] * 100).round(0),
                    sub.index.strftime("%Y-%m-%d")
                ], axis=-1),
                hovertemplate=(
                    f"<b>{dir_label}</b><br>"
                    "Date: %{customdata[5]}<br>"
                    f"Price: {currency_symbol}%{{y:,.2f}}<br>"
                    "Score: %{customdata[0]:.0f}/100<br>"
                    "Volume: %{customdata[1]:,.0f}<br>"
                    "20d Avg: %{customdata[2]:,.0f}<br>"
                    "Streak: %{customdata[3]:.0f}d<br>"
                    "Buy pressure: %{customdata[4]:.0f}%<extra></extra>"
                ),
                name=dir_label
            ))

# Streak annotations (≥ 3 consecutive whale days)
streak_starts = df[df["Whale_Streak"] == 3]
for idx, row in streak_starts.iterrows():
    fig_price.add_annotation(
        x=idx, y=row["High"] * 1.012,
        text=f"🔥 {int(row['Whale_Streak'])}d",
        showarrow=False,
        font=dict(size=9, color=TIER_COLORS[2]),
        bgcolor="rgba(255,255,255,0.7)"
    )

interval_label = {"1d": "Daily", "1wk": "Weekly", "1h": "1-Hour",
                  "30m": "30-Min", "15m": "15-Min", "5m": "5-Min"}.get(interval, interval)
fig_price.update_layout(
    height=650, xaxis_rangeslider_visible=False,
    title=f"{ticker} — Price + Whale Activity ({interval_label} · {currency})",
    yaxis=dict(tickprefix=currency_symbol, title=f"Price ({currency})"),
    legend=dict(orientation="h", y=-0.08)
)

# =========================
# VOLUME PROFILE (price-at-volume)
# =========================
n_bins = 40
price_bins = np.linspace(df["Low"].min(), df["High"].max(), n_bins)
vol_profile = np.zeros(n_bins - 1)
for _, row in df.iterrows():
    mask = (price_bins[:-1] <= row["High"]) & (price_bins[1:] >= row["Low"])
    count = mask.sum()
    if count > 0:
        vol_profile[mask] += row["Volume"] / count

bin_mids = (price_bins[:-1] + price_bins[1:]) / 2

fig_vp = go.Figure(go.Bar(
    x=vol_profile, y=bin_mids,
    orientation="h",
    marker=dict(
        color=vol_profile,
        colorscale="Reds",
        showscale=True,
        colorbar=dict(title="Volume", x=1.02)
    ),
    name="Volume Profile"
))
fig_vp.update_layout(
    height=500,
    title=f"{ticker} — Volume Profile (price-at-volume, {currency})",
    xaxis_title="Accumulated Volume",
    yaxis=dict(tickprefix=currency_symbol, title=f"Price ({currency})")
)

# =========================
# WHALE SCORE CHART
# =========================
fig_score = go.Figure()
fig_score.add_trace(go.Scatter(
    x=df.index, y=df["Whale_Score"],
    fill="tozeroy",
    fillcolor="rgba(216,90,48,0.15)",
    line=dict(color="#D85A30", width=1.5),
    name="Whale Score"
))
fig_score.add_hline(y=60, line_dash="dash", line_color="#EF9F27", annotation_text="High conviction (60)")
fig_score.add_hline(y=80, line_dash="dash", line_color="#A32D2D", annotation_text="Mega-whale (80)")
fig_score.update_layout(
    height=300,
    title="Whale Composite Score (0–100)",
    yaxis=dict(range=[0, 105])
)

# =========================
# WHALE BUY / SELL PRESSURE
# =========================
whale_df = df[df["Whale_Tier"] >= 2].copy()

fig_bs = go.Figure()
fig_bs.add_bar(
    x=whale_df.index, y=whale_df["Buy_Vol"],
    name="Whale Buy Pressure", marker_color="#1D9E75"
)
fig_bs.add_bar(
    x=whale_df.index, y=-whale_df["Sell_Vol"],
    name="Whale Sell Pressure", marker_color="#D85A30"
)
fig_bs.add_hline(y=0, line_color="gray", line_width=0.5)
fig_bs.update_layout(
    barmode="relative",
    height=320,
    title="Whale Buy vs Sell Pressure (tier 2+ bars only)",
    yaxis_title="Volume"
)

# =========================
# RSI
# =========================
fig_rsi = go.Figure()
fig_rsi.add_trace(go.Scatter(x=df.index, y=df["RSI"], name="RSI", line=dict(color="#534AB7")))
fig_rsi.add_hline(y=70, line_dash="dash", line_color="#D85A30")
fig_rsi.add_hline(y=30, line_dash="dash", line_color="#1D9E75")
fig_rsi.update_layout(height=300, title="RSI (14)")

# =========================
# MACD
# =========================
fig_macd = go.Figure()
fig_macd.add_trace(go.Scatter(x=df.index, y=df["MACD"], name="MACD", line=dict(color="#185FA5")))
fig_macd.add_trace(go.Scatter(x=df.index, y=df["Signal"], name="Signal", line=dict(color="#D85A30", dash="dot")))
colors = ["#1D9E75" if v >= 0 else "#D85A30" for v in df["Hist"]]
fig_macd.add_bar(x=df.index, y=df["Hist"], name="Histogram", marker_color=colors)
fig_macd.update_layout(height=300, title="MACD")

# =========================
# OBV
# =========================
fig_obv = go.Figure()
fig_obv.add_trace(go.Scatter(x=df.index, y=df["OBV"], name="OBV Flow", fill="tozeroy",
                             fillcolor="rgba(29,158,117,0.1)", line=dict(color="#1D9E75")))
fig_obv.update_layout(height=300, title="OBV — On-Balance Volume")

# =========================
# CONFLUENCE ALERT ENGINE
# =========================

def compute_alerts(df: pd.DataFrame) -> list[dict]:
    """
    Scan the last 3 bars for selling whale confluence signals.
    Returns a list of alert dicts ordered by severity.
    """
    alerts = []
    recent = df.tail(3).copy()

    for idx, row in recent.iterrows():
        signals = []
        severity = 0

        # Signal 1 — whale tier + selling pressure
        if row["Whale_Tier"] >= 2 and row["Buy_Pct"] < 0.5:
            tier_name = TIER_LABELS[int(row["Whale_Tier"])]
            sell_pct = round((1 - row["Buy_Pct"]) * 100)
            signals.append(f"{tier_name} selling bar ({sell_pct}% sell pressure)")
            severity += 3 if row["Whale_Tier"] == 3 else 2
        elif row["Whale_Tier"] == 1 and row["Buy_Pct"] < 0.5:
            sell_pct = round((1 - row["Buy_Pct"]) * 100)
            signals.append(f"Elevated selling volume ({sell_pct}% sell pressure)")
            severity += 1

        # Signal 2 — dark pool distribution
        if row.get("DarkPool_Dist", False):
            signals.append("Dark pool distribution detected")
            severity += 2

        # Signal 3 — price crossed below VWAP
        if row["Close"] < row["VWAP"]:
            signals.append("Price trading below VWAP")
            severity += 1

        # Signal 4 — OBV declining
        if row["OBV_Slope"] < 0:
            signals.append("OBV declining (outflow)")
            severity += 1

        # Signal 5 — RSI overbought
        if row["RSI"] > 65:
            signals.append(f"RSI elevated at {row['RSI']:.0f}")
            severity += 1

        # Signal 6 — MACD bearish cross
        if row["MACD"] < row["Signal"] and row["Hist"] < 0:
            signals.append("MACD below signal line")
            severity += 1

        # Signal 7 — whale score dropping
        if row["Whale_Score"] > 60 and row["Buy_Pct"] < 0.5:
            signals.append(f"High whale score ({row['Whale_Score']:.0f}) with selling bias")
            severity += 1

        if len(signals) >= 2:
            ts = idx.strftime("%Y-%m-%d %H:%M") if hasattr(idx, "hour") else idx.strftime("%Y-%m-%d")
            alerts.append({
                "time": ts,
                "signals": signals,
                "severity": severity,
                "price": row["Close"],
                "sell_pct": round((1 - row["Buy_Pct"]) * 100),
            })

    return sorted(alerts, key=lambda x: x["severity"], reverse=True)

alerts = compute_alerts(df)

# =========================
# REAL-TIME STATUS HEADER
# =========================
now_str = datetime.now().strftime("%H:%M:%S")
latest = df.iloc[-1]
latest_price = latest["Close"]
latest_change = latest["Close"] - df.iloc[-2]["Close"]
latest_pct    = latest_change / df.iloc[-2]["Close"] * 100
delta_color   = "🟢" if latest_change >= 0 else "🔴"

header_cols = st.columns([2, 1, 1, 1, 1])
with header_cols[0]:
    st.metric(
        label=f"{ticker.upper()} Last Price",
        value=f"{currency_symbol}{latest_price:,.2f}",
        delta=f"{latest_change:+.2f} ({latest_pct:+.2f}%)"
    )
with header_cols[1]:
    st.metric("RSI", f"{latest['RSI']:.1f}")
with header_cols[2]:
    st.metric("Whale Score", f"{latest['Whale_Score']:.0f}/100")
with header_cols[3]:
    st.metric("Whale Tier", TIER_LABELS[int(latest["Whale_Tier"])])
with header_cols[4]:
    pressure = f"{latest['Buy_Pct']*100:.0f}% buy" if "Buy_Pct" in df.columns else "—"
    st.metric("Last Bar Pressure", pressure)

st.caption(f"Last updated: {now_str}")

# =========================
# ALERT BANNERS
# =========================
alert_col1, alert_col2 = st.columns(2)

with alert_col1:
    st.markdown("#### 🔴 Sell Confluence")
    if sell_alerts:
        for alert in sell_alerts:
            sev = alert["severity"]
            signal_list = " · ".join(alert["signals"])
            msg = (
                f"Price: {currency_symbol}{alert['price']:,.2f} | "
                f"Sell pressure: {alert['pressure_pct']}%\n"
                f"Signals: {signal_list}"
            )
            if sev >= 5:
                st.error(f"🚨 **STRONG SELL SIGNAL** — {alert['time']}\n{msg}")
            elif sev >= 3:
                st.warning(f"⚠️ **DISTRIBUTION ALERT** — {alert['time']}\n{msg}")
            else:
                st.info(f"📊 **WEAK SELL SIGNAL** — {alert['time']}\n{msg}")
    else:
        st.success("✅ No active sell confluence on recent bars.")

with alert_col2:
    st.markdown("#### 🟢 Buy Confluence")
    if buy_alerts:
        for alert in buy_alerts:
            sev = alert["severity"]
            signal_list = " · ".join(alert["signals"])
            msg = (
                f"Price: {currency_symbol}{alert['price']:,.2f} | "
                f"Buy pressure: {alert['pressure_pct']}%\n"
                f"Signals: {signal_list}"
            )
            if sev >= 5:
                st.success(f"🚀 **STRONG BUY SIGNAL** — {alert['time']}\n{msg}")
            elif sev >= 3:
                st.success(f"📈 **ACCUMULATION ALERT** — {alert['time']}\n{msg}")
            else:
                st.info(f"📊 **WEAK BUY SIGNAL** — {alert['time']}\n{msg}")
    else:
        st.info("⚪ No active buy confluence on recent bars.")

st.divider()

# =========================
# DISPLAY
# =========================
st.plotly_chart(fig_price,  use_container_width=True)

st.subheader("Volume Analysis")
col1, col2 = st.columns([1, 1])
with col1:
    st.plotly_chart(fig_vp,    use_container_width=True)
with col2:
    st.plotly_chart(fig_score, use_container_width=True)

st.plotly_chart(fig_bs, use_container_width=True)

st.subheader("Technical Indicators")
st.plotly_chart(fig_rsi,  use_container_width=True)
st.plotly_chart(fig_macd, use_container_width=True)
st.plotly_chart(fig_obv,  use_container_width=True)

# =========================
# AUTO-REFRESH LOOP
# =========================
if realtime_on:
    if "last_refresh_placeholder" in dir():
        last_refresh_placeholder.caption(f"Next refresh in {refresh_interval}s")
    time.sleep(refresh_interval)
    st.cache_data.clear()
    st.rerun()
