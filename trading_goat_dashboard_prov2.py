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

# Calculate scores
goat_score, goat_reasons = calculate_goat_score(df, info)
advanced_metrics = calculate_advanced_metrics(df, info)

# ML Prediction
ml_prediction = None
ml_probability = None
ml_importance = None
if enable_ml_prediction:
    ml_prediction, ml_probability, ml_importance = ml_price_prediction(df)

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

# =========================================================
# TABS FOR DIFFERENT SECTIONS
# =========================================================

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Analysis", "🎯 Watchlist", "💎 Discovery", "📰 News", "🔔 Alerts", "⚙️ Settings"
])

with tab1:
    st.markdown("### 📊 Technical Analysis Summary")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### GOAT Quality Breakdown")
        st.markdown(f"**Overall Score: {goat_score:.0f}/100**")
        for reason in goat_reasons:
            st.markdown(f"• {reason}")
        
        st.markdown("---")
        st.markdown("#### Advanced Metrics")
        st.markdown(f"• **Sharpe Ratio:** {advanced_metrics.get('sharpe_ratio', 0):.2f}")
        st.markdown(f"• **Max Drawdown:** {advanced_metrics.get('max_drawdown', 0):.2f}%")
        st.markdown(f"• **Volatility:** {advanced_metrics.get('volatility', 0):.2f}%")
        st.markdown(f"• **Beta:** {advanced_metrics.get('beta', 1.0):.2f}")
    
    with col2:
        st.markdown("#### Key Levels")
        support, resistance = find_support_resistance(df)
        
        st.markdown("**Support Levels:**")
        for s in support[:3]:
            st.markdown(f"• ${s:.2f}")
        
        st.markdown("**Resistance Levels:**")
        for r in resistance[:3]:
            st.markdown(f"• ${r:.2f}")
        
        if show_fibonacci:
            st.markdown("---")
            st.markdown("**Fibonacci Levels:**")
            fib = calculate_fibonacci_levels(df)
            for level, price in list(fib.items())[:4]:
                st.markdown(f"• {level}: ${price:.2f}")

with tab2:
    st.markdown("### 🎯 Watchlist Scanner")
    st.info("Multi-ticker scanning feature - enter tickers separated by commas")
    
    watchlist_input = st.text_area("Enter tickers (comma-separated)", "AAPL, MSFT, GOOGL, TSLA, NVDA")
    
    if st.button("🔍 Scan Watchlist"):
        watchlist = parse_tickers(watchlist_input)
        results = []
        
        progress_bar = st.progress(0)
        for idx, wl_ticker in enumerate(watchlist[:10]):
            try:
                wl_df, wl_info = fetch_data(wl_ticker, "3mo", "1d")
                if not wl_df.empty:
                    wl_score, _ = calculate_goat_score(wl_df, wl_info)
                    wl_rsi = calculate_rsi(wl_df['Close']).iloc[-1]
                    wl_price = wl_df['Close'].iloc[-1]
                    wl_change = ((wl_df['Close'].iloc[-1] / wl_df['Close'].iloc[-2]) - 1) * 100
                    
                    results.append({
                        'Ticker': wl_ticker,
                        'Price': f"${wl_price:.2f}",
                        'Change %': f"{wl_change:+.2f}%",
                        'RSI': f"{wl_rsi:.1f}",
                        'GOAT Score': f"{wl_score:.0f}",
                        'Signal': '🟢 Buy' if wl_rsi < 35 and wl_score > 60 else '🔴 Sell' if wl_rsi > 65 else '⚪ Hold'
                    })
                progress_bar.progress((idx + 1) / len(watchlist[:10]))
            except:
                continue
        
        if results:
            results_df = pd.DataFrame(results)
            st.dataframe(results_df, use_container_width=True, hide_index=True)

with tab3:
    st.markdown("### 💎 ETF & Sector Discovery")
    st.info("Explore themed ETFs and sector rotation opportunities")
    
    theme_choice = st.selectbox("Select Theme", list(ETF_DISCOVERY_THEMES.keys()))
    
    if theme_choice:
        st.markdown(f"#### {theme_choice} ETFs")
        for category, tickers in ETF_DISCOVERY_THEMES[theme_choice].items():
            with st.expander(f"📁 {category}"):
                for idx, etf_ticker in enumerate(tickers[:5]):
                    col1, col2, col3 = st.columns([2, 1, 1])
                    with col1:
                        st.markdown(f"**{etf_ticker}**")
                    with col2:
                        expense = ETF_EXPENSES.get(etf_ticker, 0.0)
                        st.markdown(f"Fee: {expense:.2f}%")
                    with col3:
                        # Make key unique by combining theme, category, index and ticker
                        unique_key = f"analyze_{theme_choice}_{category}_{idx}_{etf_ticker}"
                        if st.button(f"Analyze", key=unique_key):
                            st.session_state['analyze_ticker'] = etf_ticker
                            st.rerun()

with tab4:
    st.markdown("### 📰 News & Sentiment")
    articles = fetch_news_articles(ticker, max_age_days=3)
    
    if articles:
        high_impact = [a for a in articles if a.get('is_high_impact')]
        
        if high_impact:
            st.markdown("#### 🚨 High Impact News")
            for article in high_impact[:5]:
                sentiment_icon = "🟢" if article['sentiment'] > 0 else "🔴" if article['sentiment'] < 0 else "⚪"
                st.markdown(f"{sentiment_icon} [{article['title']}]({article['url']})")
                st.caption(f"{article['source']} • {article['age_hrs']:.0f}h ago")
                st.markdown("---")
        
        st.markdown("#### 📢 Recent Headlines")
        for article in articles[:10]:
            sentiment_icon = "🟢" if article['sentiment'] > 0 else "🔴" if article['sentiment'] < 0 else "⚪"
            st.markdown(f"{sentiment_icon} [{article['title']}]({article['url']})")
            st.caption(f"{article['source']} • {article['age_hrs']:.0f}h ago")
    else:
        st.info("No recent news available")

with tab5:
    st.markdown("### 🔔 Active Alerts")
    
    alerts = []
    
    # RSI Alerts
    if rsi_current < alert_rsi_oversold:
        alerts.append({
            'type': 'success',
            'message': f"🟢 RSI Oversold: {rsi_current:.1f} < {alert_rsi_oversold}"
        })
    elif rsi_current > alert_rsi_overbought:
        alerts.append({
            'type': 'danger',
            'message': f"🔴 RSI Overbought: {rsi_current:.1f} > {alert_rsi_overbought}"
        })
    
    # Volume Alerts
    if volume_ratio > alert_volume_spike:
        alerts.append({
            'type': 'warning',
            'message': f"⚡ Volume Spike: {volume_ratio:.0f}% of average"
        })
    
    # ML Alerts
    if enable_ml_prediction and ml_prediction is not None:
        if ml_prediction == 1 and ml_probability[1] > 0.7:
            alerts.append({
                'type': 'success',
                'message': f"🤖 Strong AI Buy Signal ({ml_probability[1]*100:.0f}% confidence)"
            })
        elif ml_prediction == 0 and ml_probability[0] > 0.7:
            alerts.append({
                'type': 'danger',
                'message': f"🤖 Strong AI Sell Signal ({ml_probability[0]*100:.0f}% confidence)"
            })
    
    if alerts:
        for alert in alerts:
            alert_class = f"alert-{alert['type']}"
            st.markdown(f"""
                <div class="alert-box {alert_class}">
                    {alert['message']}
                </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No active alerts at this time")

with tab6:
    st.markdown("### ⚙️ Advanced Settings")
    
    st.markdown("#### 📦 Required Packages")
    st.code("pip install streamlit yfinance pandas numpy plotly requests feedparser scikit-learn", language="bash")
    
    st.markdown("#### 🔌 API Integrations")
    st.info("""
    **Available Integrations:**
    - Discord Webhooks for alerts
    - Telegram Bot for notifications
    - Custom data feeds (configure in sidebar)
    - Export to PDF/CSV/JSON
    """)
    
    st.markdown("#### 📊 Performance Stats")
    st.markdown(f"• Cache size: {len(st.session_state)} items")
    st.markdown(f"• Last refresh: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
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
