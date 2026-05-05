import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(layout="wide")
st.title("🐋 Institutional Flow Tracker")

# =========================
# USER INPUTS
# =========================
ticker = st.text_input("Ticker", "SPY").upper()

period = st.selectbox(
    "Period",
    ["5d", "1mo", "3mo", "6mo", "1y", "2y", "5y"],
    index=3
)

interval = st.selectbox(
    "Interval",
    ["5m", "15m", "30m", "1h", "1d", "1wk"],
    index=4
)

# =========================
# DATA DOWNLOAD
# =========================
df = yf.download(
    ticker,
    period=period,
    interval=interval,
    auto_adjust=False,
    progress=False
)

if df.empty:
    st.error("No data found. Try another ticker, period, or interval.")
    st.stop()

# Fix yfinance MultiIndex issue
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

df = df.dropna()

# =========================
# RSI
# =========================
delta = df["Close"].diff()
gain = delta.clip(lower=0)
loss = -delta.clip(upper=0)

avg_gain = gain.rolling(14).mean()
avg_loss = loss.rolling(14).mean()

rs = avg_gain / avg_loss
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
# VWAP
# =========================
tp = (df["High"] + df["Low"] + df["Close"]) / 3
df["VWAP"] = (tp * df["Volume"]).cumsum() / df["Volume"].cumsum()

# =========================
# OBV
# =========================
df["OBV"] = np.where(
    df["Close"] > df["Close"].shift(1),
    df["Volume"],
    np.where(df["Close"] < df["Close"].shift(1), -df["Volume"], 0)
).cumsum()

df["OBV_Slope"] = df["OBV"].diff()
df["OBV_MA"] = df["OBV"].rolling(10).mean()

# =========================
# WHALE VOLUME
# =========================
df["Vol_Avg"] = df["Volume"].rolling(20).mean()
df["Whale"] = df["Volume"] > df["Vol_Avg"] * 2

# =========================
# DARK POOL PROXY LOGIC
# =========================
df["Body"] = abs(df["Close"] - df["Open"])
df["Range"] = df["High"] - df["Low"]
df["Body_Ratio"] = df["Body"] / df["Range"].replace(0, np.nan)
df["VWAP_Diff"] = abs(df["Close"] - df["VWAP"]) / df["VWAP"]

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
# BUY / SELL SCORE
# =========================
latest = df.iloc[-1]

buy_score = 0
sell_score = 0
reasons_buy = []
reasons_sell = []

# VWAP
if latest["Close"] > latest["VWAP"]:
    buy_score += 25
    reasons_buy.append("Price above VWAP")
else:
    sell_score += 25
    reasons_sell.append("Price below VWAP")

# OBV
if latest["OBV_Slope"] > 0:
    buy_score += 20
    reasons_buy.append("OBV rising")
else:
    sell_score += 20
    reasons_sell.append("OBV falling")

# MACD
if latest["MACD"] > latest["Signal"]:
    buy_score += 15
    reasons_buy.append("MACD bullish")
else:
    sell_score += 15
    reasons_sell.append("MACD bearish")

# RSI
if 40 <= latest["RSI"] <= 65:
    buy_score += 15
    reasons_buy.append("RSI healthy")
elif latest["RSI"] > 70:
    sell_score += 15
    reasons_sell.append("RSI overbought")
elif latest["RSI"] < 35:
    buy_score += 10
    reasons_buy.append("RSI oversold bounce area")

# Whale
if latest["Whale"]:
    if latest["Close"] > latest["VWAP"]:
        buy_score += 10
        reasons_buy.append("Whale volume above VWAP")
    else:
        sell_score += 10
        reasons_sell.append("Whale volume below VWAP")

# Dark Pool Proxy
if latest["DarkPool_Accum"]:
    buy_score += 15
    reasons_buy.append("Dark pool accumulation proxy")

if latest["DarkPool_Dist"]:
    sell_score += 15
    reasons_sell.append("Dark pool distribution proxy")

buy_score = min(buy_score, 100)
sell_score = min(sell_score, 100)

if buy_score >= 70 and buy_score > sell_score:
    signal = "🟢 BUY"
elif sell_score >= 70 and sell_score > buy_score:
    signal = "🔴 SELL / AVOID"
else:
    signal = "⚖️ NEUTRAL"

confidence_gap = abs(buy_score - sell_score)

# =========================
# SCORE DISPLAY
# =========================
st.subheader("📊 Buy / Sell Score")

col1, col2, col3, col4 = st.columns(4)

col1.metric("Signal", signal)
col2.metric("Buy Score", f"{buy_score}/100")
col3.metric("Sell Score", f"{sell_score}/100")
col4.metric("Confidence Gap", f"{confidence_gap}")

st.progress(buy_score / 100)

with st.expander("Why this signal?"):
    st.write("### Bullish factors")
    st.write(reasons_buy if reasons_buy else "No strong bullish factors.")

    st.write("### Bearish factors")
    st.write(reasons_sell if reasons_sell else "No strong bearish factors.")

# =========================
# ALERTS
# =========================
st.subheader("🔔 Smart Alerts")

if buy_score >= 70 and latest["Close"] > latest["VWAP"] and latest["OBV_Slope"] > 0:
    st.success("Strong bullish alignment: price above VWAP, OBV rising, and buy score above 70.")

elif sell_score >= 70 and latest["Close"] < latest["VWAP"] and latest["OBV_Slope"] < 0:
    st.error("Strong bearish alignment: price below VWAP, OBV falling, and sell score above 70.")

else:
    st.info("No high-confidence setup right now.")

# =========================
# RECENT CLUSTERS
# =========================
st.subheader("🕶️ Recent Institutional Proxy Clusters")

recent = df.tail(30)

recent_accum = recent[recent["DarkPool_Accum"]]
recent_dist = recent[recent["DarkPool_Dist"]]

colA, colB = st.columns(2)

colA.metric("Recent Accumulation Signals", len(recent_accum))
colB.metric("Recent Distribution Signals", len(recent_dist))

if len(recent_accum) > len(recent_dist):
    st.success("Recent flow leans accumulation.")
elif len(recent_dist) > len(recent_accum):
    st.warning("Recent flow leans distribution.")
else:
    st.info("Recent flow is balanced or unclear.")

# =========================
# PRICE CHART
# =========================
fig_price = go.Figure()

fig_price.add_candlestick(
    x=df.index,
    open=df["Open"],
    high=df["High"],
    low=df["Low"],
    close=df["Close"],
    name="Price"
)

fig_price.add_trace(go.Scatter(
    x=df.index,
    y=df["VWAP"],
    name="VWAP",
    line=dict(width=2)
))

fig_price.add_trace(go.Scatter(
    x=df[df["Whale"]].index,
    y=df[df["Whale"]]["High"],
    mode="markers",
    marker=dict(size=10, symbol="circle"),
    name="🐋 Whale Volume"
))

fig_price.add_trace(go.Scatter(
    x=df[df["DarkPool_Accum"]].index,
    y=df[df["DarkPool_Accum"]]["Low"],
    mode="markers",
    marker=dict(size=14, symbol="triangle-up"),
    name="🟢 Dark Pool Accumulation"
))

fig_price.add_trace(go.Scatter(
    x=df[df["DarkPool_Dist"]].index,
    y=df[df["DarkPool_Dist"]]["High"],
    mode="markers",
    marker=dict(size=14, symbol="triangle-down"),
    name="🔴 Dark Pool Distribution"
))

# Shaded dark pool proxy zones
for idx in df[df["DarkPool_Accum"]].index:
    fig_price.add_vrect(
        x0=idx,
        x1=idx,
        fillcolor="green",
        opacity=0.15,
        line_width=0
    )

for idx in df[df["DarkPool_Dist"]].index:
    fig_price.add_vrect(
        x0=idx,
        x1=idx,
        fillcolor="red",
        opacity=0.15,
        line_width=0
    )

fig_price.update_layout(
    height=700,
    xaxis_rangeslider_visible=False,
    title=f"{ticker} Price + VWAP + Institutional Flow"
)

# =========================
# RSI CHART
# =========================
fig_rsi = go.Figure()

fig_rsi.add_trace(go.Scatter(
    x=df.index,
    y=df["RSI"],
    name="RSI"
))

fig_rsi.add_hline(y=70, line_dash="dash")
fig_rsi.add_hline(y=30, line_dash="dash")

fig_rsi.update_layout(
    height=320,
    title="RSI"
)

# =========================
# MACD CHART
# =========================
fig_macd = go.Figure()

fig_macd.add_trace(go.Scatter(
    x=df.index,
    y=df["MACD"],
    name="MACD"
))

fig_macd.add_trace(go.Scatter(
    x=df.index,
    y=df["Signal"],
    name="Signal"
))

fig_macd.add_bar(
    x=df.index,
    y=df["Hist"],
    name="Histogram"
)

fig_macd.update_layout(
    height=380,
    title="MACD"
)

# =========================
# OBV CHART
# =========================
fig_obv = go.Figure()

fig_obv.add_trace(go.Scatter(
    x=df.index,
    y=df["OBV"],
    name="OBV"
))

fig_obv.add_trace(go.Scatter(
    x=df.index,
    y=df["OBV_MA"],
    name="OBV Moving Average"
))

fig_obv.update_layout(
    height=340,
    title="OBV Flow"
)

# =========================
# DISPLAY CHARTS
# =========================
st.plotly_chart(fig_price, use_container_width=True)
st.plotly_chart(fig_rsi, use_container_width=True)
st.plotly_chart(fig_macd, use_container_width=True)
st.plotly_chart(fig_obv, use_container_width=True)

# =========================
# FOOTER
# =========================
st.caption(
    "Educational tool only. This is not financial advice. "
    "Dark pool signals are proxy estimates based on volume, VWAP behavior, candle compression, and OBV flow."
)
