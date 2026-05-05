import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, timedelta
import time
import re

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False

try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except ImportError:
    FEEDPARSER_AVAILABLE = False

# =========================================================
# CONFIG
# =========================================================
st.set_page_config(page_title="Institutional Flow Pro", layout="wide")
st.title("🐋 Institutional Flow Pro Dashboard")
st.caption("VWAP · RSI · MACD · OBV · Whale Flow · Dark-Pool Proxy · Watchlist Scanner · Hidden Gem Scanner · Sector Flow · Risk Panel")

SECTOR_MAP = {
    "SPY": "Index", "QQQ": "Index", "DIA": "Index", "IWM": "Index",
    "SOXL": "Semiconductors", "SOXS": "Semiconductors", "SMH": "Semiconductors", "NVDA": "Semiconductors", "AMD": "Semiconductors", "INTC": "Semiconductors", "AVGO": "Semiconductors", "TSM": "Semiconductors",
    "XLE": "Energy", "USO": "Energy", "HUC.TO": "Energy", "CNQ.TO": "Energy", "SU.TO": "Energy", "XOM": "Energy", "CVX": "Energy",
    "GLD": "Gold", "GDX": "Gold Miners", "GDXU": "Gold Miners", "KGC": "Gold Miners", "ABX.TO": "Gold Miners", "AEM.TO": "Gold Miners",
    "XLF": "Financials", "RY.TO": "Financials", "TD.TO": "Financials", "BNS.TO": "Financials", "JPM": "Financials", "BAC": "Financials",
    "ITA": "Defense", "LMT": "Defense", "RTX": "Defense", "NOC": "Defense", "GD": "Defense",
    "HACK": "Cybersecurity", "PANW": "Cybersecurity", "CRWD": "Cybersecurity", "ZS": "Cybersecurity",
    "BTC-USD": "Crypto", "ETH-USD": "Crypto", "X:BTCUSD": "Crypto", "X:ETHUSD": "Crypto",
    "SHOP.TO": "Technology", "SHOP": "Technology", "AAPL": "Technology", "MSFT": "Technology", "GOOGL": "Technology", "META": "Technology", "TSLA": "Consumer/EV",
}

BULLISH_WORDS = ["surge", "soar", "rally", "beat", "record", "growth", "strong", "upgrade", "buy", "outperform", "bullish", "breakout", "gain", "rise", "profit", "positive", "exceed", "boost", "rebound", "recovery", "high", "up", "launch", "approval"]
BEARISH_WORDS = ["drop", "fall", "slump", "miss", "downgrade", "sell", "bearish", "decline", "loss", "weak", "below", "cut", "risk", "concern", "warn", "crash", "plunge", "negative", "down", "low", "layoff", "investigation", "lawsuit", "probe", "halt"]

TIER_LABELS = {0: "Normal", 1: "Elevated", 2: "🐋 Whale", 3: "🔴 Mega-whale"}
TIER_COLORS = {0: "gray", 1: "#EF9F27", 2: "#D85A30", 3: "#A32D2D"}

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.header("Settings")
    api_key = st.text_input("Polygon.io API Key", type="password", help="Optional. yfinance works without an API key. Polygon is better for intraday.")
    data_source_choice = st.radio("Data source", ["yfinance (free)", "Polygon.io"], index=0)
    use_yfinance = data_source_choice == "yfinance (free)"

    st.divider()
    ticker = st.text_input("Main ticker", "SPY").strip().upper()
    interval = st.selectbox("Interval", ["5m", "15m", "30m", "1h", "1d", "1wk"], index=4)
    PERIOD_OPTIONS = {
        "5m": ["5d", "1mo"], "15m": ["5d", "1mo", "3mo"], "30m": ["5d", "1mo", "3mo"],
        "1h": ["5d", "1mo", "3mo", "6mo", "1y", "2y"], "1d": ["5d", "1mo", "3mo", "6mo", "1y", "2y", "5y"],
        "1wk": ["1mo", "3mo", "6mo", "1y", "2y", "5y"],
    }
    period = st.selectbox("Period", PERIOD_OPTIONS[interval], index=min(3, len(PERIOD_OPTIONS[interval])-1))
    currency = st.selectbox("Display currency", ["USD", "CAD"], index=0)
    currency_symbol = "$" if currency == "USD" else "CA$"

    extended_hours = st.toggle("Extended hours", value=False, help="Uses yfinance pre/post market when available. Daily/weekly bars do not have extended hours.")

    st.divider()
    st.subheader("Watchlist Scanner")
    default_watchlist = "SPY, QQQ, SOXL, SOXS, NVDA, AMD, INTC, TSLA, AAPL, MSFT, XLE, GLD, GDX, HUC.TO, SHOP.TO"
    watchlist_text = st.text_area("Tickers", default_watchlist, height=120)
    scan_period = st.selectbox("Scanner period", ["5d", "1mo", "3mo", "6mo", "1y"], index=2)
    scan_interval = st.selectbox("Scanner interval", ["1h", "1d"], index=1)
    max_scan = st.slider("Max tickers to scan", 5, 50, 20)

    st.divider()
    st.subheader("Hidden Gem Scanner")
    default_hidden_list = "CLS, SANM, FLEX, JBL, BLD, ATKR, MOD, STRL, GVA, ACM, WLDN, PRIM, VRT, SMCI, MU, ALGM, CECO, AEHR, IESC, HPS.A.TO, ATS.TO, DXT.TO, NOA.TO, TVK.TO, NFI.TO, MDA.TO"
    hidden_text = st.text_area("Hidden gem tickers", default_hidden_list, height=120)
    hidden_max_scan = st.slider("Max hidden-gem tickers", 5, 100, 30)
    min_hidden_score = st.slider("Minimum hidden-gem score", 40, 90, 65)

    st.divider()
    st.subheader("Alerts")
    buy_alert_threshold = st.slider("Buy alert threshold", 50, 95, 70)
    sell_alert_threshold = st.slider("Sell alert threshold", 50, 95, 70)

    st.divider()
    realtime_on = st.toggle("Auto-refresh", value=False)
    refresh_interval = st.selectbox("Refresh every", [30, 60, 120, 300], index=1, disabled=not realtime_on)

# =========================================================
# DATA HELPERS
# =========================================================
def period_to_dates(period: str):
    end = datetime.today()
    mapping = {"5d": 5, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730, "5y": 1825}
    start = end - timedelta(days=mapping.get(period, 365))
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

def interval_to_polygon(interval: str):
    return {"5m": (5, "minute"), "15m": (15, "minute"), "30m": (30, "minute"), "1h": (1, "hour"), "1d": (1, "day"), "1wk": (1, "week")}.get(interval, (1, "day"))

@st.cache_data(ttl=60)
def fetch_yfinance(ticker: str, period: str, interval: str, extended: bool = False) -> pd.DataFrame:
    if not YF_AVAILABLE:
        return pd.DataFrame()
    try:
        raw = yf.download(ticker, period=period, interval=interval, prepost=extended, auto_adjust=False, progress=False)
        if raw.empty:
            return pd.DataFrame()
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        raw = raw.dropna()
        keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in raw.columns]
        raw = raw[keep]
        try:
            raw.index = pd.to_datetime(raw.index, utc=True).tz_convert("America/New_York")
        except Exception:
            raw.index = pd.to_datetime(raw.index)
        return raw
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=60)
def fetch_polygon(ticker: str, period: str, interval: str, key: str) -> pd.DataFrame:
    if not key:
        return pd.DataFrame()
    try:
        multiplier, timespan = interval_to_polygon(interval)
        from_date, to_date = period_to_dates(period)
        url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from_date}/{to_date}?adjusted=true&sort=asc&limit=50000&apiKey={key}"
        data = requests.get(url, timeout=15).json()
        if not data.get("results"):
            return pd.DataFrame()
        df = pd.DataFrame(data["results"])
        df["Date"] = pd.to_datetime(df["t"], unit="ms", utc=True).dt.tz_convert("America/New_York")
        df = df.set_index("Date")
        df = df.rename(columns={"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"})
        return df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def fetch_usdcad(key: str = "") -> float:
    # yfinance fallback avoids requiring Polygon just for conversion.
    if YF_AVAILABLE:
        try:
            fx = yf.download("CAD=X", period="5d", interval="1d", progress=False, auto_adjust=False)
            if isinstance(fx.columns, pd.MultiIndex):
                fx.columns = fx.columns.get_level_values(0)
            return float(fx["Close"].dropna().iloc[-1])
        except Exception:
            pass
    if key:
        try:
            url = f"https://api.polygon.io/v2/aggs/ticker/C:USDCAD/range/1/day/2020-01-01/{datetime.today().strftime('%Y-%m-%d')}?adjusted=true&sort=desc&limit=1&apiKey={key}"
            data = requests.get(url, timeout=10).json()
            return float(data["results"][0]["c"])
        except Exception:
            pass
    return 1.36

def get_data(ticker: str, period: str, interval: str) -> tuple[pd.DataFrame, str]:
    if use_yfinance or not api_key:
        df = fetch_yfinance(ticker, period, interval, extended_hours)
        return df, "yfinance"
    df = fetch_polygon(ticker, period, interval, api_key)
    if df.empty:
        df = fetch_yfinance(ticker, period, interval, extended_hours)
        return df, "yfinance fallback"
    return df, "Polygon.io"

# =========================================================
# INDICATORS AND SCORING
# =========================================================
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy().dropna()
    if df.empty or len(df) < 30:
        return df

    # Session label
    try:
        market_open = (df.index.hour > 9) | ((df.index.hour == 9) & (df.index.minute >= 30))
        market_close = df.index.hour < 16
        df["Session"] = "Regular"
        df.loc[~market_open, "Session"] = "Pre-Market"
        df.loc[~market_close, "Session"] = "After-Hours"
    except Exception:
        df["Session"] = "Regular"

    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))

    df["EMA12"] = df["Close"].ewm(span=12, adjust=False).mean()
    df["EMA26"] = df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = df["EMA12"] - df["EMA26"]
    df["Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["Hist"] = df["MACD"] - df["Signal"]

    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    df["VWAP"] = (tp * df["Volume"]).cumsum() / df["Volume"].replace(0, np.nan).cumsum()

    df["OBV"] = np.where(df["Close"] > df["Close"].shift(1), df["Volume"], np.where(df["Close"] < df["Close"].shift(1), -df["Volume"], 0)).cumsum()
    df["OBV_Slope"] = df["OBV"].diff()
    df["OBV_MA"] = df["OBV"].rolling(10).mean()

    df["Vol_Avg"] = df["Volume"].rolling(20).mean()
    df["Vol_Std"] = df["Volume"].rolling(20).std()
    df["Vol_Z"] = (df["Volume"] - df["Vol_Avg"]) / df["Vol_Std"].replace(0, np.nan)
    df["Whale_Tier"] = pd.cut(df["Vol_Z"].fillna(0), bins=[-np.inf, 1, 2, 3, np.inf], labels=[0, 1, 2, 3]).astype(int)

    df["Body"] = (df["Close"] - df["Open"]).abs()
    df["Range"] = df["High"] - df["Low"]
    df["Body_Ratio"] = df["Body"] / df["Range"].replace(0, np.nan)
    df["VWAP_Diff"] = (df["Close"] - df["VWAP"]).abs() / df["VWAP"].replace(0, np.nan)
    df["Whale"] = df["Volume"] > df["Vol_Avg"] * 2

    df["Buy_Pct"] = (df["Close"] - df["Low"]) / (df["High"] - df["Low"] + 1e-9)
    df["Buy_Vol"] = df["Volume"] * df["Buy_Pct"]
    df["Sell_Vol"] = df["Volume"] * (1 - df["Buy_Pct"])

    score_parts = pd.DataFrame(index=df.index)
    score_parts["vol_s"] = (df["Vol_Z"].clip(0, 3) / 3 * 30).fillna(0)
    score_parts["body_s"] = ((1 - df["Body_Ratio"].clip(0, 1)) * 20).fillna(0)
    score_parts["vwap_s"] = ((1 - df["VWAP_Diff"].clip(0, 0.01) / 0.01) * 20).fillna(0)
    score_parts["obv_s"] = np.where(df["OBV_Slope"] > 0, 15, 0)
    score_parts["rsi_s"] = ((1 - (df["RSI"].clip(50, 80) - 50) / 30) * 15).fillna(0)
    df["Whale_Score"] = score_parts.sum(axis=1).clip(0, 100)

    df["DarkPool_Accum"] = (df["Volume"] > df["Vol_Avg"] * 1.8) & (df["Body_Ratio"] < 0.35) & (df["VWAP_Diff"] < 0.003) & (df["OBV_Slope"] > 0)
    df["DarkPool_Dist"] = (df["Volume"] > df["Vol_Avg"] * 1.8) & (df["Body_Ratio"] < 0.35) & (df["VWAP_Diff"] < 0.003) & (df["RSI"] > 65)

    df["Prev_Close"] = df["Close"].shift(1)
    df["TR"] = np.maximum.reduce([df["High"] - df["Low"], (df["High"] - df["Prev_Close"]).abs(), (df["Low"] - df["Prev_Close"]).abs()])
    df["ATR"] = df["TR"].rolling(14).mean()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()

    df["Whale_Cluster"] = (df["Whale_Tier"] >= 2).rolling(5).sum().fillna(0)
    df["Mega_Cluster"] = (df["Whale_Tier"] == 3).rolling(10).sum().fillna(0)
    df["Range_Compression"] = df["Range"].rolling(5).mean() < df["Range"].rolling(20).mean()
    df["Smart_Accum"] = (df["Whale_Cluster"] >= 2) & (df["Close"] >= df["VWAP"]) & (df["OBV_Slope"] > 0) & df["Range_Compression"].fillna(False)
    df["Smart_Dist"] = (df["Whale_Cluster"] >= 2) & (df["Close"] <= df["VWAP"]) & (df["OBV_Slope"] < 0) & df["Range_Compression"].fillna(False)

    streak, count = [], 0
    for val in df["Whale_Tier"] >= 2:
        count = count + 1 if val else 0
        streak.append(count)
    df["Whale_Streak"] = streak
    return df

def classify_regime(df: pd.DataFrame) -> str:
    if df.empty or len(df) < 30:
        return "Not enough data"
    recent = df.tail(5)
    last = df.iloc[-1]
    whale_cluster = recent["Whale_Cluster"].max() >= 2
    obv_up = recent["OBV_Slope"].sum() > 0
    obv_down = recent["OBV_Slope"].sum() < 0
    above_vwap = last["Close"] >= last["VWAP"]
    trending_up = last["EMA50"] > last["EMA200"] and last["MACD"] > last["Signal"]
    trending_down = last["EMA50"] < last["EMA200"] and last["MACD"] < last["Signal"]
    compression = bool(recent["Range_Compression"].fillna(False).any())
    if whale_cluster and above_vwap and obv_up and compression:
        return "🟢 Accumulation"
    if whale_cluster and not above_vwap and obv_down and compression:
        return "🔴 Distribution"
    if trending_up and above_vwap:
        return "📈 Bull Trend"
    if trending_down and not above_vwap:
        return "📉 Bear Trend"
    return "⚪ Chop / No clear edge"

def compute_scores(df: pd.DataFrame) -> dict:
    last = df.iloc[-1]
    buy = sell = 0
    buy_reasons, sell_reasons = [], []
    components = {}

    # Trend score
    trend_buy = 0; trend_sell = 0
    if last["Close"] > last["VWAP"]: trend_buy += 15; buy_reasons.append("Price above VWAP")
    else: trend_sell += 15; sell_reasons.append("Price below VWAP")
    if last["EMA50"] > last["EMA200"]: trend_buy += 10; buy_reasons.append("EMA50 above EMA200")
    else: trend_sell += 10; sell_reasons.append("EMA50 below EMA200")
    components["Trend"] = (trend_buy, trend_sell)

    # Flow score
    flow_buy = 0; flow_sell = 0
    if last["OBV_Slope"] > 0: flow_buy += 15; buy_reasons.append("OBV rising")
    else: flow_sell += 15; sell_reasons.append("OBV falling")
    if last["Whale_Tier"] >= 2 and last["Buy_Pct"] >= 0.5: flow_buy += 10; buy_reasons.append("Whale buying pressure")
    elif last["Whale_Tier"] >= 2 and last["Buy_Pct"] < 0.5: flow_sell += 10; sell_reasons.append("Whale selling pressure")
    if last["DarkPool_Accum"] or last["Smart_Accum"]: flow_buy += 15; buy_reasons.append("Accumulation proxy")
    if last["DarkPool_Dist"] or last["Smart_Dist"]: flow_sell += 15; sell_reasons.append("Distribution proxy")
    components["Flow"] = (flow_buy, flow_sell)

    # Momentum score
    mom_buy = 0; mom_sell = 0
    if last["MACD"] > last["Signal"]: mom_buy += 10; buy_reasons.append("MACD bullish")
    else: mom_sell += 10; sell_reasons.append("MACD bearish")
    if 40 <= last["RSI"] <= 65: mom_buy += 10; buy_reasons.append("RSI healthy")
    elif last["RSI"] > 70: mom_sell += 10; sell_reasons.append("RSI overbought")
    elif last["RSI"] < 35: mom_buy += 8; buy_reasons.append("RSI oversold bounce area")
    components["Momentum"] = (mom_buy, mom_sell)

    buy = sum(v[0] for v in components.values())
    sell = sum(v[1] for v in components.values())
    buy = int(min(100, buy)); sell = int(min(100, sell))
    signal = "🟢 BUY" if buy >= buy_alert_threshold and buy > sell else "🔴 SELL / AVOID" if sell >= sell_alert_threshold and sell > buy else "⚖️ NEUTRAL"
    return {"buy": buy, "sell": sell, "signal": signal, "gap": abs(buy-sell), "buy_reasons": buy_reasons, "sell_reasons": sell_reasons, "components": components}

def build_trade_plan(df: pd.DataFrame, scores: dict) -> dict:
    last = df.iloc[-1]
    atr = last.get("ATR", np.nan)
    if pd.isna(atr) or atr <= 0:
        atr = last["Close"] * 0.02
    if scores["buy"] > scores["sell"] and scores["buy"] >= buy_alert_threshold:
        entry = max(last["VWAP"], last["Close"] - 0.5 * atr)
        stop = entry - 1.5 * atr
        target = entry + 3.0 * atr
        bias = "Long bias"
    elif scores["sell"] > scores["buy"] and scores["sell"] >= sell_alert_threshold:
        entry = min(last["VWAP"], last["Close"] + 0.5 * atr)
        stop = entry + 1.5 * atr
        target = entry - 3.0 * atr
        bias = "Short / avoid-long bias"
    else:
        return {"bias": "No clean setup", "entry": np.nan, "stop": np.nan, "target": np.nan, "rr": np.nan, "risk_per_share": np.nan}
    rr = abs(target - entry) / abs(entry - stop) if entry != stop else np.nan
    return {"bias": bias, "entry": entry, "stop": stop, "target": target, "rr": rr, "risk_per_share": abs(entry-stop)}

def backtest_strategy(df: pd.DataFrame, hold_bars: int = 5) -> dict:
    test = df.copy().dropna(subset=["Close", "VWAP", "Whale_Cluster", "MACD", "Signal"])
    if len(test) < hold_bars + 30:
        return {"trades": 0, "win_rate": np.nan, "avg_return": np.nan, "max_drawdown": np.nan}
    signal = (((test["Smart_Accum"]) | ((test["Close"] > test["VWAP"]) & (test["MACD"] > test["Signal"]))) & (test["Whale_Cluster"] >= 1))
    entries = np.where(signal)[0]
    returns, last_exit = [], -1
    for i in entries:
        if i <= last_exit or i + hold_bars >= len(test):
            continue
        ret = test["Close"].iloc[i + hold_bars] / test["Close"].iloc[i] - 1
        returns.append(ret)
        last_exit = i + hold_bars
    if not returns:
        return {"trades": 0, "win_rate": np.nan, "avg_return": np.nan, "max_drawdown": np.nan}
    r = pd.Series(returns)
    equity = (1 + r).cumprod()
    dd = equity / equity.cummax() - 1
    return {"trades": int(len(r)), "win_rate": float((r > 0).mean() * 100), "avg_return": float(r.mean() * 100), "max_drawdown": float(dd.min() * 100)}

# =========================================================
# NEWS
# =========================================================
def score_headline(text: str) -> int:
    t = text.lower()
    return sum(w in t for w in BULLISH_WORDS) - sum(w in t for w in BEARISH_WORDS)

@st.cache_data(ttl=900)
def fetch_news(ticker: str) -> list[dict]:
    if not FEEDPARSER_AVAILABLE:
        return []
    clean = re.sub(r"^[A-Z]+:", "", ticker.upper()).replace("-", " ")
    feeds = [
        f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US",
        f"https://news.google.com/rss/search?q={clean}+stock&hl=en-US&gl=US&ceid=US:en",
    ]
    articles, seen = [], set()
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                title = entry.get("title", "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                pub = entry.get("published", entry.get("updated", ""))
                try:
                    pub_dt = pd.to_datetime(pub, utc=True)
                    age_hrs = (datetime.utcnow() - pub_dt.replace(tzinfo=None)).total_seconds() / 3600
                except Exception:
                    age_hrs = 999
                articles.append({"title": title, "url": entry.get("link", "#"), "source": feed.feed.get("title", "RSS"), "sentiment": score_headline(title), "age_hrs": age_hrs})
        except Exception:
            pass
    return sorted(articles, key=lambda x: x["age_hrs"])[:20]

def news_momentum(articles: list[dict]) -> dict:
    if not articles:
        return {"score": 0, "label": "No data", "bullish": 0, "bearish": 0, "neutral": 0, "total": 0}
    scores = [a["sentiment"] for a in articles]
    avg = sum(scores) / len(scores)
    if avg >= 0.75: label = "📈 Bullish"
    elif avg <= -0.75: label = "📉 Bearish"
    else: label = "➡️ Neutral"
    return {"score": round(avg, 2), "label": label, "bullish": sum(s > 0 for s in scores), "bearish": sum(s < 0 for s in scores), "neutral": sum(s == 0 for s in scores), "total": len(scores)}


# =========================================================
# HIDDEN GEM SCANNER
# =========================================================
@st.cache_data(ttl=3600)
def fetch_fundamentals_yf(ticker: str) -> dict:
    """Lightweight fundamentals from yfinance. Fields vary by ticker, so every value is optional."""
    if not YF_AVAILABLE:
        return {}
    try:
        tk = yf.Ticker(ticker)
        info = tk.get_info() or {}
        # Cash flow / financial statements are best-effort and can be unavailable for some Canadian tickers.
        cf = tk.cashflow
        fin = tk.financials
        bs = tk.balance_sheet

        def latest_two(frame, row_names):
            if frame is None or frame.empty:
                return (np.nan, np.nan)
            for r in row_names:
                if r in frame.index:
                    vals = pd.to_numeric(frame.loc[r], errors="coerce").dropna()
                    if len(vals) >= 2:
                        return float(vals.iloc[0]), float(vals.iloc[1])
                    if len(vals) == 1:
                        return float(vals.iloc[0]), np.nan
            return (np.nan, np.nan)

        fcf_now, fcf_prev = latest_two(cf, ["Free Cash Flow", "FreeCashFlow"])
        ocf_now, ocf_prev = latest_two(cf, ["Operating Cash Flow", "Total Cash From Operating Activities", "OperatingCashFlow"])
        capex_now, capex_prev = latest_two(cf, ["Capital Expenditure", "CapitalExpenditure"])
        rev_now, rev_prev = latest_two(fin, ["Total Revenue", "TotalRevenue"])
        op_now, op_prev = latest_two(fin, ["Operating Income", "OperatingIncome"])
        debt_now, debt_prev = latest_two(bs, ["Total Debt", "TotalDebt"])
        cash_now, cash_prev = latest_two(bs, ["Cash And Cash Equivalents", "Cash And Cash Equivalents And Short Term Investments", "CashAndCashEquivalents"])

        if pd.isna(fcf_now) and pd.notna(ocf_now) and pd.notna(capex_now):
            fcf_now = ocf_now + capex_now  # capex is often negative in yfinance statements
        if pd.isna(fcf_prev) and pd.notna(ocf_prev) and pd.notna(capex_prev):
            fcf_prev = ocf_prev + capex_prev

        market_cap = info.get("marketCap", np.nan)
        enterprise_value = info.get("enterpriseValue", np.nan)
        ebitda = info.get("ebitda", np.nan)
        pe = info.get("trailingPE", np.nan)
        forward_pe = info.get("forwardPE", np.nan)
        shares = info.get("sharesOutstanding", np.nan)
        inst_pct = info.get("heldPercentInstitutions", np.nan)
        beta = info.get("beta", np.nan)
        sector = info.get("sector", SECTOR_MAP.get(ticker.upper(), "Other"))
        name = info.get("shortName", ticker)

        return {
            "Name": name,
            "Sector": sector or SECTOR_MAP.get(ticker.upper(), "Other"),
            "MarketCap": market_cap,
            "EnterpriseValue": enterprise_value,
            "EBITDA": ebitda,
            "FCF": fcf_now,
            "FCF_Prev": fcf_prev,
            "OCF": ocf_now,
            "Revenue": rev_now,
            "Revenue_Prev": rev_prev,
            "OperatingIncome": op_now,
            "OperatingIncome_Prev": op_prev,
            "Debt": debt_now,
            "Debt_Prev": debt_prev,
            "Cash": cash_now,
            "PE": pe,
            "ForwardPE": forward_pe,
            "Shares": shares,
            "InstitutionalPct": inst_pct,
            "Beta": beta,
        }
    except Exception:
        return {}

def safe_growth(now, prev):
    if pd.isna(now) or pd.isna(prev) or prev == 0:
        return np.nan
    # If previous was negative, percent growth can be misleading; use directional improvement instead.
    return (now - prev) / abs(prev) * 100

def score_hidden_gem(fund: dict, df: pd.DataFrame) -> dict:
    """Score 0-100 for 'quality improving + under followed + flow confirming'."""
    last = df.iloc[-1]
    fcf = fund.get("FCF", np.nan)
    fcf_prev = fund.get("FCF_Prev", np.nan)
    revenue = fund.get("Revenue", np.nan)
    revenue_prev = fund.get("Revenue_Prev", np.nan)
    op = fund.get("OperatingIncome", np.nan)
    op_prev = fund.get("OperatingIncome_Prev", np.nan)
    debt = fund.get("Debt", np.nan)
    debt_prev = fund.get("Debt_Prev", np.nan)
    market_cap = fund.get("MarketCap", np.nan)
    ev = fund.get("EnterpriseValue", np.nan)
    ebitda = fund.get("EBITDA", np.nan)
    inst_pct = fund.get("InstitutionalPct", np.nan)

    fcf_growth = safe_growth(fcf, fcf_prev)
    rev_growth = safe_growth(revenue, revenue_prev)
    op_growth = safe_growth(op, op_prev)
    debt_change = safe_growth(debt, debt_prev)

    p_fcf = market_cap / fcf if pd.notna(market_cap) and pd.notna(fcf) and fcf > 0 else np.nan
    ev_ebitda = ev / ebitda if pd.notna(ev) and pd.notna(ebitda) and ebitda > 0 else np.nan
    fcf_yield = fcf / market_cap * 100 if pd.notna(market_cap) and market_cap > 0 and pd.notna(fcf) else np.nan

    fundamental = 0
    fund_reasons = []
    if pd.notna(fcf) and fcf > 0:
        fundamental += 10; fund_reasons.append("positive FCF")
    if pd.notna(fcf_growth):
        if fcf_growth > 25: fundamental += 15; fund_reasons.append("FCF growth >25%")
        elif fcf_growth > 10: fundamental += 10; fund_reasons.append("FCF growth >10%")
        elif fcf_growth > 0: fundamental += 5; fund_reasons.append("FCF improving")
    if pd.notna(rev_growth) and rev_growth > 5:
        fundamental += 7; fund_reasons.append("revenue growing")
    if pd.notna(op_growth) and op_growth > 10:
        fundamental += 8; fund_reasons.append("operating income improving")
    if pd.notna(debt_change) and debt_change <= 0:
        fundamental += 5; fund_reasons.append("debt stable/decreasing")
    fundamental = min(fundamental, 40)

    valuation = 0
    val_reasons = []
    if pd.notna(p_fcf):
        if p_fcf < 8: valuation += 12; val_reasons.append("P/FCF < 8")
        elif p_fcf < 15: valuation += 9; val_reasons.append("P/FCF < 15")
        elif p_fcf < 25: valuation += 5; val_reasons.append("P/FCF reasonable")
    if pd.notna(ev_ebitda):
        if ev_ebitda < 8: valuation += 8; val_reasons.append("EV/EBITDA < 8")
        elif ev_ebitda < 12: valuation += 5; val_reasons.append("EV/EBITDA < 12")
    if pd.notna(fcf_yield):
        if fcf_yield > 8: valuation += 7; val_reasons.append("FCF yield >8%")
        elif fcf_yield > 4: valuation += 4; val_reasons.append("FCF yield >4%")
    valuation = min(valuation, 25)

    flow = 0
    flow_reasons = []
    recent = df.tail(30)
    obv_up = recent["OBV"].iloc[-1] > recent["OBV"].iloc[0] if len(recent) >= 2 else False
    if last["Close"] >= last["VWAP"]:
        flow += 8; flow_reasons.append("above VWAP")
    if obv_up:
        flow += 10; flow_reasons.append("30-bar OBV rising")
    if recent["Whale_Cluster"].max() >= 2:
        flow += 8; flow_reasons.append("whale cluster")
    if recent["Smart_Accum"].sum() > recent["Smart_Dist"].sum():
        flow += 7; flow_reasons.append("more accumulation than distribution")
    if last["MACD"] > last["Signal"]:
        flow += 5; flow_reasons.append("MACD bullish")
    flow = min(flow, 30)

    under_radar = 0
    under_reasons = []
    if pd.notna(market_cap):
        if 300_000_000 <= market_cap <= 10_000_000_000:
            under_radar += 3; under_reasons.append("small/mid-cap size")
        elif market_cap < 300_000_000:
            under_radar -= 4; under_reasons.append("very small/high-risk")
    if pd.notna(inst_pct):
        if 0.20 <= inst_pct <= 0.75:
            under_radar += 4; under_reasons.append("institutional ownership present, not saturated")
        elif inst_pct > 0.9:
            under_radar -= 2; under_reasons.append("already heavily institution-owned")
    # low headline count proxy: no news or neutral news is treated as under-the-radar, not bullish by itself.
    under_radar = max(0, min(5, under_radar))

    total = int(min(100, fundamental + valuation + flow + under_radar))
    return {
        "HiddenGemScore": total,
        "FundamentalScore": int(fundamental),
        "ValuationScore": int(valuation),
        "FlowScore": int(flow),
        "UnderRadarScore": int(under_radar),
        "P/FCF": p_fcf,
        "EV/EBITDA": ev_ebitda,
        "FCFYield%": fcf_yield,
        "FCFGrowth%": fcf_growth,
        "RevenueGrowth%": rev_growth,
        "DebtChange%": debt_change,
        "Reasons": "; ".join(fund_reasons + val_reasons + flow_reasons + under_reasons),
    }

@st.cache_data(ttl=1800)
def scan_hidden_gems(tickers: tuple[str, ...], period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    rows = []
    for t in tickers:
        px = fetch_yfinance(t, period, interval, False)
        px = add_indicators(px)
        if px.empty or len(px) < 60:
            continue
        fund = fetch_fundamentals_yf(t)
        if not fund:
            fund = {"Name": t, "Sector": SECTOR_MAP.get(t, "Other")}
        hg = score_hidden_gem(fund, px)
        sc = compute_scores(px)
        reg = classify_regime(px)
        last = px.iloc[-1]
        rows.append({
            "Ticker": t,
            "Name": fund.get("Name", t),
            "Sector": fund.get("Sector", SECTOR_MAP.get(t, "Other")),
            "HiddenGemScore": hg["HiddenGemScore"],
            "Fundamentals": hg["FundamentalScore"],
            "Valuation": hg["ValuationScore"],
            "Flow": hg["FlowScore"],
            "UnderRadar": hg["UnderRadarScore"],
            "BuyScore": sc["buy"],
            "SellScore": sc["sell"],
            "Regime": reg,
            "Price": float(last["Close"]),
            "RSI": float(last["RSI"]),
            "WhaleScore": float(last["Whale_Score"]),
            "WhaleCluster": float(last["Whale_Cluster"]),
            "P/FCF": hg["P/FCF"],
            "EV/EBITDA": hg["EV/EBITDA"],
            "FCFYield%": hg["FCFYield%"],
            "FCFGrowth%": hg["FCFGrowth%"],
            "RevenueGrowth%": hg["RevenueGrowth%"],
            "DebtChange%": hg["DebtChange%"],
            "Reasons": hg["Reasons"],
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["HiddenGemScore", "Flow", "BuyScore"], ascending=False)
    return out

# =========================================================
# CHARTS
# =========================================================
def make_price_chart(df: pd.DataFrame, ticker: str, symbol: str) -> go.Figure:
    fig = go.Figure()
    fig.add_candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="Price")
    fig.add_trace(go.Scatter(x=df.index, y=df["VWAP"], name="VWAP", line=dict(width=2, dash="dot")))
    fig.add_trace(go.Scatter(x=df[df["DarkPool_Accum"]].index, y=df[df["DarkPool_Accum"]]["Low"]*0.997, mode="markers", marker=dict(size=14, symbol="triangle-up", color="#1D9E75"), name="Dark Pool Accum"))
    fig.add_trace(go.Scatter(x=df[df["DarkPool_Dist"]].index, y=df[df["DarkPool_Dist"]]["High"]*1.003, mode="markers", marker=dict(size=14, symbol="triangle-down", color="#D85A30"), name="Dark Pool Dist"))
    fig.add_trace(go.Scatter(x=df[df["Smart_Accum"]].index, y=df[df["Smart_Accum"]]["Low"]*0.992, mode="markers", marker=dict(size=17, symbol="star", color="#1D9E75", line=dict(width=1, color="white")), name="Smart Accum"))
    fig.add_trace(go.Scatter(x=df[df["Smart_Dist"]].index, y=df[df["Smart_Dist"]]["High"]*1.008, mode="markers", marker=dict(size=17, symbol="star", color="#D85A30", line=dict(width=1, color="white")), name="Smart Dist"))
    for tier in [1, 2, 3]:
        sub = df[df["Whale_Tier"] == tier]
        if sub.empty: continue
        fig.add_trace(go.Scatter(x=sub.index, y=sub["High"]*1.004, mode="markers", marker=dict(size={1:8,2:13,3:20}[tier], color=TIER_COLORS[tier], symbol="circle", line=dict(width=1, color="white")), name=TIER_LABELS[tier]))
    # shaded zones
    for idx in df[df["Smart_Accum"]].index:
        fig.add_vrect(x0=idx, x1=idx, fillcolor="green", opacity=0.12, line_width=0)
    for idx in df[df["Smart_Dist"]].index:
        fig.add_vrect(x0=idx, x1=idx, fillcolor="red", opacity=0.12, line_width=0)
    fig.update_layout(height=720, xaxis_rangeslider_visible=False, title=f"{ticker} Price + Institutional Flow", yaxis=dict(tickprefix=symbol), legend=dict(orientation="h", y=-0.12))
    return fig

def make_indicator_charts(df: pd.DataFrame):
    fig_rsi = go.Figure()
    fig_rsi.add_trace(go.Scatter(x=df.index, y=df["RSI"], name="RSI"))
    fig_rsi.add_hline(y=70, line_dash="dash"); fig_rsi.add_hline(y=30, line_dash="dash")
    fig_rsi.update_layout(height=330, title="RSI")

    fig_macd = go.Figure()
    fig_macd.add_trace(go.Scatter(x=df.index, y=df["MACD"], name="MACD"))
    fig_macd.add_trace(go.Scatter(x=df.index, y=df["Signal"], name="Signal"))
    fig_macd.add_bar(x=df.index, y=df["Hist"], name="Histogram")
    fig_macd.update_layout(height=360, title="MACD")

    fig_obv = go.Figure()
    fig_obv.add_trace(go.Scatter(x=df.index, y=df["OBV"], name="OBV"))
    fig_obv.add_trace(go.Scatter(x=df.index, y=df["OBV_MA"], name="OBV MA"))
    fig_obv.update_layout(height=340, title="OBV Flow")
    return fig_rsi, fig_macd, fig_obv

def make_volume_charts(df: pd.DataFrame):
    fig_score = go.Figure()
    fig_score.add_trace(go.Scatter(x=df.index, y=df["Whale_Score"], fill="tozeroy", name="Whale Score"))
    fig_score.add_hline(y=60, line_dash="dash"); fig_score.add_hline(y=80, line_dash="dash")
    fig_score.update_layout(height=320, title="Whale Composite Score", yaxis=dict(range=[0, 105]))

    whale = df[df["Whale_Tier"] >= 2]
    fig_bs = go.Figure()
    fig_bs.add_bar(x=whale.index, y=whale["Buy_Vol"], name="Buy Pressure")
    fig_bs.add_bar(x=whale.index, y=-whale["Sell_Vol"], name="Sell Pressure")
    fig_bs.update_layout(height=320, title="Whale Buy/Sell Pressure", barmode="relative")

    fig_cluster = go.Figure()
    fig_cluster.add_bar(x=df.index, y=df["Whale_Cluster"], name="5-bar cluster")
    fig_cluster.add_hline(y=2, line_dash="dash")
    fig_cluster.update_layout(height=280, title="Whale Clustering", yaxis=dict(range=[0,5]))
    return fig_score, fig_bs, fig_cluster

# =========================================================
# MAIN DATA
# =========================================================
main_df, source = get_data(ticker, period, interval)
if main_df.empty:
    st.error("No data returned. Try yfinance, a different ticker, or a different interval/period.")
    st.stop()

if currency == "CAD":
    fx = fetch_usdcad(api_key)
    for c in ["Open", "High", "Low", "Close"]:
        main_df[c] = main_df[c] * fx
else:
    fx = 1.0

main_df = add_indicators(main_df)
if main_df.empty or len(main_df) < 30:
    st.error("Not enough bars to calculate indicators. Try a longer period or larger interval.")
    st.stop()

regime = classify_regime(main_df)
scores = compute_scores(main_df)
trade_plan = build_trade_plan(main_df, scores)
backtest = backtest_strategy(main_df)
latest = main_df.iloc[-1]

# =========================================================
# TOP METRICS
# =========================================================
cols = st.columns(6)
prev_close = main_df["Close"].iloc[-2]
change = latest["Close"] - prev_close
pct = change / prev_close * 100
cols[0].metric(f"{ticker} Last", f"{currency_symbol}{latest['Close']:,.2f}", f"{change:+.2f} ({pct:+.2f}%)")
cols[1].metric("Signal", scores["signal"])
cols[2].metric("Buy Score", f"{scores['buy']}/100")
cols[3].metric("Sell Score", f"{scores['sell']}/100")
cols[4].metric("Regime", regime)
cols[5].metric("Whale Tier", TIER_LABELS[int(latest["Whale_Tier"])])
st.caption(f"Source: {source} · FX rate used: {fx:.4f} · Educational only, not financial advice.")

# =========================================================
# TABS
# =========================================================
tab_overview, tab_price, tab_volume, tab_indicators, tab_watchlist, tab_hidden, tab_sector, tab_news, tab_backtest, tab_settings = st.tabs([
    "Overview", "Price Chart", "Whale Flow", "Indicators", "Watchlist Scanner", "Hidden Gem Scanner", "Sector Flow", "News", "Backtest/Risk", "API Hooks"
])

with tab_overview:
    st.subheader("Decision Dashboard")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Buy", f"{scores['buy']}/100")
    c2.metric("Sell", f"{scores['sell']}/100")
    c3.metric("Confidence Gap", scores["gap"])
    c4.metric("Trade Bias", trade_plan["bias"])
    st.progress(scores["buy"] / 100)

    with st.expander("Score breakdown"):
        breakdown = pd.DataFrame([
            {"Component": k, "Buy Points": v[0], "Sell Points": v[1]} for k, v in scores["components"].items()
        ])
        st.dataframe(breakdown, use_container_width=True, hide_index=True)
        st.write("**Bullish factors:**", scores["buy_reasons"] or "None")
        st.write("**Bearish factors:**", scores["sell_reasons"] or "None")

    st.subheader("Smart Alerts")
    if scores["buy"] >= buy_alert_threshold and scores["buy"] > scores["sell"]:
        st.success("Strong bullish alignment. Consider waiting for a pullback/retest rather than chasing.")
    elif scores["sell"] >= sell_alert_threshold and scores["sell"] > scores["buy"]:
        st.error("Strong bearish/distribution alignment. Avoid longs or manage risk tightly.")
    else:
        st.info("No high-confidence setup right now.")

    st.subheader("Risk Management Panel")
    risk_cols = st.columns(5)
    if pd.notna(trade_plan["entry"]):
        risk_cols[0].metric("Entry Zone", f"{currency_symbol}{trade_plan['entry']:,.2f}")
        risk_cols[1].metric("Stop", f"{currency_symbol}{trade_plan['stop']:,.2f}")
        risk_cols[2].metric("Target", f"{currency_symbol}{trade_plan['target']:,.2f}")
        risk_cols[3].metric("R/R", f"{trade_plan['rr']:.1f}")
        acct = risk_cols[4].number_input("Account $", min_value=100.0, value=10000.0, step=500.0)
        risk_pct = st.slider("Risk per trade %", 0.25, 5.0, 1.0)
        shares = int((acct * risk_pct / 100) / trade_plan["risk_per_share"]) if trade_plan["risk_per_share"] > 0 else 0
        st.write(f"Suggested max position by risk: **{shares} shares/units** at {risk_pct}% risk.")
    else:
        st.info("No clean entry/stop/target zone from current confluence.")

with tab_price:
    st.plotly_chart(make_price_chart(main_df, ticker, currency_symbol), use_container_width=True)

with tab_volume:
    fs, fbs, fc = make_volume_charts(main_df)
    st.plotly_chart(fs, use_container_width=True)
    st.plotly_chart(fbs, use_container_width=True)
    st.plotly_chart(fc, use_container_width=True)

with tab_indicators:
    rsi, macd, obv = make_indicator_charts(main_df)
    st.plotly_chart(rsi, use_container_width=True)
    st.plotly_chart(macd, use_container_width=True)
    st.plotly_chart(obv, use_container_width=True)

# =========================================================
# WATCHLIST SCANNER
# =========================================================
@st.cache_data(ttl=300)
def scan_watchlist(tickers: tuple[str, ...], scan_period: str, scan_interval: str) -> pd.DataFrame:
    rows = []
    for t in tickers:
        df = fetch_yfinance(t, scan_period, scan_interval, False)
        df = add_indicators(df)
        if df.empty or len(df) < 30:
            continue
        sc = compute_scores(df)
        reg = classify_regime(df)
        last = df.iloc[-1]
        bt = backtest_strategy(df)
        rows.append({
            "Ticker": t,
            "Sector": SECTOR_MAP.get(t, "Other"),
            "Signal": sc["signal"],
            "Buy": sc["buy"],
            "Sell": sc["sell"],
            "Gap": sc["gap"],
            "Regime": reg,
            "Price": float(last["Close"]),
            "RSI": float(last["RSI"]),
            "WhaleScore": float(last["Whale_Score"]),
            "WhaleTier": TIER_LABELS[int(last["Whale_Tier"])],
            "WhaleCluster": float(last["Whale_Cluster"]),
            "BacktestTrades": bt["trades"],
            "BacktestWinRate": bt["win_rate"],
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["Buy", "Gap"], ascending=False)
    return out

watchlist = tuple([x.strip().upper() for x in watchlist_text.replace("\n", ",").split(",") if x.strip()][:max_scan])

with tab_watchlist:
    st.subheader("Watchlist Scanner")
    st.caption("Ranks tickers by the same flow/trend/momentum scoring engine. Uses yfinance for fast batch scanning.")
    if st.button("Run scan", type="primary"):
        st.cache_data.clear()
    scan_df = scan_watchlist(watchlist, scan_period, scan_interval)
    if scan_df.empty:
        st.warning("No scan results. Try fewer tickers or a longer period.")
    else:
        st.dataframe(scan_df, use_container_width=True, hide_index=True)
        c1, c2 = st.columns(2)
        c1.write("### Top accumulation")
        c1.dataframe(scan_df.sort_values("Buy", ascending=False).head(10), use_container_width=True, hide_index=True)
        c2.write("### Top distribution")
        c2.dataframe(scan_df.sort_values("Sell", ascending=False).head(10), use_container_width=True, hide_index=True)


with tab_hidden:
    st.subheader("Hidden Gem Scanner")
    st.caption(
        "Looks for the Celestica-style setup: improving cash flow/operations, still-reasonable valuation, "
        "and early institutional-flow confirmation. Fundamentals are best-effort from yfinance and may be missing for some tickers."
    )
    hidden_list = tuple([x.strip().upper() for x in hidden_text.replace("\n", ",").split(",") if x.strip()][:hidden_max_scan])
    h1, h2, h3 = st.columns([1, 1, 2])
    with h1:
        run_hidden = st.button("Run hidden-gem scan", type="primary")
    with h2:
        st.metric("Tickers queued", len(hidden_list))
    with h3:
        st.info("Tip: use boring industrials, suppliers, EMS, infrastructure, aerospace, niche tech, and TSX mid-caps — not already-hyped mega caps.")

    if run_hidden:
        st.cache_data.clear()

    hidden_df = scan_hidden_gems(hidden_list, "1y", "1d")
    if hidden_df.empty:
        st.warning("No hidden-gem results. Try different tickers or install/update yfinance.")
    else:
        filtered = hidden_df[hidden_df["HiddenGemScore"] >= min_hidden_score].copy()
        display_df = filtered if not filtered.empty else hidden_df.head(15)
        st.write("### Ranked candidates")
        st.dataframe(
            display_df[[
                "Ticker", "Name", "Sector", "HiddenGemScore", "Fundamentals", "Valuation", "Flow", "UnderRadar",
                "BuyScore", "SellScore", "Regime", "Price", "P/FCF", "EV/EBITDA", "FCFYield%", "FCFGrowth%", "RevenueGrowth%", "Reasons"
            ]],
            use_container_width=True,
            hide_index=True,
        )

        top = hidden_df.head(10).copy()
        fig_hg = go.Figure()
        fig_hg.add_bar(x=top["Ticker"], y=top["Fundamentals"], name="Fundamentals")
        fig_hg.add_bar(x=top["Ticker"], y=top["Valuation"], name="Valuation")
        fig_hg.add_bar(x=top["Ticker"], y=top["Flow"], name="Flow")
        fig_hg.add_bar(x=top["Ticker"], y=top["UnderRadar"], name="Under-radar")
        fig_hg.update_layout(barmode="stack", height=440, title="Hidden Gem Score Composition — Top 10", yaxis_title="Score")
        st.plotly_chart(fig_hg, use_container_width=True)

        st.write("### Best setups by category")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.write("**Best fundamental improvement**")
            st.dataframe(hidden_df.sort_values("Fundamentals", ascending=False).head(5)[["Ticker", "Fundamentals", "FCFGrowth%", "RevenueGrowth%", "Reasons"]], use_container_width=True, hide_index=True)
        with c2:
            st.write("**Cheapest cash-flow valuation**")
            st.dataframe(hidden_df.sort_values("Valuation", ascending=False).head(5)[["Ticker", "Valuation", "P/FCF", "EV/EBITDA", "FCFYield%", "Reasons"]], use_container_width=True, hide_index=True)
        with c3:
            st.write("**Strongest quiet accumulation**")
            st.dataframe(hidden_df.sort_values("Flow", ascending=False).head(5)[["Ticker", "Flow", "BuyScore", "WhaleScore", "WhaleCluster", "Regime", "Reasons"]], use_container_width=True, hide_index=True)

        st.warning(
            "Important: this is a discovery engine, not a buy button. After a candidate appears, verify filings, debt maturities, customer concentration, margins, and guidance manually."
        )

with tab_sector:
    st.subheader("Sector Flow")
    scan_df = scan_watchlist(watchlist, scan_period, scan_interval)
    if scan_df.empty:
        st.warning("Run a watchlist scan first or add valid tickers.")
    else:
        sector = scan_df.groupby("Sector", as_index=False).agg(
            AvgBuy=("Buy", "mean"), AvgSell=("Sell", "mean"), AvgWhale=("WhaleScore", "mean"), Count=("Ticker", "count")
        )
        sector["NetFlow"] = sector["AvgBuy"] - sector["AvgSell"]
        sector = sector.sort_values("NetFlow", ascending=False)
        st.dataframe(sector, use_container_width=True, hide_index=True)
        fig = go.Figure(go.Bar(x=sector["Sector"], y=sector["NetFlow"], name="Net Flow"))
        fig.update_layout(height=420, title="Sector Net Flow: Avg Buy Score - Avg Sell Score")
        st.plotly_chart(fig, use_container_width=True)

with tab_news:
    st.subheader(f"News & Sentiment — {ticker}")
    articles = fetch_news(ticker)
    momentum = news_momentum(articles)
    cols = st.columns(5)
    cols[0].metric("Sentiment", momentum["label"], momentum["score"])
    cols[1].metric("Headlines", momentum["total"])
    cols[2].metric("Bullish", momentum["bullish"])
    cols[3].metric("Bearish", momentum["bearish"])
    cols[4].metric("Neutral", momentum["neutral"])
    if not articles:
        st.info("No RSS news available. Install feedparser or check the ticker.")
    else:
        for a in articles[:15]:
            icon = "🟢" if a["sentiment"] > 0 else "🔴" if a["sentiment"] < 0 else "⚪"
            age = f"{a['age_hrs']:.0f}h ago" if a["age_hrs"] < 48 else f"{a['age_hrs']/24:.0f}d ago"
            st.markdown(f"{icon} [{a['title']}]({a['url']})  \n<small>{a['source']} · {age}</small>", unsafe_allow_html=True)

with tab_backtest:
    st.subheader("Backtest & Risk Validation")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Trades", backtest["trades"])
    c2.metric("Win Rate", f"{backtest['win_rate']:.0f}%" if pd.notna(backtest["win_rate"]) else "—")
    c3.metric("Avg Return", f"{backtest['avg_return']:+.2f}%" if pd.notna(backtest["avg_return"]) else "—")
    c4.metric("Max Drawdown", f"{backtest['max_drawdown']:.2f}%" if pd.notna(backtest["max_drawdown"]) else "—")
    st.info("Backtest is intentionally simple: long-only entries on smart accumulation or VWAP+MACD with whale cluster, fixed hold. Use it as a sanity check, not proof.")

with tab_settings:
    st.subheader("Paid API Hooks / Future Integrations")
    st.write("Real dark-pool prints and options flow require paid/official feeds. This file includes proxy logic only, and avoids pretending proxy data is real prints.")
    st.code("""
# Optional future hooks you can wire later:
# fetch_finra_ats_trf(ticker) -> real ATS/TRF dark pool volume
# fetch_unusual_options(ticker) -> call/put sweeps, premium, expiry, strike
# send_telegram_alert(message) -> push alert
# send_discord_alert(message) -> Discord webhook
# fetch_fmp_fundamentals(ticker) -> richer historical FCF/margins for Hidden Gem Scanner
""", language="python")
    st.write("Required packages:")
    st.code("pip install streamlit yfinance pandas numpy plotly requests feedparser", language="bash")

if realtime_on:
    time.sleep(refresh_interval)
    st.cache_data.clear()
    st.rerun()
