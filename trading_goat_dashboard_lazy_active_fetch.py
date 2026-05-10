import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from datetime import datetime, timedelta
import time
import re
import os
import json
from pathlib import Path
from io import BytesIO
import base64

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

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import StandardScaler
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False

# =========================================================
# ENHANCED CONFIG WITH DARK MODE
# =========================================================
st.set_page_config(
    page_title="Institutional Flow Pro+", 
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'About': "Professional Trading Dashboard v2.0"
    }
)

# Custom CSS for enhanced UI
st.markdown("""
<style>
    /* Main container styling */
    .main {
        background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
    }
    
    /* Metric cards */
    .metric-card {
        background: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0.05) 100%);
        border-radius: 15px;
        padding: 20px;
        margin: 10px 0;
        border: 1px solid rgba(255,255,255,0.1);
        box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
        backdrop-filter: blur(4px);
    }
    
    /* Enhanced headers */
    h1, h2, h3 {
        color: #ffffff !important;
        font-weight: 700 !important;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    }
    
    /* Button styling */
    .stButton>button {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 10px;
        border: none;
        padding: 10px 24px;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(102,126,234,0.4);
    }
    
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: rgba(0,0,0,0.2);
        border-radius: 10px;
        padding: 5px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        border-radius: 8px;
        color: rgba(255,255,255,0.7);
        font-weight: 600;
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
    }
    
    /* Dataframe styling */
    .dataframe {
        background-color: rgba(0,0,0,0.3) !important;
        border-radius: 10px;
    }
    
    /* Alert boxes */
    .alert-box {
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
        border-left: 5px solid;
    }
    
    .alert-success {
        background: rgba(34, 197, 94, 0.1);
        border-left-color: #22c55e;
    }
    
    .alert-warning {
        background: rgba(251, 191, 36, 0.1);
        border-left-color: #fbbf24;
    }
    
    .alert-danger {
        background: rgba(239, 68, 68, 0.1);
        border-left-color: #ef4444;
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1e1e2e 0%, #2d2d44 100%);
    }
    
    /* Progress indicators */
    .progress-ring {
        display: inline-block;
        position: relative;
    }
</style>
""", unsafe_allow_html=True)

# Enhanced title with animation
st.markdown("""
    <h1 style='text-align: center; font-size: 3em; margin-bottom: 0;'>
        🚀 Institutional Flow Pro+
    </h1>
    <p style='text-align: center; color: rgba(255,255,255,0.7); font-size: 1.2em; margin-top: 0;'>
        AI-Powered Trading Intelligence Dashboard
    </p>
""", unsafe_allow_html=True)

st.caption("Advanced Analytics · ML Predictions · Smart Alerts · Portfolio Optimization · Real-time Monitoring")

# Full 11-sector GICS ETF proxy map
GICS_SECTOR_ETFS = {
    "Information Technology": "XLK",
    "Health Care": "XLV",
    "Financials": "XLF",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Industrials": "XLI",
    "Energy": "XLE",
    "Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}

THEMATIC_ETFS = {
    "Defense / Aerospace": "ITA",
    "Semiconductors": "SMH",
    "AI / Nasdaq Growth": "QQQ",
    "Cybersecurity": "HACK",
    "Uranium": "URA",
    "Oil Services": "OIH",
    "Gold Miners": "GDX",
    "Infrastructure": "PAVE",
    "Biotech": "XBI",
    "Homebuilders": "XHB",
    "Transportation": "IYT",
    "Banks": "KBE",
    "Regional Banks": "KRE",
}

ROTATION_ETFS = {**GICS_SECTOR_ETFS, **THEMATIC_ETFS}

ETF_DISCOVERY_THEMES = {
    "Hot Themes": {
        "AI": ["QQQ", "BOTZ", "AIQ"],
        "AI Infrastructure": ["VRT", "PAVE", "GRID"],
        "Semiconductors": ["SMH", "SOXX"],
        "Defense": ["ITA", "XAR"],
        "Energy": ["XLE", "XOP", "OIH"],
        "Nuclear": ["NLR"],
        "Uranium": ["URA", "URNM"],
        "Gold": ["GLD", "GDX", "GDXJ"],
        "Bitcoin / Crypto": ["IBIT", "BITB", "BTC-USD"],
        "Cybersecurity": ["HACK", "CIBR"],
        "Robotics & Automation": ["BOTZ", "ROBO"],
        "Space": ["ARKX", "UFO"],
        "Lithium / EV": ["LIT", "DRIV"],
        "Clean Energy": ["ICLN", "QCLN"],
    },
    "Income": {
        "Dividend": ["SCHD", "VYM", "XEI.TO"],
        "REITs": ["VNQ", "XLRE", "ZRE.TO"],
        "Bonds": ["AGG", "BND", "XBB.TO"],
        "Treasuries": ["TLT", "IEF", "SGOV"],
    },
    "Geography": {
        "US Large Cap": ["SPY", "VOO", "IVV"],
        "US Small Cap": ["IWM", "VB"],
        "Europe": ["VGK", "IEUR"],
        "UK": ["EWU"],
        "Japan": ["EWJ"],
        "China": ["FXI", "MCHI"],
        "India": ["INDA"],
        "Emerging Markets": ["EEM", "VWO"],
    },
    "Style": {
        "Quality": ["QUAL", "SPHQ"],
        "Momentum": ["MTUM", "PDP"],
        "Value": ["VLUE", "VTV"],
    },
}

ETF_EXPENSES = {
    "SPY": 0.09, "VOO": 0.03, "IVV": 0.03, "QQQ": 0.20, "SCHD": 0.06, "VYM": 0.06,
    "XLK": 0.09, "XLF": 0.09, "XLE": 0.09, "XLV": 0.09, "XLI": 0.09, "XLP": 0.09,
    "XLY": 0.09, "XLU": 0.09, "XLRE": 0.09, "XLC": 0.09, "SMH": 0.35, "SOXX": 0.35,
    "ITA": 0.40, "XAR": 0.35, "GDX": 0.51, "GDXJ": 0.52, "URA": 0.69, "URNM": 0.75,
    "HACK": 0.60, "CIBR": 0.60, "BOTZ": 0.68, "ROBO": 0.95, "LIT": 0.75, "ICLN": 0.41,
    "XEI.TO": 0.22, "ZRE.TO": 0.61, "XBB.TO": 0.10,
}

ETF_CATALOG = [
    {"Ticker":"SPY", "Name":"SPDR S&P 500 ETF Trust", "Tags":["US Large Cap","S&P 500","Core","Equity","Low Fee"], "Theme":"US Large Cap", "Category":"Geography", "Expense":0.09},
    {"Ticker":"VOO", "Name":"Vanguard S&P 500 ETF", "Tags":["US Large Cap","S&P 500","Core","Equity","Low Fee","Fee Saver"], "Theme":"US Large Cap", "Category":"Geography", "Expense":0.03},
    {"Ticker":"IVV", "Name":"iShares Core S&P 500 ETF", "Tags":["US Large Cap","S&P 500","Core","Equity","Low Fee","Fee Saver"], "Theme":"US Large Cap", "Category":"Geography", "Expense":0.03},
    {"Ticker":"QQQ", "Name":"Invesco QQQ Trust", "Tags":["AI","Growth","Nasdaq","Technology","Mega Cap"], "Theme":"AI / Growth", "Category":"Hot Themes", "Expense":0.20},
    {"Ticker":"QQQM", "Name":"Invesco NASDAQ 100 ETF", "Tags":["AI","Growth","Nasdaq","Technology","Low Fee","Fee Saver"], "Theme":"AI / Growth", "Category":"Hot Themes", "Expense":0.15},
    {"Ticker":"SMH", "Name":"VanEck Semiconductor ETF", "Tags":["Semiconductors","AI Infrastructure","Chips","Technology"], "Theme":"Semiconductors", "Category":"Hot Themes", "Expense":0.35},
    {"Ticker":"SOXX", "Name":"iShares Semiconductor ETF", "Tags":["Semiconductors","AI Infrastructure","Chips","Technology"], "Theme":"Semiconductors", "Category":"Hot Themes", "Expense":0.35},
]

# =========================================================
# ENHANCED SIDEBAR WITH BETTER ORGANIZATION
# =========================================================
with st.sidebar:
    st.markdown("### 🎯 Main Ticker")
    ticker = st.text_input("", "AAPL", key="main_ticker_input", help="Enter stock or ETF symbol").strip().upper()
    
    # Update from session state if set by analyze button
    if 'analyze_ticker' in st.session_state:
        ticker = st.session_state['analyze_ticker']
        del st.session_state['analyze_ticker']
    
    st.markdown("---")
    
    st.markdown("### 📊 Chart Settings")
    period = st.selectbox("Time Period", ["1mo", "3mo", "6mo", "1y", "2y", "5y"], index=3, help="Historical data range")
    interval = st.selectbox("Interval", ["1d", "1wk", "1mo"], index=0, help="Data granularity")
    
    st.markdown("---")
    
    st.markdown("### 🎛️ Technical Indicators")
    show_fibonacci = st.checkbox("Fibonacci Retracements", value=False)
    show_support_resistance = st.checkbox("Support/Resistance Levels", value=True)
    show_volume_profile = st.checkbox("Volume Profile", value=False)
    show_bollinger = st.checkbox("Bollinger Bands", value=True)
    
    st.markdown("---")
    
    st.markdown("### 🤖 AI Features")
    enable_ml_prediction = st.checkbox("ML Price Prediction", value=True, help="Machine learning trend prediction")
    enable_pattern_recognition = st.checkbox("Pattern Recognition", value=True, help="Detect chart patterns")
    enable_sentiment_analysis = st.checkbox("Sentiment Analysis", value=False, help="Social media sentiment (requires API)")
    
    st.markdown("---")
    
    st.markdown("### 📈 Portfolio Tracking")
    enable_portfolio = st.checkbox("Enable Portfolio", value=False)
    if enable_portfolio:
        portfolio_value = st.number_input("Portfolio Value ($)", min_value=0, value=100000, step=10000)
        risk_tolerance = st.select_slider("Risk Tolerance", options=["Conservative", "Moderate", "Aggressive"], value="Moderate")
    
    st.markdown("---")
    
    st.markdown("### 🔔 Alert Settings")
    enable_real_alerts = st.checkbox("Enable Real Alerts", value=False)
    if enable_real_alerts:
        alert_rsi_oversold = st.slider("RSI Oversold Alert", 10, 40, 30)
        alert_rsi_overbought = st.slider("RSI Overbought Alert", 60, 90, 70)
        alert_volume_spike = st.slider("Volume Spike % Alert", 100, 500, 200)
        
        st.markdown("**Notification Channels**")
        discord_webhook = st.text_input("Discord Webhook", type="password")
        telegram_bot_token = st.text_input("Telegram Bot Token", type="password")
        telegram_chat_id = st.text_input("Telegram Chat ID", type="password")
    else:
        discord_webhook = ""
        telegram_bot_token = ""
        telegram_chat_id = ""
        alert_rsi_oversold = 30
        alert_rsi_overbought = 70
        alert_volume_spike = 200
    
    st.markdown("---")
    
    st.markdown("### ⚡ Real-time Features")
    realtime_on = st.checkbox("Auto-refresh", value=False)
    if realtime_on:
        refresh_interval = st.slider("Refresh (sec)", 10, 300, 60, step=10)
    else:
        refresh_interval = 60
    
    st.markdown("---")
    
    st.markdown("---")

    st.markdown("### 🧭 Active Page")
    PAGE_OPTIONS = [
        "📊 Analysis", "🐋 Volume/Whales", "🗺️ Sector Map", "💎 Discovery", "🎯 Watchlist",
        "📰 News", "💼 Portfolio", "🥇 Metals", "🤖 ML Lab", "🔔 Alerts", "⚙️ Settings"
    ]
    active_tab = st.radio(
        "Choose one page to load",
        PAGE_OPTIONS,
        index=0,
        key="active_lazy_page",
        help="This replaces Streamlit tabs so inactive pages do not fetch data."
    )

    st.markdown("---")

    st.markdown("### 💾 Export Options")
    export_format = st.selectbox("Export Format", ["PDF Report", "CSV Data", "JSON"])
    if st.button("📥 Export Dashboard"):
        st.info("Export feature: Click to download comprehensive report")

# =========================================================
# HELPER FUNCTIONS (KEEPING ORIGINAL LOGIC)
# =========================================================

def parse_tickers(text):
    """Parse comma/space-separated ticker list."""
    if not text:
        return []
    text = text.replace(",", " ").replace("\n", " ").upper()
    raw = re.split(r"\s+", text.strip())
    return [t for t in raw if t]

@st.cache_data(ttl=300, show_spinner=False)
def fetch_data(ticker, period, interval):
    """Fetch OHLCV + metrics from yfinance with enhanced error handling."""
    if not YF_AVAILABLE:
        return pd.DataFrame(), {}
    try:
        yf_ticker = yf.Ticker(ticker)
        df = yf_ticker.history(period=period, interval=interval, auto_adjust=True)
        if df.empty:
            return pd.DataFrame(), {}
        
        # Calculate additional metrics
        df['Returns'] = df['Close'].pct_change()
        df['Log_Returns'] = np.log(df['Close'] / df['Close'].shift(1))
        df['Cumulative_Returns'] = (1 + df['Returns']).cumprod()
        
        info = yf_ticker.info
        return df, info
    except Exception as e:
        st.error(f"Error fetching {ticker}: {e}")
        return pd.DataFrame(), {}

def calculate_vwap(df):
    """Enhanced VWAP calculation."""
    if df.empty or 'Close' not in df.columns:
        return df
    df = df.copy()
    df['Typical'] = (df['High'] + df['Low'] + df['Close']) / 3
    df['TPV'] = df['Typical'] * df['Volume']
    df['VWAP'] = df['TPV'].cumsum() / df['Volume'].cumsum()
    
    # VWAP bands (standard deviation)
    df['VWAP_Upper'] = df['VWAP'] * 1.02
    df['VWAP_Lower'] = df['VWAP'] * 0.98
    
    return df

def calculate_rsi(series, period=14):
    """RSI calculation."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(series, fast=12, slow=26, signal=9):
    """MACD calculation."""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calculate_obv(df):
    """On-Balance Volume calculation."""
    if df.empty:
        return pd.Series(dtype=float)
    obv = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()
    return obv

def calculate_bollinger_bands(series, window=20, num_std=2):
    """Bollinger Bands calculation."""
    sma = series.rolling(window=window).mean()
    std = series.rolling(window=window).std()
    upper = sma + (std * num_std)
    lower = sma - (std * num_std)
    return upper, sma, lower

def calculate_fibonacci_levels(df):
    """Calculate Fibonacci retracement levels."""
    if df.empty:
        return {}
    
    high = df['High'].max()
    low = df['Low'].min()
    diff = high - low
    
    levels = {
        '0.0%': high,
        '23.6%': high - 0.236 * diff,
        '38.2%': high - 0.382 * diff,
        '50.0%': high - 0.500 * diff,
        '61.8%': high - 0.618 * diff,
        '100.0%': low
    }
    return levels

def find_support_resistance(df, window=20):
    """Find support and resistance levels using local extrema."""
    if df.empty or len(df) < window * 2:
        return [], []
    
    highs = df['High'].rolling(window=window, center=True).max()
    lows = df['Low'].rolling(window=window, center=True).min()
    
    resistance = df[df['High'] == highs]['High'].unique()
    support = df[df['Low'] == lows]['Low'].unique()
    
    # Filter to most significant levels
    resistance = sorted(resistance[-5:], reverse=True)
    support = sorted(support[-5:])
    
    return support, resistance

def detect_candlestick_patterns(df):
    """Detect common candlestick patterns."""
    if df.empty or len(df) < 3:
        return []
    
    patterns = []
    df = df.tail(20).copy()
    
    for i in range(2, len(df)):
        open_price = df['Open'].iloc[i]
        close_price = df['Close'].iloc[i]
        high = df['High'].iloc[i]
        low = df['Low'].iloc[i]
        
        body = abs(close_price - open_price)
        range_total = high - low
        
        # Doji
        if range_total > 0 and body / range_total < 0.1:
            patterns.append({'index': i, 'pattern': 'Doji', 'signal': 'Neutral'})
        
        # Hammer
        if close_price > open_price:
            upper_shadow = high - close_price
            lower_shadow = open_price - low
            if lower_shadow > 2 * body and upper_shadow < body:
                patterns.append({'index': i, 'pattern': 'Hammer', 'signal': 'Bullish'})
        
        # Shooting Star
        if close_price < open_price:
            upper_shadow = high - open_price
            lower_shadow = close_price - low
            if upper_shadow > 2 * body and lower_shadow < body:
                patterns.append({'index': i, 'pattern': 'Shooting Star', 'signal': 'Bearish'})
    
    return patterns

def ml_price_prediction(df):
    """Machine learning-based price prediction."""
    if not ML_AVAILABLE or df.empty or len(df) < 30:
        return None, None, None
    
    try:
        # Feature engineering
        df = df.copy()
        df['SMA_5'] = df['Close'].rolling(5).mean()
        df['SMA_20'] = df['Close'].rolling(20).mean()
        df['RSI'] = calculate_rsi(df['Close'])
        df['Volume_SMA'] = df['Volume'].rolling(10).mean()
        df['Price_Change'] = df['Close'].pct_change()
        
        # Create target (1 if price goes up next day, 0 otherwise)
        df['Target'] = (df['Close'].shift(-1) > df['Close']).astype(int)
        
        # Prepare features
        features = ['SMA_5', 'SMA_20', 'RSI', 'Volume_SMA', 'Price_Change']
        df_ml = df[features + ['Target']].dropna()
        
        if len(df_ml) < 20:
            return None, None, None
        
        X = df_ml[features].values[:-1]
        y = df_ml['Target'].values[:-1]
        
        # Train model
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
        model.fit(X_scaled, y)
        
        # Predict next move
        last_features = df_ml[features].values[-1].reshape(1, -1)
        last_scaled = scaler.transform(last_features)
        prediction = model.predict(last_scaled)[0]
        probability = model.predict_proba(last_scaled)[0]
        
        # Feature importance
        importance = dict(zip(features, model.feature_importances_))
        
        return prediction, probability, importance
    except Exception as e:
        return None, None, None

def calculate_advanced_metrics(df, info):
    """Calculate advanced portfolio metrics."""
    if df.empty:
        return {}
    
    returns = df['Returns'].dropna()
    
    metrics = {}
    
    # Sharpe Ratio (assuming 4% risk-free rate)
    if len(returns) > 0 and returns.std() != 0:
        risk_free_rate = 0.04 / 252  # Daily
        excess_returns = returns - risk_free_rate
        metrics['sharpe_ratio'] = np.sqrt(252) * excess_returns.mean() / returns.std()
    else:
        metrics['sharpe_ratio'] = 0
    
    # Max Drawdown
    cumulative = df['Cumulative_Returns']
    running_max = cumulative.expanding().max()
    drawdown = (cumulative - running_max) / running_max
    metrics['max_drawdown'] = drawdown.min() * 100
    
    # Volatility (annualized)
    metrics['volatility'] = returns.std() * np.sqrt(252) * 100
    
    # Beta (compared to SPY)
    try:
        spy_data = yf.download('SPY', period='1y', interval='1d', progress=False)
        if not spy_data.empty:
            spy_returns = spy_data['Close'].pct_change().dropna()
            aligned_returns = returns.align(spy_returns, join='inner')
            if len(aligned_returns[0]) > 20:
                covariance = np.cov(aligned_returns[0], aligned_returns[1])[0][1]
                spy_variance = np.var(aligned_returns[1])
                metrics['beta'] = covariance / spy_variance if spy_variance != 0 else 1.0
            else:
                metrics['beta'] = 1.0
        else:
            metrics['beta'] = 1.0
    except:
        metrics['beta'] = 1.0
    
    return metrics

def create_enhanced_chart(df, ticker, show_fibonacci, show_support_resistance, show_bollinger):
    """Create enhanced candlestick chart with multiple indicators."""
    if df.empty:
        return None
    
    # Create subplots
    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.5, 0.15, 0.15, 0.2],
        subplot_titles=(f'{ticker} Price Action', 'RSI', 'MACD', 'Volume')
    )
    
    # Candlestick chart
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df['Open'],
            high=df['High'],
            low=df['Low'],
            close=df['Close'],
            name='Price',
            increasing_line_color='#26a69a',
            decreasing_line_color='#ef5350'
        ),
        row=1, col=1
    )
    
    # VWAP
    if 'VWAP' in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df['VWAP'],
                mode='lines',
                name='VWAP',
                line=dict(color='#FFA726', width=2, dash='dot')
            ),
            row=1, col=1
        )
    
    # Bollinger Bands
    if show_bollinger and len(df) > 20:
        bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(df['Close'])
        fig.add_trace(
            go.Scatter(x=df.index, y=bb_upper, mode='lines', name='BB Upper',
                      line=dict(color='rgba(128,128,128,0.3)', width=1)),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(x=df.index, y=bb_middle, mode='lines', name='BB Middle',
                      line=dict(color='rgba(128,128,128,0.5)', width=1, dash='dash')),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(x=df.index, y=bb_lower, mode='lines', name='BB Lower',
                      line=dict(color='rgba(128,128,128,0.3)', width=1),
                      fill='tonexty', fillcolor='rgba(128,128,128,0.1)'),
            row=1, col=1
        )
    
    # Fibonacci levels
    if show_fibonacci:
        fib_levels = calculate_fibonacci_levels(df)
        for level_name, level_value in fib_levels.items():
            fig.add_hline(
                y=level_value, line_dash="dash", line_color="rgba(255,255,255,0.3)",
                annotation_text=level_name, annotation_position="right",
                row=1, col=1
            )
    
    # Support and Resistance
    if show_support_resistance:
        support, resistance = find_support_resistance(df)
        for s in support:
            fig.add_hline(y=s, line_dash="dot", line_color="rgba(34,197,94,0.5)", row=1, col=1)
        for r in resistance:
            fig.add_hline(y=r, line_dash="dot", line_color="rgba(239,68,68,0.5)", row=1, col=1)
    
    # RSI
    rsi = calculate_rsi(df['Close'])
    fig.add_trace(
        go.Scatter(x=df.index, y=rsi, mode='lines', name='RSI',
                  line=dict(color='#AB47BC', width=2)),
        row=2, col=1
    )
    fig.add_hline(y=70, line_dash="dash", line_color="rgba(239,68,68,0.5)", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="rgba(34,197,94,0.5)", row=2, col=1)
    
    # MACD
    macd_line, signal_line, histogram = calculate_macd(df['Close'])
    fig.add_trace(
        go.Scatter(x=df.index, y=macd_line, mode='lines', name='MACD',
                  line=dict(color='#42A5F5', width=2)),
        row=3, col=1
    )
    fig.add_trace(
        go.Scatter(x=df.index, y=signal_line, mode='lines', name='Signal',
                  line=dict(color='#FF7043', width=2)),
        row=3, col=1
    )
    colors = ['#26a69a' if h >= 0 else '#ef5350' for h in histogram]
    fig.add_trace(
        go.Bar(x=df.index, y=histogram, name='Histogram', marker_color=colors),
        row=3, col=1
    )
    
    # Volume
    volume_colors = ['#26a69a' if df['Close'].iloc[i] >= df['Open'].iloc[i] else '#ef5350' 
                     for i in range(len(df))]
    fig.add_trace(
        go.Bar(x=df.index, y=df['Volume'], name='Volume', marker_color=volume_colors),
        row=4, col=1
    )
    
    # Layout
    fig.update_layout(
        height=1000,
        showlegend=True,
        xaxis_rangeslider_visible=False,
        template='plotly_dark',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0.3)',
        font=dict(color='white'),
        hovermode='x unified'
    )
    
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(255,255,255,0.1)')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(255,255,255,0.1)')
    
    return fig

def calculate_goat_score(df, info):
    """Calculate GOAT quality score with enhanced metrics."""
    if df.empty:
        return 0, {}
    
    score = 0
    reasons = []
    
    # Price momentum (0-25 points)
    if len(df) >= 20:
        sma_20 = df['Close'].rolling(20).mean().iloc[-1]
        current_price = df['Close'].iloc[-1]
        if current_price > sma_20:
            momentum_score = min(25, ((current_price / sma_20 - 1) * 100))
            score += momentum_score
            reasons.append(f"Strong momentum: +{momentum_score:.1f} pts")
    
    # Volume trend (0-20 points)
    if 'Volume' in df.columns and len(df) >= 10:
        recent_vol = df['Volume'].tail(5).mean()
        avg_vol = df['Volume'].mean()
        if recent_vol > avg_vol:
            vol_score = min(20, ((recent_vol / avg_vol - 1) * 50))
            score += vol_score
            reasons.append(f"Volume increase: +{vol_score:.1f} pts")
    
    # RSI positioning (0-15 points)
    rsi = calculate_rsi(df['Close']).iloc[-1]
    if 40 <= rsi <= 60:
        score += 15
        reasons.append("Healthy RSI: +15 pts")
    elif 30 <= rsi < 40 or 60 < rsi <= 70:
        score += 10
        reasons.append("Moderate RSI: +10 pts")
    
    # Volatility (0-10 points)
    volatility = df['Close'].pct_change().std()
    if volatility < 0.03:
        score += 10
        reasons.append("Low volatility: +10 pts")
    elif volatility < 0.05:
        score += 5
        reasons.append("Moderate volatility: +5 pts")
    
    # Fundamental score (0-30 points)
    if info:
        fundamental_score = 0
        if info.get('profitMargins', 0) > 0.15:
            fundamental_score += 10
            reasons.append("High profit margin: +10 pts")
        if info.get('revenueGrowth', 0) > 0.10:
            fundamental_score += 10
            reasons.append("Revenue growth: +10 pts")
        if info.get('debtToEquity', 100) < 50:
            fundamental_score += 10
            reasons.append("Low debt: +10 pts")
        score += fundamental_score
    
    return min(100, score), reasons

@st.cache_data(ttl=3600)
def fetch_news_articles(ticker, max_age_days=3):
    """Fetch news articles with enhanced parsing."""
    if not FEEDPARSER_AVAILABLE:
        return []
    
    articles = []
    feeds = [
        f"https://finance.yahoo.com/rss/headline?s={ticker}",
        f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}",
    ]
    
    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:20]:
                pub_date = entry.get('published_parsed')
                if pub_date:
                    pub_dt = datetime(*pub_date[:6])
                    age_hrs = (datetime.now() - pub_dt).total_seconds() / 3600
                    if age_hrs <= max_age_days * 24:
                        # Enhanced sentiment analysis
                        title = entry.get('title', '').lower()
                        sentiment = 0
                        if any(word in title for word in ['surges', 'jumps', 'soars', 'rallies', 'gains']):
                            sentiment = 1
                        elif any(word in title for word in ['plunges', 'drops', 'falls', 'crashes', 'tumbles']):
                            sentiment = -1
                        
                        articles.append({
                            'title': entry.get('title', ''),
                            'url': entry.get('link', ''),
                            'source': 'Yahoo Finance',
                            'age_hrs': age_hrs,
                            'sentiment': sentiment,
                            'is_press': 'press release' in title or 'announces' in title,
                            'is_high_impact': any(word in title for word in ['earnings', 'acquisition', 'merger', 'fda', 'approval'])
                        })
        except:
            continue
    

    return articles

# =========================================================
# V3 UPGRADES: ML IMPACT, WHALE/VOLUME, SECTOR MAP, PORTFOLIO, METALS
# =========================================================

def add_whale_flow_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    """Add whale tiers, buy/sell pressure, dark-pool proxy and flow scores."""
    if frame is None or frame.empty:
        return pd.DataFrame()
    out = frame.copy()
    out['Vol_Avg'] = out['Volume'].rolling(20).mean()
    out['Vol_Std'] = out['Volume'].rolling(20).std().replace(0, np.nan)
    out['Vol_Z'] = ((out['Volume'] - out['Vol_Avg']) / out['Vol_Std']).replace([np.inf, -np.inf], np.nan).fillna(0)
    out['Whale_Tier'] = pd.cut(out['Vol_Z'], bins=[-np.inf, 1, 2, 3, np.inf], labels=[0, 1, 2, 3]).astype(int)
    out['Range'] = (out['High'] - out['Low']).replace(0, np.nan)
    out['Body'] = (out['Close'] - out['Open']).abs()
    out['Body_Ratio'] = (out['Body'] / out['Range']).fillna(0)
    out['Buy_Pct'] = ((out['Close'] - out['Low']) / (out['Range'] + 1e-9)).clip(0, 1).fillna(0.5)
    out['Buy_Vol'] = out['Volume'] * out['Buy_Pct']
    out['Sell_Vol'] = out['Volume'] * (1 - out['Buy_Pct'])
    out['OBV_Slope'] = out.get('OBV', calculate_obv(out)).diff().fillna(0)
    if 'VWAP' not in out.columns:
        out = calculate_vwap(out)
    out['VWAP_Diff'] = ((out['Close'] - out['VWAP']).abs() / out['VWAP'].replace(0, np.nan)).fillna(0)
    out['DarkPool_Accum'] = (out['Vol_Z'] > 1.8) & (out['Body_Ratio'] < 0.35) & (out['VWAP_Diff'] < 0.01) & (out['OBV_Slope'] > 0)
    out['DarkPool_Dist'] = (out['Vol_Z'] > 1.8) & (out['Body_Ratio'] < 0.35) & (out['VWAP_Diff'] < 0.01) & (out['OBV_Slope'] < 0)
    out['Whale_Cluster'] = (out['Whale_Tier'] >= 2).rolling(5).sum().fillna(0)
    out['Whale_Score'] = (
        (out['Vol_Z'].clip(0, 3) / 3 * 35) +
        ((1 - out['Body_Ratio'].clip(0, 1)) * 20) +
        ((1 - out['VWAP_Diff'].clip(0, 0.02) / 0.02) * 20) +
        np.where(out['OBV_Slope'] > 0, 15, 0) +
        np.where(out['Close'] > out['VWAP'], 10, 0)
    ).clip(0, 100).fillna(0)
    return out

def compute_buy_sell_score(frame: pd.DataFrame, ml_prediction=None, ml_probability=None, use_ml=True) -> dict:
    """Transparent score. ML toggle now actually changes final composite score."""
    if frame is None or frame.empty:
        return {'buy': 0, 'sell': 0, 'gap': 0, 'signal': 'No data', 'reasons_buy': [], 'reasons_sell': [], 'ml_adjustment': 0}
    row = frame.iloc[-1]
    buy = sell = 0
    rb, rs = [], []
    if row['Close'] > row.get('VWAP', row['Close']):
        buy += 20; rb.append('Price above VWAP')
    else:
        sell += 20; rs.append('Price below VWAP')
    if row.get('OBV_Slope', 0) > 0:
        buy += 20; rb.append('OBV rising')
    else:
        sell += 20; rs.append('OBV falling')
    if row.get('MACD', 0) > row.get('MACD_Signal', 0):
        buy += 15; rb.append('MACD bullish')
    else:
        sell += 15; rs.append('MACD bearish')
    rsi = row.get('RSI', 50)
    if 40 <= rsi <= 65:
        buy += 10; rb.append('RSI healthy')
    elif rsi > 70:
        sell += 15; rs.append('RSI overbought')
    elif rsi < 35:
        buy += 15; rb.append('RSI oversold bounce zone')
    if row.get('Whale_Tier', 0) >= 2:
        if row.get('Buy_Pct', 0.5) >= 0.55:
            buy += 15; rb.append('Whale buying pressure')
        elif row.get('Buy_Pct', 0.5) <= 0.45:
            sell += 15; rs.append('Whale selling pressure')
    if row.get('DarkPool_Accum', False):
        buy += 15; rb.append('Dark-pool accumulation proxy')
    if row.get('DarkPool_Dist', False):
        sell += 15; rs.append('Dark-pool distribution proxy')
    ml_adjustment = 0
    if use_ml and ml_prediction is not None and ml_probability is not None:
        try:
            confidence = float(ml_probability[int(ml_prediction)])
            pts = int(round(max(0, confidence - 0.50) * 40))  # max +20 points at 100% confidence
            if int(ml_prediction) == 1:
                buy += pts; rb.append(f'ML bullish adjustment +{pts}')
                ml_adjustment = pts
            else:
                sell += pts; rs.append(f'ML bearish adjustment +{pts}')
                ml_adjustment = -pts
        except Exception:
            pass
    buy, sell = min(100, int(buy)), min(100, int(sell))
    gap = abs(buy - sell)
    if buy >= 70 and buy > sell:
        signal = '🟢 BUY / ACCUMULATION'
    elif sell >= 70 and sell > buy:
        signal = '🔴 SELL / DISTRIBUTION'
    elif gap < 15:
        signal = '⚪ NO EDGE'
    else:
        signal = '🟡 WATCH'
    return {'buy': buy, 'sell': sell, 'gap': gap, 'signal': signal, 'reasons_buy': rb, 'reasons_sell': rs, 'ml_adjustment': ml_adjustment}

@st.cache_data(ttl=900, show_spinner=False)
def scan_rotation_map(period='3mo', interval='1d'):
    """Restore sector map: GICS + themes with rotation score, RSI, flow and relative strength."""
    rows = []
    spy_df, _ = fetch_data('SPY', period, interval)
    spy_ret = 0
    if not spy_df.empty and len(spy_df) > 5:
        spy_ret = (spy_df['Close'].iloc[-1] / spy_df['Close'].iloc[0] - 1) * 100
    for name, etf in ROTATION_ETFS.items():
        try:
            sec_df, _ = fetch_data(etf, period, interval)
            if sec_df.empty or len(sec_df) < 25:
                continue
            sec_df = calculate_vwap(sec_df)
            sec_df['RSI'] = calculate_rsi(sec_df['Close'])
            sec_df['OBV'] = calculate_obv(sec_df)
            macd, sig, hist = calculate_macd(sec_df['Close'])
            sec_df['MACD'] = macd; sec_df['MACD_Signal'] = sig
            sec_df = add_whale_flow_metrics(sec_df)
            last = sec_df.iloc[-1]
            perf = (sec_df['Close'].iloc[-1] / sec_df['Close'].iloc[0] - 1) * 100
            rel = perf - spy_ret
            flow = 0
            flow += 25 if last['Close'] > last['VWAP'] else -25
            flow += 20 if last['OBV_Slope'] > 0 else -20
            flow += 15 if last['MACD'] > last['MACD_Signal'] else -15
            flow += min(20, last['Whale_Cluster'] * 8)
            flow += 10 if rel > 0 else -10
            rotation = int(np.clip(50 + flow / 2, 0, 100))
            if last['RSI'] < 35 and last['OBV_Slope'] > 0 and last['Close'] >= last['VWAP']:
                state = '🟢 Oversold accumulation'
            elif last['RSI'] < 35:
                state = '🔴 Oversold weakness'
            elif last['RSI'] > 70 and last['OBV_Slope'] < 0:
                state = '🔴 Overbought distribution'
            elif last['RSI'] > 70 and last['Close'] > last['VWAP']:
                state = '🟢 Overbought momentum'
            elif rotation >= 65:
                state = '🟢 Inflow leader'
            elif rotation <= 35:
                state = '🔴 Outflow leader'
            else:
                state = '🟡 Neutral / watch'
            rows.append({
                'Group': 'GICS Sector' if name in GICS_SECTOR_ETFS else 'Theme',
                'Name': name,
                'Ticker': etf,
                'Rotation Score': rotation,
                'Return %': round(perf, 2),
                'Rel vs SPY %': round(rel, 2),
                'RSI': round(float(last['RSI']), 1),
                'Whale Cluster': int(last.get('Whale_Cluster', 0)),
                'VWAP': 'Above' if last['Close'] > last['VWAP'] else 'Below',
                'Signal': state
            })
        except Exception:
            continue
    return pd.DataFrame(rows).sort_values('Rotation Score', ascending=False) if rows else pd.DataFrame()

def build_volume_profile(frame: pd.DataFrame, bins=40):
    if frame is None or frame.empty:
        return go.Figure()
    price_bins = np.linspace(frame['Low'].min(), frame['High'].max(), bins)
    vol_profile = np.zeros(bins - 1)
    for _, row in frame.iterrows():
        mask = (price_bins[:-1] <= row['High']) & (price_bins[1:] >= row['Low'])
        count = int(mask.sum())
        if count > 0:
            vol_profile[mask] += row['Volume'] / count
    mids = (price_bins[:-1] + price_bins[1:]) / 2
    fig = go.Figure(go.Bar(x=vol_profile, y=mids, orientation='h', name='Volume Profile'))
    fig.update_layout(template='plotly_dark', height=420, title='Volume Profile: Price-at-Volume', xaxis_title='Volume', yaxis_title='Price')
    return fig

def build_metal_meter(symbol='GC=F', name='Gold'):
    mdf, _ = fetch_data(symbol, '6mo', '1d')
    if mdf.empty or len(mdf) < 30:
        return None
    mdf = calculate_vwap(mdf)
    mdf['RSI'] = calculate_rsi(mdf['Close'])
    mdf['OBV'] = calculate_obv(mdf)
    macd, sig, _ = calculate_macd(mdf['Close'])
    mdf['MACD'] = macd; mdf['MACD_Signal'] = sig
    mdf = add_whale_flow_metrics(mdf)
    score = compute_buy_sell_score(mdf, use_ml=False)
    last = mdf.iloc[-1]
    return {
        'Metal': name,
        'Symbol': symbol,
        'Price': float(last['Close']),
        'Smart Money Meter': score['buy'],
        'Sell Pressure': score['sell'],
        'RSI': float(last['RSI']),
        'Whale Score': float(last['Whale_Score']),
        'Paper Leverage Proxy': round(max(1, float(last['Vol_Z']) + 4), 1),
        'Delivery Coverage Proxy': round(max(1, 25 - float(last['Vol_Z']) * 3), 1),
        'Signal': score['signal']
    }

# =========================================================
# MAIN DASHBOARD — LAZY LOADED
# =========================================================
MAIN_DATA_PAGES = {"📊 Analysis", "🐋 Volume/Whales", "🤖 ML Lab", "🔔 Alerts"}

if active_tab in MAIN_DATA_PAGES:
    # =========================================================
    # MAIN DASHBOARD
    # =========================================================

    # Fetch data
    with st.spinner(f"🔄 Loading data for {ticker}..."):
        df, info = fetch_data(ticker, period, interval)

    if df.empty:
        st.error(f"❌ Unable to fetch data for {ticker}. Please check the symbol and try again.")
        st.stop()

    # Calculate indicators
    df = calculate_vwap(df)
    df['RSI'] = calculate_rsi(df['Close'])
    df['OBV'] = calculate_obv(df)
    macd_line, signal_line, histogram = calculate_macd(df['Close'])
    df['MACD'] = macd_line
    df['MACD_Signal'] = signal_line
    df['MACD_Hist'] = histogram

    # V3: whale/flow metrics used by score, volume analysis, alerts, and sector confirmation
    df = add_whale_flow_metrics(df)

    # Calculate scores
    goat_score, goat_reasons = calculate_goat_score(df, info)
    advanced_metrics = calculate_advanced_metrics(df, info)

    # ML Prediction
    ml_prediction = None
    ml_probability = None
    ml_importance = None
    if enable_ml_prediction:
        ml_prediction, ml_probability, ml_importance = ml_price_prediction(df)

    # V3: ML now actively changes the combined signal when enabled
    combined_score = compute_buy_sell_score(df, ml_prediction, ml_probability, use_ml=enable_ml_prediction)

    # Pattern Detection
    patterns_detected = []
    if enable_pattern_recognition:
        patterns_detected = detect_candlestick_patterns(df)

    # =========================================================
    # KEY METRICS DASHBOARD
    # =========================================================

    st.markdown("## 📊 Key Metrics Overview")

    col1, col2, col3, col4, col5 = st.columns(5)

    current_price = df['Close'].iloc[-1]
    price_change = df['Close'].iloc[-1] - df['Close'].iloc[-2]
    price_change_pct = (price_change / df['Close'].iloc[-2]) * 100

    with col1:
        st.markdown(f"""
            <div class="metric-card">
                <h4 style='margin:0; color: rgba(255,255,255,0.7);'>Current Price</h4>
                <h2 style='margin:5px 0; color: #4CAF50;'>${current_price:.2f}</h2>
                <p style='margin:0; color: {'#22c55e' if price_change >= 0 else '#ef4444'};'>
                    {'+' if price_change >= 0 else ''}{price_change_pct:.2f}%
                </p>
            </div>
        """, unsafe_allow_html=True)

    with col2:
        rsi_current = df['RSI'].iloc[-1]
        rsi_color = '#22c55e' if rsi_current < 30 else '#ef4444' if rsi_current > 70 else '#fbbf24'
        st.markdown(f"""
            <div class="metric-card">
                <h4 style='margin:0; color: rgba(255,255,255,0.7);'>RSI (14)</h4>
                <h2 style='margin:5px 0; color: {rsi_color};'>{rsi_current:.1f}</h2>
                <p style='margin:0; color: rgba(255,255,255,0.5);'>
                    {'Oversold' if rsi_current < 30 else 'Overbought' if rsi_current > 70 else 'Neutral'}
                </p>
            </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
            <div class="metric-card">
                <h4 style='margin:0; color: rgba(255,255,255,0.7);'>GOAT Score</h4>
                <h2 style='margin:5px 0; color: #AB47BC;'>{goat_score:.0f}/100</h2>
                <p style='margin:0; color: rgba(255,255,255,0.5);'>
                    {'Excellent' if goat_score >= 80 else 'Good' if goat_score >= 60 else 'Average' if goat_score >= 40 else 'Poor'}
                </p>
            </div>
        """, unsafe_allow_html=True)

    with col4:
        volume_avg = df['Volume'].tail(20).mean()
        volume_current = df['Volume'].iloc[-1]
        volume_ratio = (volume_current / volume_avg) * 100
        st.markdown(f"""
            <div class="metric-card">
                <h4 style='margin:0; color: rgba(255,255,255,0.7);'>Volume</h4>
                <h2 style='margin:5px 0; color: #42A5F5;'>{volume_current/1e6:.1f}M</h2>
                <p style='margin:0; color: rgba(255,255,255,0.5);'>
                    {volume_ratio:.0f}% of avg
                </p>
            </div>
        """, unsafe_allow_html=True)

    with col5:
        sharpe = advanced_metrics.get('sharpe_ratio', 0)
        sharpe_color = '#22c55e' if sharpe > 1 else '#fbbf24' if sharpe > 0 else '#ef4444'
        st.markdown(f"""
            <div class="metric-card">
                <h4 style='margin:0; color: rgba(255,255,255,0.7);'>Sharpe Ratio</h4>
                <h2 style='margin:5px 0; color: {sharpe_color};'>{sharpe:.2f}</h2>
                <p style='margin:0; color: rgba(255,255,255,0.5);'>
                    {'Excellent' if sharpe > 2 else 'Good' if sharpe > 1 else 'Fair' if sharpe > 0 else 'Poor'}
                </p>
            </div>
        """, unsafe_allow_html=True)

    # V3 Composite Signal Display
    st.markdown("---")
    st.markdown("### 🧭 Composite Signal — Technical + Flow" + (" + ML" if enable_ml_prediction else ""))
    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("Signal", combined_score['signal'])
    sc2.metric("Buy Score", f"{combined_score['buy']}/100")
    sc3.metric("Sell Score", f"{combined_score['sell']}/100")
    sc4.metric("Confidence Gap", combined_score['gap'], help="Absolute difference between buy and sell score. Higher = clearer edge.")
    if enable_ml_prediction:
        st.caption(f"ML adjustment applied to composite score: {combined_score['ml_adjustment']:+d} points")
    else:
        st.caption("ML Prediction is OFF: the composite score uses only price, VWAP, OBV, MACD, RSI, and whale-flow data.")

    # ML Prediction Display
    if enable_ml_prediction and ml_prediction is not None:
        st.markdown("---")
        st.markdown("### 🤖 AI Prediction")
    
        col1, col2, col3 = st.columns(3)
    
        with col1:
            prediction_text = "📈 BULLISH" if ml_prediction == 1 else "📉 BEARISH"
            prediction_color = "#22c55e" if ml_prediction == 1 else "#ef4444"
            confidence = ml_probability[ml_prediction] * 100
            st.markdown(f"""
                <div class="alert-box alert-{'success' if ml_prediction == 1 else 'danger'}">
                    <h3 style='margin:0; color: {prediction_color};'>{prediction_text}</h3>
                    <p style='margin:5px 0;'>Confidence: {confidence:.1f}%</p>
                </div>
            """, unsafe_allow_html=True)
    
        with col2:
            if ml_importance:
                st.markdown("**Feature Importance**")
                importance_df = pd.DataFrame(list(ml_importance.items()), columns=['Feature', 'Importance'])
                importance_df = importance_df.sort_values('Importance', ascending=False)
                for _, row in importance_df.iterrows():
                    st.markdown(f"• {row['Feature']}: {row['Importance']:.3f}")
    
        with col3:
            st.markdown("**Trading Signal**")
            if ml_prediction == 1 and confidence > 60:
                st.success("✅ Strong buy signal")
            elif ml_prediction == 0 and confidence > 60:
                st.error("⚠️ Strong sell signal")
            else:
                st.warning("⚡ Weak signal - use caution")

    # Pattern Recognition Display
    if enable_pattern_recognition and patterns_detected:
        st.markdown("### 🔍 Detected Patterns")
        pattern_cols = st.columns(len(patterns_detected))
        for idx, pattern in enumerate(patterns_detected[-3:]):  # Show last 3 patterns
            with pattern_cols[idx]:
                signal_color = '#22c55e' if pattern['signal'] == 'Bullish' else '#ef4444' if pattern['signal'] == 'Bearish' else '#fbbf24'
                st.markdown(f"""
                    <div class="metric-card">
                        <h4 style='color: {signal_color};'>{pattern['pattern']}</h4>
                        <p style='margin:0;'>{pattern['signal']}</p>
                    </div>
                """, unsafe_allow_html=True)

    st.markdown("---")

    # =========================================================
    # ENHANCED CHART
    # =========================================================

    st.markdown("## 📈 Advanced Price Chart")
    chart = create_enhanced_chart(df, ticker, show_fibonacci, show_support_resistance, show_bollinger)
    if chart:
        st.plotly_chart(chart, use_container_width=True)

else:
    st.info(f"Main ticker data for {ticker} is not loaded on this page. Switch to Analysis, Volume/Whales, ML Lab, or Alerts to load it.")
    df = pd.DataFrame()
    info = {}
    goat_score = 0
    goat_reasons = []
    advanced_metrics = {}
    ml_prediction = None
    ml_probability = None
    ml_importance = None
    combined_score = {"signal": "Not loaded", "buy": 0, "sell": 0, "gap": 0, "reasons_buy": [], "reasons_sell": [], "ml_adjustment": 0}
    patterns_detected = []
    rsi_current = 50
    volume_ratio = 0

# =========================================================
# RESTORED + UPGRADED TABS
# =========================================================

st.caption(f"Lazy-load mode: only **{active_tab}** runs its data fetches.")

if active_tab == "📊 Analysis":
    st.markdown("### 📊 Technical Analysis Summary")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### GOAT Quality Breakdown")
        st.markdown(f"**Overall Score: {goat_score:.0f}/100**")
        for reason in goat_reasons:
            st.markdown(f"• {reason}")
        st.markdown("---")
        st.markdown("#### Composite Reasons")
        st.markdown("**Bullish factors**")
        st.write(combined_score['reasons_buy'] if combined_score['reasons_buy'] else "None")
        st.markdown("**Bearish factors**")
        st.write(combined_score['reasons_sell'] if combined_score['reasons_sell'] else "None")
    with col2:
        st.markdown("#### Advanced Metrics")
        st.markdown(f"• **Sharpe Ratio:** {advanced_metrics.get('sharpe_ratio', 0):.2f}")
        st.markdown(f"• **Max Drawdown:** {advanced_metrics.get('max_drawdown', 0):.2f}%")
        st.markdown(f"• **Volatility:** {advanced_metrics.get('volatility', 0):.2f}%")
        st.markdown(f"• **Beta:** {advanced_metrics.get('beta', 1.0):.2f}")
        st.markdown("---")
        st.markdown("#### Key Levels")
        support, resistance = find_support_resistance(df)
        st.markdown("**Support:** " + (", ".join([f"${s:.2f}" for s in support[:4]]) if support else "—"))
        st.markdown("**Resistance:** " + (", ".join([f"${r:.2f}" for r in resistance[:4]]) if resistance else "—"))

elif active_tab == "🐋 Volume/Whales":
    st.markdown("### 🐋 Volume Analysis — restored")
    v1, v2, v3, v4 = st.columns(4)
    latest = df.iloc[-1]
    v1.metric("Whale Score", f"{latest.get('Whale_Score', 0):.0f}/100")
    v2.metric("Whale Tier", int(latest.get('Whale_Tier', 0)))
    v3.metric("5-Bar Cluster", f"{int(latest.get('Whale_Cluster', 0))}/5")
    v4.metric("Last Bar Buy Pressure", f"{latest.get('Buy_Pct', 0.5)*100:.0f}%")
    col1, col2 = st.columns(2)
    with col1:
        fig_score = go.Figure()
        fig_score.add_trace(go.Scatter(x=df.index, y=df['Whale_Score'], fill='tozeroy', name='Whale Composite Score'))
        fig_score.add_hline(y=60, line_dash='dash', annotation_text='High')
        fig_score.add_hline(y=80, line_dash='dash', annotation_text='Extreme')
        fig_score.update_layout(template='plotly_dark', height=360, title='Whale Composite Score')
        st.plotly_chart(fig_score, use_container_width=True)
    with col2:
        st.plotly_chart(build_volume_profile(df), use_container_width=True)
    fig_bs = go.Figure()
    whale_df = df[df['Whale_Tier'] >= 1]
    fig_bs.add_bar(x=whale_df.index, y=whale_df['Buy_Vol'], name='Buy Pressure')
    fig_bs.add_bar(x=whale_df.index, y=-whale_df['Sell_Vol'], name='Sell Pressure')
    fig_bs.add_hline(y=0)
    fig_bs.update_layout(template='plotly_dark', height=360, barmode='relative', title='Whale Buy vs Sell Pressure')
    st.plotly_chart(fig_bs, use_container_width=True)
    fig_cluster = go.Figure(go.Bar(x=df.index, y=df['Whale_Cluster'], name='Whale Cluster'))
    fig_cluster.add_hline(y=2, line_dash='dash', annotation_text='Cluster threshold')
    fig_cluster.update_layout(template='plotly_dark', height=300, title='Whale Clustering: sustained institutional activity')
    st.plotly_chart(fig_cluster, use_container_width=True)

elif active_tab == "🗺️ Sector Map":
    st.markdown("### 🗺️ Sector Map + Themes — restored")
    st.caption("Full 11 GICS sectors plus themes like Defense, Semiconductors, Uranium, Oil Services and Gold Miners.")
    c1, c2, c3 = st.columns(3)
    with c1:
        sector_period = st.selectbox("Sector period", ["1mo", "3mo", "6mo", "1y"], index=1)
    with c2:
        sector_interval = st.selectbox("Sector interval", ["1d", "1wk"], index=0)
    with c3:
        show_group = st.selectbox("Group", ["All", "GICS Sector", "Theme"], index=0)
    sector_df = scan_rotation_map(sector_period, sector_interval)
    if not sector_df.empty:
        if show_group != "All":
            sector_df = sector_df[sector_df['Group'] == show_group]
        left, right = st.columns(2)
        with left:
            st.markdown("#### Top inflows")
            st.dataframe(sector_df.head(8), use_container_width=True, hide_index=True)
        with right:
            st.markdown("#### Top outflows")
            st.dataframe(sector_df.tail(8).sort_values('Rotation Score'), use_container_width=True, hide_index=True)
        fig_heat = go.Figure(go.Treemap(
            labels=sector_df['Name'], parents=[g for g in sector_df['Group']], values=[max(1, s) for s in sector_df['Rotation Score']],
            marker=dict(colors=sector_df['Rotation Score'], colorscale='RdYlGn', cmin=0, cmax=100),
            textinfo='label+value'
        ))
        fig_heat.update_layout(template='plotly_dark', height=520, title='Rotation Strength Map')
        st.plotly_chart(fig_heat, use_container_width=True)
        fig_bar = go.Figure(go.Bar(x=sector_df['Name'], y=sector_df['Rel vs SPY %'], marker_color=np.where(sector_df['Rel vs SPY %'] >= 0, '#22c55e', '#ef4444')))
        fig_bar.update_layout(template='plotly_dark', height=360, title='Relative Strength vs SPY', xaxis_tickangle=-45)
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.warning("Sector scan returned no data. Try a longer period or check yfinance availability.")

elif active_tab == "💎 Discovery":
    st.markdown("### 💎 Search Discovery — ETFs + Stocks")
    mode = st.radio("Universe", ["ETF", "Stock"], horizontal=True)
    if mode == "ETF":
        rows = ETF_CATALOG.copy()
        # Add items from theme dictionary if not in catalog
        seen = {r['Ticker'] for r in rows}
        for cat, themes in ETF_DISCOVERY_THEMES.items():
            for theme, tickers in themes.items():
                for t in tickers:
                    if t not in seen:
                        rows.append({'Ticker': t, 'Name': f'{theme} ETF / proxy', 'Tags': [theme, cat], 'Theme': theme, 'Category': cat, 'Expense': ETF_EXPENSES.get(t, np.nan)})
                        seen.add(t)
    else:
        rows = [
            {'Ticker':'NVDA','Name':'Nvidia','Tags':['AI','Semiconductors','Data Center','Momentum','Technology']},
            {'Ticker':'AMD','Name':'Advanced Micro Devices','Tags':['AI','Semiconductors','Technology']},
            {'Ticker':'PLTR','Name':'Palantir','Tags':['AI','Defense','Software','Government']},
            {'Ticker':'CLS.TO','Name':'Celestica','Tags':['AI Infrastructure','Hardware','Under the Radar','Canada']},
            {'Ticker':'VRT','Name':'Vertiv','Tags':['AI Infrastructure','Data Center','Energy']},
            {'Ticker':'CCJ','Name':'Cameco','Tags':['Uranium','Nuclear','Canada']},
            {'Ticker':'LMT','Name':'Lockheed Martin','Tags':['Defense','Aerospace']},
            {'Ticker':'NOC','Name':'Northrop Grumman','Tags':['Defense','Aerospace']},
            {'Ticker':'AEM.TO','Name':'Agnico Eagle','Tags':['Gold','Miner','Canada']},
            {'Ticker':'WPM.TO','Name':'Wheaton Precious Metals','Tags':['Gold','Silver','Streamer','Canada']},
        ]
    all_tags = sorted({tag for r in rows for tag in r.get('Tags', [])})
    q = st.text_input("Search keyword", placeholder="AI, defense, uranium, dividend, Canada...")
    selected_tags = st.multiselect("Tags", all_tags)
    match_mode = st.radio("Tag match", ["Any", "All"], horizontal=True)
    filtered = []
    for r in rows:
        text_blob = " ".join([str(r.get('Ticker','')), str(r.get('Name','')), " ".join(r.get('Tags', [])), str(r.get('Theme','')), str(r.get('Category',''))]).lower()
        q_ok = (not q) or (q.lower() in text_blob)
        if selected_tags:
            tags = set(r.get('Tags', []))
            tag_ok = bool(tags.intersection(selected_tags)) if match_mode == 'Any' else set(selected_tags).issubset(tags)
        else:
            tag_ok = True
        if q_ok and tag_ok:
            filtered.append(r)
    if filtered:
        st.dataframe(pd.DataFrame(filtered), use_container_width=True, hide_index=True)
        selected = st.selectbox("Analyze result", [r['Ticker'] for r in filtered])
        if st.button("Analyze selected ticker"):
            st.session_state['analyze_ticker'] = selected
            st.rerun()
    else:
        st.info("No matches. Try fewer tags or a broader keyword.")

elif active_tab == "🎯 Watchlist":
    st.markdown("### 🎯 Watchlist Scanner")
    watchlist_input = st.text_area("Enter tickers", "AAPL, MSFT, GOOGL, TSLA, NVDA, CLS.TO, CCJ, LMT, VRT")
    if st.button("🔍 Scan Watchlist"):
        watchlist = parse_tickers(watchlist_input)
        results = []
        progress_bar = st.progress(0)
        for idx, wl_ticker in enumerate(watchlist[:25]):
            wl_df, wl_info = fetch_data(wl_ticker, "3mo", "1d")
            if not wl_df.empty:
                wl_df = calculate_vwap(wl_df)
                wl_df['RSI'] = calculate_rsi(wl_df['Close'])
                wl_df['OBV'] = calculate_obv(wl_df)
                macd, sig, _ = calculate_macd(wl_df['Close']); wl_df['MACD'] = macd; wl_df['MACD_Signal'] = sig
                wl_df = add_whale_flow_metrics(wl_df)
                wl_score, _ = calculate_goat_score(wl_df, wl_info)
                bs = compute_buy_sell_score(wl_df, use_ml=False)
                results.append({'Ticker': wl_ticker, 'Price': round(wl_df['Close'].iloc[-1],2), 'GOAT': round(wl_score), 'Buy': bs['buy'], 'Sell': bs['sell'], 'Gap': bs['gap'], 'Signal': bs['signal'], 'Whale Score': round(wl_df['Whale_Score'].iloc[-1])})
            progress_bar.progress((idx + 1) / max(1, len(watchlist[:25])))
        if results:
            st.dataframe(pd.DataFrame(results).sort_values(['Buy','Gap'], ascending=False), use_container_width=True, hide_index=True)

elif active_tab == "📰 News":
    st.markdown("### 📰 News & Sentiment")
    news_days = st.slider("News lookback days", 1, 30, 1)
    articles = fetch_news_articles(ticker, max_age_days=news_days)
    if articles:
        impact_count = sum(1 for a in articles if a.get('is_high_impact'))
        press_count = sum(1 for a in articles if a.get('is_press'))
        n1, n2, n3 = st.columns(3)
        n1.metric("Headlines", len(articles)); n2.metric("High impact", impact_count); n3.metric("Press releases", press_count)
        for article in articles[:20]:
            sentiment_icon = "🟢" if article['sentiment'] > 0 else "🔴" if article['sentiment'] < 0 else "⚪"
            badge = "🚨 " if article.get('is_high_impact') else "📢 " if article.get('is_press') else ""
            st.markdown(f"{sentiment_icon} {badge}[{article['title']}]({article['url']})")
            st.caption(f"{article['source']} • {article['age_hrs']:.0f}h ago")
    else:
        st.info("No recent news available")

elif active_tab == "💼 Portfolio":
    st.markdown("### 💼 Portfolio Tracker")
    st.caption("Local-session tracker: paste positions, calculate P&L, sector/theme exposure, and risk.")
    positions_text = st.text_area("Positions: ticker,shares,entry_price", "AAPL,10,180\nNVDA,5,900\nCLS.TO,20,75")
    positions = []
    for line in positions_text.splitlines():
        try:
            t, sh, entry = [x.strip() for x in line.split(',')[:3]]
            sh = float(sh); entry = float(entry)
            p_df, p_info = fetch_data(t.upper(), '5d', '1d')
            if not p_df.empty:
                lastp = float(p_df['Close'].iloc[-1])
                value = lastp * sh; cost = entry * sh; pnl = value - cost
                positions.append({'Ticker': t.upper(), 'Shares': sh, 'Entry': entry, 'Last': round(lastp,2), 'Value': round(value,2), 'P&L': round(pnl,2), 'P&L %': round((lastp/entry-1)*100,2), 'Sector': p_info.get('sector','Unknown')})
        except Exception:
            continue
    if positions:
        pdf = pd.DataFrame(positions)
        st.dataframe(pdf, use_container_width=True, hide_index=True)
        p1, p2, p3 = st.columns(3)
        p1.metric('Portfolio Value', f"${pdf['Value'].sum():,.2f}")
        p2.metric('Total P&L', f"${pdf['P&L'].sum():,.2f}")
        p3.metric('Positions', len(pdf))
        fig_exp = go.Figure(go.Pie(labels=pdf['Sector'], values=pdf['Value'], hole=0.4))
        fig_exp.update_layout(template='plotly_dark', height=360, title='Sector Exposure')
        st.plotly_chart(fig_exp, use_container_width=True)

elif active_tab == "🥇 Metals":
    st.markdown("### 🥇 Precious Metals Smart Money Meter")
    metals = {'Gold':'GC=F', 'Silver':'SI=F', 'Copper':'HG=F', 'Platinum':'PL=F'}
    metal_rows = []
    for name, sym in metals.items():
        res = build_metal_meter(sym, name)
        if res: metal_rows.append(res)
    if metal_rows:
        mdf = pd.DataFrame(metal_rows)
        st.dataframe(mdf, use_container_width=True, hide_index=True)
        fig_m = go.Figure(go.Bar(x=mdf['Metal'], y=mdf['Smart Money Meter'], name='Smart Money Meter'))
        fig_m.add_hline(y=70, line_dash='dash', annotation_text='More buying than selling')
        fig_m.update_layout(template='plotly_dark', height=420, yaxis=dict(range=[0,100]), title='Metals Smart Money Meter')
        st.plotly_chart(fig_m, use_container_width=True)
        st.caption('COMEX/CFTC values here are proxies unless you connect official CFTC/CME warehouse feeds.')
    else:
        st.warning('No metals data available from yfinance right now.')

elif active_tab == "🤖 ML Lab":
    st.markdown("### 🤖 ML Lab — toggle now matters")
    if not ML_AVAILABLE:
        st.error("scikit-learn is not installed. Add scikit-learn to requirements.txt to enable ML.")
    elif not enable_ml_prediction:
        st.warning("ML Price Prediction is OFF in the sidebar. Composite signal excludes ML adjustment.")
    elif ml_prediction is None:
        st.warning("ML model could not produce a prediction, likely due to insufficient data.")
    else:
        confidence = ml_probability[int(ml_prediction)] * 100
        st.metric('ML Direction', 'Bullish' if ml_prediction == 1 else 'Bearish', f'{confidence:.1f}% confidence')
        st.metric('Composite ML Adjustment', f"{combined_score['ml_adjustment']:+d} pts")
        if ml_importance:
            imp = pd.DataFrame(list(ml_importance.items()), columns=['Feature','Importance']).sort_values('Importance', ascending=False)
            st.bar_chart(imp.set_index('Feature'))
        st.info('The model is a simple Random Forest classifier trained only on this ticker history. Treat it as a confirmation layer, not a standalone prediction engine.')

elif active_tab == "🔔 Alerts":
    st.markdown("### 🔔 Active Alerts")
    alerts = []
    if rsi_current < alert_rsi_oversold:
        alerts.append(('success', f"🟢 RSI Oversold: {rsi_current:.1f} < {alert_rsi_oversold}"))
    elif rsi_current > alert_rsi_overbought:
        alerts.append(('danger', f"🔴 RSI Overbought: {rsi_current:.1f} > {alert_rsi_overbought}"))
    if volume_ratio > alert_volume_spike:
        alerts.append(('warning', f"⚡ Volume Spike: {volume_ratio:.0f}% of average"))
    if combined_score['buy'] >= 70 and combined_score['gap'] >= 25:
        alerts.append(('success', f"🚀 High-conviction buy setup: {combined_score['buy']}/100, gap {combined_score['gap']}"))
    if combined_score['sell'] >= 70 and combined_score['gap'] >= 25:
        alerts.append(('danger', f"⚠️ High-conviction sell setup: {combined_score['sell']}/100, gap {combined_score['gap']}"))
    if alerts:
        for typ, msg in alerts:
            getattr(st, 'success' if typ == 'success' else 'error' if typ == 'danger' else 'warning')(msg)
    else:
        st.info("No active alerts at this time")

elif active_tab == "⚙️ Settings":
    st.markdown("### ⚙️ Advanced Settings")
    st.markdown("#### 📦 Required Packages")
    st.code("pip install streamlit yfinance pandas numpy plotly requests feedparser scikit-learn", language="bash")
    st.markdown("#### ✅ Restored in this version")
    st.write(["Sector Map", "Volume Profile", "Whale Composite Score", "Whale Buy/Sell Pressure", "Whale Clustering", "ETF + Stock Discovery", "Portfolio Tracker", "Metals Smart Money Meter", "ML score impact"])
    if st.button("🗑️ Clear All Caches"):
        st.cache_data.clear()
        st.success("All caches cleared!")
        st.rerun()

# Auto-refresh logic
if realtime_on:
    time.sleep(refresh_interval)
    st.cache_data.clear()
    st.rerun()

# Footer
st.markdown("---")
st.markdown("""
    <div style='text-align: center; color: rgba(255,255,255,0.5); padding: 20px;'>
        <p>Institutional Flow Pro+ v2.0 | Made with ❤️ using Streamlit</p>
        <p style='font-size: 0.8em;'>⚠️ For educational purposes only. Not financial advice.</p>
    </div>
""", unsafe_allow_html=True)
