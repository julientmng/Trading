import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, timedelta
import time
import feedparser
import re
try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False

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

# --- Data source selector ---
with st.sidebar:
    st.divider()
    st.subheader("📡 Data Source")
    data_source_choice = st.radio(
        "Fetch data from",
        ["Polygon.io", "yfinance (free)"],
        index=0,
        help="Polygon.io is more reliable for intraday. yfinance is free and needs no API key."
    )
    use_yfinance = data_source_choice == "yfinance (free)"
    if use_yfinance:
        st.caption("✅ No API key needed for normal hours.")
    else:
        st.caption("🔑 Uses your Polygon.io API key above.")

# --- Extended hours toggle ---
with st.sidebar:
    st.divider()
    st.subheader("🌙 Extended Hours")
    extended_hours = st.toggle(
        "Include pre & post market",
        value=False,
        help="Pre-market (4am–9:30am ET) and after-hours (4pm–8pm ET). Requires Polygon paid plan or uses yfinance fallback."
    )
    if extended_hours:
        use_yf_extended = st.checkbox(
            "Use yfinance fallback (free)",
            value=True,
            help="yfinance returns extended hours data for free. Uncheck to use Polygon paid tier instead."
        )
        st.caption("🌅 Pre-market: 4:00–9:30am ET\n🌆 After-hours: 4:00–8:00pm ET")
    else:
        use_yf_extended = False

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
def fetch_polygon(ticker: str, period: str, interval: str, key: str,
                  extended: bool = False) -> pd.DataFrame:
    """Fetch OHLCV bars from Polygon.io Aggregates endpoint."""
    multiplier, timespan = interval_to_polygon(interval)
    from_date, to_date = period_to_dates(period)
    ext_param = "&include_otc=true" if extended else ""
    # extended hours param only on intraday (minute/hour timespan)
    ext_hours = "&extended_hours=true" if (extended and timespan in ["minute", "hour"]) else ""
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{ticker.upper()}/range"
        f"/{multiplier}/{timespan}/{from_date}/{to_date}"
        f"?adjusted=true&sort=asc&limit=50000{ext_hours}{ext_param}&apiKey={key}"
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

@st.cache_data(ttl=30)
def fetch_yfinance_extended(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """
    Fetch OHLCV including pre/post market via yfinance (free).
    Only meaningful for intraday intervals — daily bars have no extended hours concept.
    """
    if not YF_AVAILABLE:
        return pd.DataFrame()
    # Map app interval to yfinance interval string
    yf_interval_map = {
        "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1h", "1d": "1d", "1wk": "1wk"
    }
    yf_interval = yf_interval_map.get(interval, "1d")
    # yfinance period string is already compatible
    try:
        raw = yf.download(
            ticker, period=period, interval=yf_interval,
            prepost=True, progress=False, auto_adjust=True
        )
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        raw = raw.dropna()
        raw.index = pd.to_datetime(raw.index, utc=True).tz_convert("America/New_York")
        return raw[["Open", "High", "Low", "Close", "Volume"]]
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=30)
def fetch_yfinance_regular(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """Fetch regular-hours OHLCV via yfinance (free, no API key needed)."""
    if not YF_AVAILABLE:
        return pd.DataFrame()
    yf_interval_map = {
        "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1h", "1d": "1d", "1wk": "1wk"
    }
    yf_interval = yf_interval_map.get(interval, "1d")
    try:
        raw = yf.download(
            ticker, period=period, interval=yf_interval,
            prepost=False, progress=False, auto_adjust=True
        )
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        raw = raw.dropna()
        raw.index = pd.to_datetime(raw.index, utc=True).tz_convert("America/New_York")
        return raw[["Open", "High", "Low", "Close", "Volume"]]
    except Exception:
        return pd.DataFrame()

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
if not use_yfinance and not api_key:
    st.warning("Enter your Polygon.io API key or switch to yfinance in the sidebar.")
    st.stop()

# Route to the right data source
if extended_hours and use_yf_extended:
    # Extended hours always uses yfinance fallback when checkbox is on
    with st.spinner("Fetching extended hours data via yfinance…"):
        df = fetch_yfinance_extended(ticker, period, interval)
    data_source = "yfinance (extended hours)"
elif use_yfinance:
    with st.spinner("Fetching data via yfinance…"):
        df = fetch_yfinance_regular(ticker, period, interval)
    data_source = "yfinance"
else:
    with st.spinner("Fetching data from Polygon.io…"):
        df = fetch_polygon(ticker, period, interval, api_key,
                           extended=extended_hours)
    data_source = "Polygon.io" + (" (extended hours)" if extended_hours else "")

if df.empty:
    st.error(
        f"No data returned for **{ticker}** via {data_source}. "
        "Check the ticker symbol and your API key. "
        "Note: commodities use Polygon format e.g. `C:XAUUSD` (gold), `C:WTIUSD` (oil). "
        "Crypto uses `X:BTCUSD`. For yfinance extended hours, use standard tickers like AAPL, SPY."
    )
    st.stop()

# Label extended hours bars (outside 9:30am–4:00pm ET)
if extended_hours and hasattr(df.index, "hour"):
    market_open  = (df.index.hour > 9) | ((df.index.hour == 9) & (df.index.minute >= 30))
    market_close = df.index.hour < 16
    df["Session"] = "Regular"
    df.loc[~market_open,  "Session"] = "Pre-Market"
    df.loc[~market_close, "Session"] = "After-Hours"
else:
    df["Session"] = "Regular"

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
# SMART MONEY UPGRADES
# =========================

# --- ATR / structure context ---
df["Prev_Close"] = df["Close"].shift(1)
df["TR"] = np.maximum.reduce([
    df["High"] - df["Low"],
    (df["High"] - df["Prev_Close"]).abs(),
    (df["Low"] - df["Prev_Close"]).abs(),
])
df["ATR"] = df["TR"].rolling(14).mean()
df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()
df["VWAP_Trend"] = np.where(df["Close"] >= df["VWAP"], 1, -1)
df["Price_Trend"] = np.where(df["EMA50"] >= df["EMA200"], 1, -1)

# --- 1) Whale clustering: sustained activity instead of one-candle spikes ---
df["Whale_Cluster"] = (df["Whale_Tier"] >= 2).rolling(5).sum().fillna(0)
df["Mega_Cluster"] = (df["Whale_Tier"] == 3).rolling(10).sum().fillna(0)

# --- Improved hidden accumulation / distribution filters ---
df["Range_Compression"] = df["Range"].rolling(5).mean() < df["Range"].rolling(20).mean()
df["Smart_Accum"] = (
    (df["Whale_Cluster"] >= 2) &
    (df["Close"] >= df["VWAP"]) &
    (df["OBV_Slope"] > 0) &
    (df["Range_Compression"].fillna(False))
)
df["Smart_Dist"] = (
    (df["Whale_Cluster"] >= 2) &
    (df["Close"] <= df["VWAP"]) &
    (df["OBV_Slope"] < 0) &
    (df["Range_Compression"].fillna(False))
)

# --- 2) Smart money regime detection ---
def classify_smart_money_regime(frame: pd.DataFrame) -> str:
    """Classify current market regime using whale cluster, VWAP, OBV and trend context."""
    if len(frame) < 30:
        return "Not enough data"
    recent = frame.tail(5)
    last = frame.iloc[-1]
    whale_cluster = recent["Whale_Cluster"].max() >= 2
    obv_up = recent["OBV_Slope"].sum() > 0
    obv_down = recent["OBV_Slope"].sum() < 0
    above_vwap = last["Close"] >= last["VWAP"]
    below_vwap = last["Close"] < last["VWAP"]
    trending_up = last["EMA50"] > last["EMA200"] and last["MACD"] > last["Signal"]
    trending_down = last["EMA50"] < last["EMA200"] and last["MACD"] < last["Signal"]
    compression = bool(recent["Range_Compression"].fillna(False).any())

    if whale_cluster and above_vwap and obv_up and compression:
        return "🟢 Accumulation"
    if whale_cluster and below_vwap and obv_down and compression:
        return "🔴 Distribution"
    if trending_up and above_vwap:
        return "📈 Bull Trend"
    if trending_down and below_vwap:
        return "📉 Bear Trend"
    return "⚪ Chop / No clear edge"

df["Smart_Regime"] = classify_smart_money_regime(df)

# --- 3) Multi-timeframe alignment ---
def add_light_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """Small indicator set used for higher-timeframe confirmation."""
    frame = frame.copy().dropna()
    if frame.empty:
        return frame
    delta = frame["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    frame["RSI"] = 100 - (100 / (1 + rs))
    frame["EMA12"] = frame["Close"].ewm(span=12, adjust=False).mean()
    frame["EMA26"] = frame["Close"].ewm(span=26, adjust=False).mean()
    frame["MACD"] = frame["EMA12"] - frame["EMA26"]
    frame["Signal"] = frame["MACD"].ewm(span=9, adjust=False).mean()
    tp_local = (frame["High"] + frame["Low"] + frame["Close"]) / 3
    frame["VWAP"] = (tp_local * frame["Volume"]).cumsum() / frame["Volume"].replace(0, np.nan).cumsum()
    frame["EMA50"] = frame["Close"].ewm(span=50, adjust=False).mean()
    frame["EMA200"] = frame["Close"].ewm(span=200, adjust=False).mean()
    frame["Vol_Avg"] = frame["Volume"].rolling(20).mean()
    frame["Vol_Std"] = frame["Volume"].rolling(20).std()
    frame["Vol_Z"] = (frame["Volume"] - frame["Vol_Avg"]) / frame["Vol_Std"]
    frame["Whale_Tier"] = pd.cut(
        frame["Vol_Z"].fillna(0),
        bins=[-np.inf, 1, 2, 3, np.inf],
        labels=[0, 1, 2, 3]
    ).astype(int)
    frame["Whale_Cluster"] = (frame["Whale_Tier"] >= 2).rolling(5).sum().fillna(0)
    return frame

def timeframe_bias(frame: pd.DataFrame) -> str:
    if frame is None or frame.empty or len(frame) < 30:
        return "Unknown"
    last = frame.iloc[-1]
    bullish = (last["Close"] > last["VWAP"]) + (last["EMA50"] > last["EMA200"]) + (last["MACD"] > last["Signal"])
    bearish = (last["Close"] < last["VWAP"]) + (last["EMA50"] < last["EMA200"]) + (last["MACD"] < last["Signal"])
    if bullish >= 2:
        return "Bullish"
    if bearish >= 2:
        return "Bearish"
    return "Neutral"

@st.cache_data(ttl=300)
def get_mtf_alignment(ticker: str):
    """Use yfinance for quick higher-timeframe confirmation, even when main source is Polygon."""
    if not YF_AVAILABLE:
        return {"Daily": "Unavailable", "1H": "Unavailable", "Current": "Available"}, "Unavailable"
    try:
        daily = add_light_indicators(fetch_yfinance_regular(ticker, "6mo", "1d"))
        hourly = add_light_indicators(fetch_yfinance_regular(ticker, "1mo", "1h"))
        daily_bias = timeframe_bias(daily)
        hourly_bias = timeframe_bias(hourly)
        current_bias = timeframe_bias(df)
        biases = {"Daily": daily_bias, "1H": hourly_bias, "Current": current_bias}
        bull_count = sum(v == "Bullish" for v in biases.values())
        bear_count = sum(v == "Bearish" for v in biases.values())
        if bull_count >= 2:
            alignment = "🟢 Bullish alignment"
        elif bear_count >= 2:
            alignment = "🔴 Bearish alignment"
        else:
            alignment = "⚪ Mixed / wait"
        return biases, alignment
    except Exception:
        return {"Daily": "Error", "1H": "Error", "Current": timeframe_bias(df)}, "Unavailable"

# --- 4) Actionable trade engine ---
def build_trade_plan(frame: pd.DataFrame) -> dict:
    """Create simple educational entry/stop/target zones from the current signal context."""
    last = frame.iloc[-1]
    atr = last["ATR"] if not np.isnan(last["ATR"]) and last["ATR"] > 0 else frame["Close"].pct_change().rolling(14).std().iloc[-1] * last["Close"]
    atr = atr if not np.isnan(atr) and atr > 0 else last["Close"] * 0.02
    regime = last["Smart_Regime"]
    buy_case = ("Accumulation" in regime or "Bull" in regime) and last["Close"] >= last["VWAP"]
    sell_case = ("Distribution" in regime or "Bear" in regime) and last["Close"] <= last["VWAP"]

    if buy_case:
        entry = max(last["VWAP"], last["Close"] - 0.5 * atr)
        stop = entry - 1.5 * atr
        target = entry + 3.0 * atr
        bias = "Long bias"
    elif sell_case:
        entry = min(last["VWAP"], last["Close"] + 0.5 * atr)
        stop = entry + 1.5 * atr
        target = entry - 3.0 * atr
        bias = "Short / avoid-long bias"
    else:
        entry = stop = target = np.nan
        bias = "No clean setup"

    rr = abs(target - entry) / abs(entry - stop) if not np.isnan(entry) and entry != stop else np.nan
    return {"bias": bias, "entry": entry, "stop": stop, "target": target, "rr": rr}

trade_plan = build_trade_plan(df)

# --- 5) Backtesting engine: quick validation of the whale/regime idea ---
def backtest_whale_strategy(frame: pd.DataFrame, hold_bars: int = 5) -> dict:
    """Simple long-only backtest. Entry = smart accumulation or bull trend + whale cluster. Exit = fixed hold."""
    test = frame.copy().dropna(subset=["Close", "VWAP", "Whale_Cluster", "MACD", "Signal"])
    if len(test) < hold_bars + 30:
        return {"trades": 0, "win_rate": np.nan, "avg_return": np.nan, "max_drawdown": np.nan}
    entry_signal = (
        ((test["Smart_Accum"]) | ((test["Close"] > test["VWAP"]) & (test["MACD"] > test["Signal"]))) &
        (test["Whale_Cluster"] >= 1)
    )
    entries = np.where(entry_signal)[0]
    returns = []
    last_exit = -1
    for i in entries:
        if i <= last_exit or i + hold_bars >= len(test):
            continue
        entry_price = test["Close"].iloc[i]
        exit_price = test["Close"].iloc[i + hold_bars]
        returns.append((exit_price / entry_price) - 1)
        last_exit = i + hold_bars
    if not returns:
        return {"trades": 0, "win_rate": np.nan, "avg_return": np.nan, "max_drawdown": np.nan}
    r = pd.Series(returns)
    equity = (1 + r).cumprod()
    drawdown = equity / equity.cummax() - 1
    return {
        "trades": int(len(r)),
        "win_rate": float((r > 0).mean() * 100),
        "avg_return": float(r.mean() * 100),
        "max_drawdown": float(drawdown.min() * 100),
    }

backtest_stats = backtest_whale_strategy(df)


# =========================
# BUY / SELL SCORE SYSTEM
# =========================
def compute_buy_sell_score(frame: pd.DataFrame) -> dict:
    """Transparent confluence score. 0-100 buy score and 0-100 sell/avoid score."""
    last = frame.iloc[-1]
    buy_score = 0
    sell_score = 0
    buy_reasons = []
    sell_reasons = []

    # 1) VWAP location — institutional fair value
    if last["Close"] > last["VWAP"]:
        buy_score += 22
        buy_reasons.append("Price above VWAP")
    else:
        sell_score += 22
        sell_reasons.append("Price below VWAP")

    # 2) OBV flow — accumulation/distribution
    if last["OBV_Slope"] > 0:
        buy_score += 18
        buy_reasons.append("OBV rising")
    elif last["OBV_Slope"] < 0:
        sell_score += 18
        sell_reasons.append("OBV falling")

    # 3) MACD momentum confirmation
    if last["MACD"] > last["Signal"]:
        buy_score += 14
        buy_reasons.append("MACD bullish")
    else:
        sell_score += 14
        sell_reasons.append("MACD bearish")

    # 4) RSI timing context
    if 40 <= last["RSI"] <= 65:
        buy_score += 12
        buy_reasons.append("RSI healthy / not overbought")
    elif last["RSI"] > 70:
        sell_score += 12
        sell_reasons.append("RSI overbought")
    elif last["RSI"] < 35:
        buy_score += 8
        buy_reasons.append("RSI oversold bounce area")

    # 5) Whale participation
    if last["Whale_Tier"] >= 2:
        if last["Buy_Pct"] >= 0.5:
            buy_score += 12
            buy_reasons.append("Whale buying pressure")
        else:
            sell_score += 12
            sell_reasons.append("Whale selling pressure")

    # 6) Dark pool proxy
    if bool(last.get("DarkPool_Accum", False)):
        buy_score += 12
        buy_reasons.append("Dark pool accumulation proxy")
    if bool(last.get("DarkPool_Dist", False)):
        sell_score += 12
        sell_reasons.append("Dark pool distribution proxy")

    # 7) Smart regime / cluster confirmation
    regime = str(last.get("Smart_Regime", ""))
    if "Accumulation" in regime or "Bull" in regime:
        buy_score += 10
        buy_reasons.append(f"Smart regime: {regime}")
    elif "Distribution" in regime or "Bear" in regime:
        sell_score += 10
        sell_reasons.append(f"Smart regime: {regime}")

    buy_score = int(min(buy_score, 100))
    sell_score = int(min(sell_score, 100))

    if buy_score >= 70 and buy_score > sell_score:
        signal = "🟢 BUY"
    elif sell_score >= 70 and sell_score > buy_score:
        signal = "🔴 SELL / AVOID"
    else:
        signal = "⚖️ NEUTRAL"

    return {
        "signal": signal,
        "buy_score": buy_score,
        "sell_score": sell_score,
        "confidence_gap": abs(buy_score - sell_score),
        "buy_reasons": buy_reasons,
        "sell_reasons": sell_reasons,
    }

score = compute_buy_sell_score(df)

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
    st.metric("Current regime", df["Smart_Regime"].iloc[-1] if "Smart_Regime" in df.columns else "—")
    st.metric("5-bar whale cluster", f"{int(df['Whale_Cluster'].iloc[-1])}/5" if "Whale_Cluster" in df.columns else "—")
    st.divider()
    if currency == "CAD":
        st.caption(f"💱 USD/CAD rate used: {usdcad_rate:.4f}")
    else:
        st.caption("💱 Prices in USD")

# =========================
# PRICE CHART
# =========================
fig_price = go.Figure()

# Regular session candles
reg = df[df["Session"] == "Regular"]
fig_price.add_candlestick(
    x=reg.index,
    open=reg["Open"], high=reg["High"], low=reg["Low"], close=reg["Close"],
    name="Regular Session",
    increasing_line_color="#1D9E75", decreasing_line_color="#D85A30"
)

# Pre-market and after-hours candles (dimmed, shown only when toggle is on)
if extended_hours:
    pre = df[df["Session"] == "Pre-Market"]
    if not pre.empty:
        fig_price.add_candlestick(
            x=pre.index,
            open=pre["Open"], high=pre["High"], low=pre["Low"], close=pre["Close"],
            name="Pre-Market",
            increasing_line_color="#7BC8A4", decreasing_line_color="#E8A090",
            opacity=0.5
        )
    aft = df[df["Session"] == "After-Hours"]
    if not aft.empty:
        fig_price.add_candlestick(
            x=aft.index,
            open=aft["Open"], high=aft["High"], low=aft["Low"], close=aft["Close"],
            name="After-Hours",
            increasing_line_color="#A0BEE8", decreasing_line_color="#C8A07B",
            opacity=0.5
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
ext_label = " · Extended Hours" if extended_hours else ""
fig_price.update_layout(
    height=650, xaxis_rangeslider_visible=False,
    title=f"{ticker} — Price + Whale Activity ({interval_label}{ext_label} · {currency})",
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

fig_cluster = go.Figure()
fig_cluster.add_trace(go.Bar(
    x=df.index,
    y=df["Whale_Cluster"],
    name="5-bar Whale Cluster",
    marker_color="#A32D2D"
))
fig_cluster.add_hline(y=2, line_dash="dash", line_color="#EF9F27", annotation_text="Cluster threshold")
fig_cluster.update_layout(
    height=280,
    title="Whale Clustering — Sustained Institutional Activity",
    yaxis=dict(range=[0, 5], title="Whale bars in last 5")
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

def compute_alerts(df: pd.DataFrame):
    """
    Scan the last 3 bars for buying AND selling whale confluence.
    Returns (sell_alerts, buy_alerts) each sorted by severity.
    """
    sell_alerts, buy_alerts = [], []
    recent = df.tail(3).copy()

    for idx, row in recent.iterrows():
        ts = idx.strftime("%Y-%m-%d %H:%M") if hasattr(idx, "hour") else idx.strftime("%Y-%m-%d")

        # ── SELL SIGNALS ──────────────────────────────────────────
        s_signals, s_severity = [], 0

        if row["Whale_Tier"] >= 2 and row["Buy_Pct"] < 0.5:
            tier_name = TIER_LABELS[int(row["Whale_Tier"])]
            sell_pct = round((1 - row["Buy_Pct"]) * 100)
            s_signals.append(f"{tier_name} selling bar ({sell_pct}% sell pressure)")
            s_severity += 3 if row["Whale_Tier"] == 3 else 2
        elif row["Whale_Tier"] == 1 and row["Buy_Pct"] < 0.5:
            sell_pct = round((1 - row["Buy_Pct"]) * 100)
            s_signals.append(f"Elevated selling volume ({sell_pct}% sell pressure)")
            s_severity += 1

        if row.get("DarkPool_Dist", False):
            s_signals.append("Dark pool distribution detected")
            s_severity += 2
        if row["Close"] < row["VWAP"]:
            s_signals.append("Price trading below VWAP")
            s_severity += 1
        if row["OBV_Slope"] < 0:
            s_signals.append("OBV declining (outflow)")
            s_severity += 1
        if row["RSI"] > 65:
            s_signals.append(f"RSI overbought at {row['RSI']:.0f}")
            s_severity += 1
        if row["MACD"] < row["Signal"] and row["Hist"] < 0:
            s_signals.append("MACD bearish — below signal line")
            s_severity += 1
        if row["Whale_Score"] > 60 and row["Buy_Pct"] < 0.5:
            s_signals.append(f"High whale score ({row['Whale_Score']:.0f}) with selling bias")
            s_severity += 1

        if len(s_signals) >= 2:
            sell_alerts.append({
                "time": ts, "signals": s_signals, "severity": s_severity,
                "price": row["Close"],
                "pressure_pct": round((1 - row["Buy_Pct"]) * 100),
            })

        # ── BUY SIGNALS ───────────────────────────────────────────
        b_signals, b_severity = [], 0

        if row["Whale_Tier"] >= 2 and row["Buy_Pct"] >= 0.5:
            tier_name = TIER_LABELS[int(row["Whale_Tier"])]
            buy_pct = round(row["Buy_Pct"] * 100)
            b_signals.append(f"{tier_name} buying bar ({buy_pct}% buy pressure)")
            b_severity += 3 if row["Whale_Tier"] == 3 else 2
        elif row["Whale_Tier"] == 1 and row["Buy_Pct"] >= 0.5:
            buy_pct = round(row["Buy_Pct"] * 100)
            b_signals.append(f"Elevated buying volume ({buy_pct}% buy pressure)")
            b_severity += 1

        if row.get("DarkPool_Accum", False):
            b_signals.append("Dark pool accumulation detected")
            b_severity += 2
        if row["Close"] > row["VWAP"]:
            b_signals.append("Price trading above VWAP")
            b_severity += 1
        if row["OBV_Slope"] > 0:
            b_signals.append("OBV rising (inflow)")
            b_severity += 1
        if row["RSI"] < 35:
            b_signals.append(f"RSI oversold at {row['RSI']:.0f}")
            b_severity += 1
        if row["MACD"] > row["Signal"] and row["Hist"] > 0:
            b_signals.append("MACD bullish — above signal line")
            b_severity += 1
        if row["Whale_Score"] > 60 and row["Buy_Pct"] >= 0.5:
            b_signals.append(f"High whale score ({row['Whale_Score']:.0f}) with buying bias")
            b_severity += 1

        if len(b_signals) >= 2:
            buy_alerts.append({
                "time": ts, "signals": b_signals, "severity": b_severity,
                "price": row["Close"],
                "pressure_pct": round(row["Buy_Pct"] * 100),
            })

    return (
        sorted(sell_alerts, key=lambda x: x["severity"], reverse=True),
        sorted(buy_alerts,  key=lambda x: x["severity"], reverse=True),
    )

sell_alerts, buy_alerts = compute_alerts(df)

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

st.caption(f"Last updated: {now_str}  ·  Source: {data_source}")

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
# SMART MONEY DASHBOARD
# =========================
st.subheader("🧠 Smart Money Decision Dashboard")
mtf_biases, mtf_alignment = get_mtf_alignment(ticker)

score_cols = st.columns(4)
with score_cols[0]:
    st.metric("Buy/Sell Signal", score["signal"])
with score_cols[1]:
    st.metric("Buy Score", f"{score['buy_score']}/100")
with score_cols[2]:
    st.metric("Sell Score", f"{score['sell_score']}/100")
with score_cols[3]:
    st.metric("Confidence Gap", score["confidence_gap"])

st.progress(score["buy_score"] / 100)
with st.expander("Score breakdown"):
    st.markdown("**Bullish factors**")
    st.write(score["buy_reasons"] if score["buy_reasons"] else "No strong bullish factors.")
    st.markdown("**Bearish factors**")
    st.write(score["sell_reasons"] if score["sell_reasons"] else "No strong bearish factors.")

dash_cols = st.columns(4)
with dash_cols[0]:
    st.metric("Regime", df["Smart_Regime"].iloc[-1])
with dash_cols[1]:
    st.metric("Multi-timeframe", mtf_alignment)
    st.caption(" · ".join([f"{k}: {v}" for k, v in mtf_biases.items()]))
with dash_cols[2]:
    st.metric("Trade bias", trade_plan["bias"])
    if not np.isnan(trade_plan["entry"]):
        st.caption(
            f"Entry: {currency_symbol}{trade_plan['entry']:,.2f} · "
            f"Stop: {currency_symbol}{trade_plan['stop']:,.2f} · "
            f"Target: {currency_symbol}{trade_plan['target']:,.2f} · "
            f"R/R: {trade_plan['rr']:.1f}"
        )
    else:
        st.caption("No clean entry zone from current confluence.")
with dash_cols[3]:
    st.metric("Backtest trades", backtest_stats["trades"])
    if backtest_stats["trades"] > 0:
        st.caption(
            f"Win rate: {backtest_stats['win_rate']:.0f}% · "
            f"Avg: {backtest_stats['avg_return']:+.2f}% · "
            f"Max DD: {backtest_stats['max_drawdown']:.2f}%"
        )
    else:
        st.caption("No historical signals found in this period.")

st.info(
    "This dashboard is educational. The trade plan and backtest are simple rules, not financial advice. "
    "Use them to validate signal quality before risking money."
)

# Add smart accumulation / distribution zones to the price chart
fig_price.add_trace(go.Scatter(
    x=df[df["Smart_Accum"]].index,
    y=df[df["Smart_Accum"]]["Low"] * 0.992,
    mode="markers",
    marker=dict(size=16, symbol="star", color="#1D9E75", line=dict(width=1, color="white")),
    name="⭐ Smart Accumulation"
))
fig_price.add_trace(go.Scatter(
    x=df[df["Smart_Dist"]].index,
    y=df[df["Smart_Dist"]]["High"] * 1.008,
    mode="markers",
    marker=dict(size=16, symbol="star", color="#D85A30", line=dict(width=1, color="white")),
    name="⭐ Smart Distribution"
))


# Shaded proxy zones — easier to see institutional accumulation/distribution clusters
for idx in df[df["Smart_Accum"]].index:
    fig_price.add_vrect(
        x0=idx,
        x1=idx,
        fillcolor="green",
        opacity=0.12,
        line_width=0,
    )

for idx in df[df["Smart_Dist"]].index:
    fig_price.add_vrect(
        x0=idx,
        x1=idx,
        fillcolor="red",
        opacity=0.12,
        line_width=0,
    )

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
st.plotly_chart(fig_cluster, use_container_width=True)

st.subheader("Technical Indicators")
st.plotly_chart(fig_rsi,  use_container_width=True)
st.plotly_chart(fig_macd, use_container_width=True)
st.plotly_chart(fig_obv,  use_container_width=True)

# =========================
# NEWS & SENTIMENT ENGINE
# =========================

# Keyword lists for simple rule-based sentiment
BULLISH_WORDS = [
    "surge", "soar", "rally", "beat", "record", "growth", "strong", "upgrade",
    "buy", "outperform", "bullish", "breakout", "gain", "rise", "profit",
    "positive", "exceed", "boost", "rebound", "recovery", "high", "up"
]
BEARISH_WORDS = [
    "drop", "fall", "slump", "miss", "downgrade", "sell", "bearish", "decline",
    "loss", "weak", "below", "cut", "risk", "concern", "warn", "crash",
    "plunge", "negative", "down", "low", "layoff", "investigation", "lawsuit"
]

def score_headline(text: str) -> float:
    """Return sentiment score: positive = bullish, negative = bearish."""
    text_lower = text.lower()
    score = 0
    for w in BULLISH_WORDS:
        if w in text_lower:
            score += 1
    for w in BEARISH_WORDS:
        if w in text_lower:
            score -= 1
    return score

@st.cache_data(ttl=600)
def fetch_news(ticker: str) -> list[dict]:
    """
    Fetch recent news from multiple RSS sources for the ticker.
    Returns list of {title, source, url, published, sentiment_score}.
    """
    # Clean ticker for search (remove exchange prefixes like X: C:)
    clean = re.sub(r"^[A-Z]+:", "", ticker.upper()).replace("-", " ")

    feeds = [
        # Yahoo Finance RSS
        f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US",
        # Seeking Alpha
        f"https://seekingalpha.com/api/sa/combined/{ticker}.xml",
        # Benzinga via MarketWatch
        f"https://www.marketwatch.com/rss/realtimeheadlines",
        # Google News for ticker name
        f"https://news.google.com/rss/search?q={clean}+stock&hl=en-US&gl=US&ceid=US:en",
        # Investing.com via RSS bridge (public)
        f"https://www.investing.com/rss/news_285.rss",
    ]

    articles = []
    seen = set()
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:8]:
                title = entry.get("title", "").strip()
                if not title or title in seen:
                    continue
                # Filter to ticker-relevant headlines only (for broad feeds)
                if clean.lower() not in title.lower() and len(articles) > 5:
                    continue
                seen.add(title)
                pub = entry.get("published", entry.get("updated", ""))
                try:
                    pub_dt = pd.to_datetime(pub, utc=True)
                    pub_str = pub_dt.strftime("%Y-%m-%d %H:%M UTC")
                    age_hrs = (datetime.utcnow() - pub_dt.replace(tzinfo=None)).total_seconds() / 3600
                except Exception:
                    pub_str = pub[:20] if pub else "—"
                    age_hrs = 999
                articles.append({
                    "title": title,
                    "source": feed.feed.get("title", url.split("/")[2]),
                    "url": entry.get("link", "#"),
                    "published": pub_str,
                    "age_hrs": age_hrs,
                    "sentiment": score_headline(title),
                })
        except Exception:
            continue

    # Sort by recency
    articles = sorted(articles, key=lambda x: x["age_hrs"])
    return articles[:20]

def news_momentum(articles: list[dict]) -> dict:
    """Aggregate sentiment into a momentum reading."""
    if not articles:
        return {"score": 0, "label": "No data", "bullish": 0, "bearish": 0, "neutral": 0}
    scores = [a["sentiment"] for a in articles]
    total = sum(scores)
    bullish = sum(1 for s in scores if s > 0)
    bearish = sum(1 for s in scores if s < 0)
    neutral = sum(1 for s in scores if s == 0)
    avg = total / len(scores)
    if avg >= 1.5:
        label = "🚀 Very Bullish"
    elif avg >= 0.5:
        label = "📈 Bullish"
    elif avg <= -1.5:
        label = "🔻 Very Bearish"
    elif avg <= -0.5:
        label = "📉 Bearish"
    else:
        label = "➡️ Neutral"
    return {
        "score": round(avg, 2),
        "label": label,
        "bullish": bullish,
        "bearish": bearish,
        "neutral": neutral,
        "total": len(scores),
    }

# ── Fetch & display ──────────────────────────────────────────────────────────
st.divider()
st.subheader(f"📰 News & Sentiment — {ticker.upper()}")

with st.spinner("Fetching latest news…"):
    articles = fetch_news(ticker)

momentum = news_momentum(articles)

# Momentum summary metrics
news_cols = st.columns([2, 1, 1, 1, 1])
with news_cols[0]:
    color = "#1D9E75" if momentum["score"] > 0 else ("#D85A30" if momentum["score"] < 0 else "#888")
    st.markdown(
        f"<div style='font-size:22px; font-weight:600; color:{color}'>"
        f"{momentum['label']}</div>"
        f"<div style='font-size:13px; color:#888'>News sentiment score: {momentum['score']:+.2f}</div>",
        unsafe_allow_html=True
    )
with news_cols[1]:
    st.metric("📰 Headlines", momentum.get("total", 0))
with news_cols[2]:
    st.metric("🟢 Bullish", momentum["bullish"])
with news_cols[3]:
    st.metric("🔴 Bearish", momentum["bearish"])
with news_cols[4]:
    st.metric("➡️ Neutral", momentum["neutral"])

st.markdown("")

# Sentiment bar chart
if articles:
    sent_scores = [a["sentiment"] for a in articles]
    sent_labels = [a["title"][:55] + "…" if len(a["title"]) > 55 else a["title"] for a in articles]
    sent_colors = ["#1D9E75" if s > 0 else ("#D85A30" if s < 0 else "#888888") for s in sent_scores]

    fig_news = go.Figure(go.Bar(
        x=sent_scores,
        y=sent_labels,
        orientation="h",
        marker_color=sent_colors,
        hovertemplate="<b>%{y}</b><br>Sentiment: %{x:+d}<extra></extra>",
    ))
    fig_news.add_vline(x=0, line_color="gray", line_width=1)
    fig_news.update_layout(
        height=max(300, len(articles) * 28),
        title="Headline Sentiment (green = bullish · red = bearish)",
        xaxis_title="Sentiment Score",
        yaxis=dict(autorange="reversed"),
        margin=dict(l=10, r=10, t=40, b=10),
    )
    st.plotly_chart(fig_news, use_container_width=True)

# Article list with links
st.markdown("**Recent Headlines**")
for a in articles[:15]:
    age = f"{a['age_hrs']:.0f}h ago" if a["age_hrs"] < 48 else f"{a['age_hrs']/24:.0f}d ago"
    icon = "🟢" if a["sentiment"] > 0 else ("🔴" if a["sentiment"] < 0 else "⚪")
    line = f"{icon} [{a['title']}]({a['url']})  \n" \
           f"<span style='font-size:11px;color:#888'>{a['source']} · {age}</span>"
    st.markdown(line, unsafe_allow_html=True)

# =========================
# AUTO-REFRESH LOOP
# =========================
if realtime_on:
    if "last_refresh_placeholder" in dir():
        last_refresh_placeholder.caption(f"Next refresh in {refresh_interval}s")
    time.sleep(refresh_interval)
    st.cache_data.clear()
    st.rerun()