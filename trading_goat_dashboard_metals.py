import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, timedelta
import time
import re
import os
import json
from pathlib import Path

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
st.caption("VWAP · RSI · MACD · OBV · Whale Flow · GOAT Quality Score · ETF/Stock Discovery · Hidden Gems · Sector Heatmap · Real Alerts · Portfolio Tracker")

# Full 11-sector GICS ETF proxy map. These ETFs are used for sector rotation analysis.
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

# Thematic/industry ETFs are not official GICS sectors, but they are useful for spotting
# earlier money rotation in areas like defense, semiconductors, uranium, infrastructure, etc.
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

# GOAT-style ETF discovery groups used for themed browsing.
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


# ETF discovery catalog: searchable/tag-based rather than fixed theme lists.
# This powers the GOAT-style ETF discovery page with multi-tag filtering.
ETF_CATALOG = [
    {"Ticker":"SPY", "Name":"SPDR S&P 500 ETF Trust", "Tags":["US Large Cap","S&P 500","Core","Equity","Low Fee"], "Theme":"US Large Cap", "Category":"Geography", "Expense":0.09},
    {"Ticker":"VOO", "Name":"Vanguard S&P 500 ETF", "Tags":["US Large Cap","S&P 500","Core","Equity","Low Fee","Fee Saver"], "Theme":"US Large Cap", "Category":"Geography", "Expense":0.03},
    {"Ticker":"IVV", "Name":"iShares Core S&P 500 ETF", "Tags":["US Large Cap","S&P 500","Core","Equity","Low Fee","Fee Saver"], "Theme":"US Large Cap", "Category":"Geography", "Expense":0.03},
    {"Ticker":"QQQ", "Name":"Invesco QQQ Trust", "Tags":["AI","Growth","Nasdaq","Technology","Mega Cap"], "Theme":"AI / Growth", "Category":"Hot Themes", "Expense":0.20},
    {"Ticker":"QQQM", "Name":"Invesco NASDAQ 100 ETF", "Tags":["AI","Growth","Nasdaq","Technology","Low Fee","Fee Saver"], "Theme":"AI / Growth", "Category":"Hot Themes", "Expense":0.15},
    {"Ticker":"SMH", "Name":"VanEck Semiconductor ETF", "Tags":["Semiconductors","AI Infrastructure","Chips","Technology"], "Theme":"Semiconductors", "Category":"Hot Themes", "Expense":0.35},
    {"Ticker":"SOXX", "Name":"iShares Semiconductor ETF", "Tags":["Semiconductors","AI Infrastructure","Chips","Technology"], "Theme":"Semiconductors", "Category":"Hot Themes", "Expense":0.35},
    {"Ticker":"BOTZ", "Name":"Global X Robotics & AI ETF", "Tags":["AI","Robotics & Automation","Automation","Technology"], "Theme":"Robotics & Automation", "Category":"Hot Themes", "Expense":0.68},
    {"Ticker":"AIQ", "Name":"Global X Artificial Intelligence & Technology ETF", "Tags":["AI","Technology","Growth"], "Theme":"AI", "Category":"Hot Themes", "Expense":0.68},
    {"Ticker":"ROBO", "Name":"ROBO Global Robotics & Automation ETF", "Tags":["Robotics & Automation","Automation","Industrial Tech"], "Theme":"Robotics & Automation", "Category":"Hot Themes", "Expense":0.95},
    {"Ticker":"ITA", "Name":"iShares U.S. Aerospace & Defense ETF", "Tags":["Defense","Aerospace","Government Spending","Industrials","Geopolitics"], "Theme":"Defense", "Category":"Hot Themes", "Expense":0.40},
    {"Ticker":"XAR", "Name":"SPDR S&P Aerospace & Defense ETF", "Tags":["Defense","Aerospace","Industrials","Geopolitics"], "Theme":"Defense", "Category":"Hot Themes", "Expense":0.35},
    {"Ticker":"XLE", "Name":"Energy Select Sector SPDR Fund", "Tags":["Energy","Oil","Gas","Inflation","Commodity"], "Theme":"Energy", "Category":"Hot Themes", "Expense":0.09},
    {"Ticker":"XOP", "Name":"SPDR S&P Oil & Gas Exploration & Production ETF", "Tags":["Energy","Oil","Exploration","High Beta"], "Theme":"Energy", "Category":"Hot Themes", "Expense":0.35},
    {"Ticker":"OIH", "Name":"VanEck Oil Services ETF", "Tags":["Energy","Oil Services","Oil","Geopolitics","Inflation"], "Theme":"Oil Services", "Category":"Hot Themes", "Expense":0.35},
    {"Ticker":"URA", "Name":"Global X Uranium ETF", "Tags":["Uranium","Nuclear","Energy","Commodity"], "Theme":"Uranium", "Category":"Hot Themes", "Expense":0.69},
    {"Ticker":"URNM", "Name":"Sprott Uranium Miners ETF", "Tags":["Uranium","Nuclear","Energy","Miners","Commodity"], "Theme":"Uranium", "Category":"Hot Themes", "Expense":0.75},
    {"Ticker":"NLR", "Name":"VanEck Uranium and Nuclear ETF", "Tags":["Nuclear","Uranium","Energy"], "Theme":"Nuclear", "Category":"Hot Themes", "Expense":0.61},
    {"Ticker":"GLD", "Name":"SPDR Gold Shares", "Tags":["Gold","Precious Metals","Hard Assets","Inflation","Defensive"], "Theme":"Gold", "Category":"Hot Themes", "Expense":0.40},
    {"Ticker":"IAU", "Name":"iShares Gold Trust", "Tags":["Gold","Precious Metals","Hard Assets","Low Fee","Fee Saver"], "Theme":"Gold", "Category":"Hot Themes", "Expense":0.25},
    {"Ticker":"GDX", "Name":"VanEck Gold Miners ETF", "Tags":["Gold","Gold Miners","Precious Metals","Miners"], "Theme":"Gold Miners", "Category":"Hot Themes", "Expense":0.51},
    {"Ticker":"GDXJ", "Name":"VanEck Junior Gold Miners ETF", "Tags":["Gold","Gold Miners","Precious Metals","High Beta","Miners"], "Theme":"Gold Miners", "Category":"Hot Themes", "Expense":0.52},
    {"Ticker":"IBIT", "Name":"iShares Bitcoin Trust ETF", "Tags":["Bitcoin / Crypto","Bitcoin","Crypto","Digital Assets"], "Theme":"Bitcoin / Crypto", "Category":"Hot Themes", "Expense":0.25},
    {"Ticker":"BITB", "Name":"Bitwise Bitcoin ETF", "Tags":["Bitcoin / Crypto","Bitcoin","Crypto","Digital Assets"], "Theme":"Bitcoin / Crypto", "Category":"Hot Themes", "Expense":0.20},
    {"Ticker":"HACK", "Name":"ETFMG Prime Cyber Security ETF", "Tags":["Cybersecurity","Technology","Defense","Software"], "Theme":"Cybersecurity", "Category":"Hot Themes", "Expense":0.60},
    {"Ticker":"CIBR", "Name":"First Trust NASDAQ Cybersecurity ETF", "Tags":["Cybersecurity","Technology","Software"], "Theme":"Cybersecurity", "Category":"Hot Themes", "Expense":0.60},
    {"Ticker":"ARKX", "Name":"ARK Space Exploration & Innovation ETF", "Tags":["Space","Innovation","Aerospace","High Beta"], "Theme":"Space", "Category":"Hot Themes", "Expense":0.75},
    {"Ticker":"UFO", "Name":"Procure Space ETF", "Tags":["Space","Aerospace","Satellite"], "Theme":"Space", "Category":"Hot Themes", "Expense":0.75},
    {"Ticker":"LIT", "Name":"Global X Lithium & Battery Tech ETF", "Tags":["Lithium / EV","Lithium","Battery","EV","Commodity"], "Theme":"Lithium / EV", "Category":"Hot Themes", "Expense":0.75},
    {"Ticker":"DRIV", "Name":"Global X Autonomous & Electric Vehicles ETF", "Tags":["Lithium / EV","EV","Autonomous","Technology"], "Theme":"Lithium / EV", "Category":"Hot Themes", "Expense":0.68},
    {"Ticker":"ICLN", "Name":"iShares Global Clean Energy ETF", "Tags":["Clean Energy","Renewables","Energy Transition"], "Theme":"Clean Energy", "Category":"Hot Themes", "Expense":0.41},
    {"Ticker":"QCLN", "Name":"First Trust NASDAQ Clean Edge Green Energy ETF", "Tags":["Clean Energy","EV","Renewables","High Beta"], "Theme":"Clean Energy", "Category":"Hot Themes", "Expense":0.58},
    {"Ticker":"SCHD", "Name":"Schwab U.S. Dividend Equity ETF", "Tags":["Dividend","Income","Quality","Value","Low Fee"], "Theme":"Dividend", "Category":"Income", "Expense":0.06},
    {"Ticker":"VYM", "Name":"Vanguard High Dividend Yield ETF", "Tags":["Dividend","Income","Value","Low Fee"], "Theme":"Dividend", "Category":"Income", "Expense":0.06},
    {"Ticker":"XEI.TO", "Name":"iShares S&P/TSX Composite High Dividend ETF", "Tags":["Dividend","Income","Canada","TSX"], "Theme":"Dividend", "Category":"Income", "Expense":0.22},
    {"Ticker":"VNQ", "Name":"Vanguard Real Estate ETF", "Tags":["REITs","Real Estate","Income","Rate Sensitive"], "Theme":"REITs", "Category":"Income", "Expense":0.13},
    {"Ticker":"XLRE", "Name":"Real Estate Select Sector SPDR Fund", "Tags":["REITs","Real Estate","Income","Rate Sensitive"], "Theme":"REITs", "Category":"Income", "Expense":0.09},
    {"Ticker":"ZRE.TO", "Name":"BMO Equal Weight REITs Index ETF", "Tags":["REITs","Real Estate","Income","Canada","TSX"], "Theme":"REITs", "Category":"Income", "Expense":0.61},
    {"Ticker":"AGG", "Name":"iShares Core U.S. Aggregate Bond ETF", "Tags":["Bonds","Income","Defensive","Treasuries"], "Theme":"Bonds", "Category":"Income", "Expense":0.03},
    {"Ticker":"BND", "Name":"Vanguard Total Bond Market ETF", "Tags":["Bonds","Income","Defensive","Low Fee"], "Theme":"Bonds", "Category":"Income", "Expense":0.03},
    {"Ticker":"TLT", "Name":"iShares 20+ Year Treasury Bond ETF", "Tags":["Treasuries","Bonds","Duration","Rate Sensitive","Defensive"], "Theme":"Treasuries", "Category":"Income", "Expense":0.15},
    {"Ticker":"IEF", "Name":"iShares 7-10 Year Treasury Bond ETF", "Tags":["Treasuries","Bonds","Defensive"], "Theme":"Treasuries", "Category":"Income", "Expense":0.15},
    {"Ticker":"SGOV", "Name":"iShares 0-3 Month Treasury Bond ETF", "Tags":["Treasuries","Cash","Defensive","Income"], "Theme":"Treasuries", "Category":"Income", "Expense":0.09},
    {"Ticker":"IWM", "Name":"iShares Russell 2000 ETF", "Tags":["US Small Cap","Equity","Risk On"], "Theme":"US Small Cap", "Category":"Geography", "Expense":0.19},
    {"Ticker":"VB", "Name":"Vanguard Small-Cap ETF", "Tags":["US Small Cap","Equity","Low Fee"], "Theme":"US Small Cap", "Category":"Geography", "Expense":0.05},
    {"Ticker":"VGK", "Name":"Vanguard FTSE Europe ETF", "Tags":["Europe","International","Equity"], "Theme":"Europe", "Category":"Geography", "Expense":0.09},
    {"Ticker":"IEUR", "Name":"iShares Core MSCI Europe ETF", "Tags":["Europe","International","Equity"], "Theme":"Europe", "Category":"Geography", "Expense":0.09},
    {"Ticker":"EWU", "Name":"iShares MSCI United Kingdom ETF", "Tags":["UK","International","Equity"], "Theme":"UK", "Category":"Geography", "Expense":0.50},
    {"Ticker":"EWJ", "Name":"iShares MSCI Japan ETF", "Tags":["Japan","International","Equity"], "Theme":"Japan", "Category":"Geography", "Expense":0.50},
    {"Ticker":"FXI", "Name":"iShares China Large-Cap ETF", "Tags":["China","Emerging Markets","International"], "Theme":"China", "Category":"Geography", "Expense":0.74},
    {"Ticker":"MCHI", "Name":"iShares MSCI China ETF", "Tags":["China","Emerging Markets","International"], "Theme":"China", "Category":"Geography", "Expense":0.58},
    {"Ticker":"INDA", "Name":"iShares MSCI India ETF", "Tags":["India","Emerging Markets","International"], "Theme":"India", "Category":"Geography", "Expense":0.65},
    {"Ticker":"EEM", "Name":"iShares MSCI Emerging Markets ETF", "Tags":["Emerging Markets","International"], "Theme":"Emerging Markets", "Category":"Geography", "Expense":0.70},
    {"Ticker":"VWO", "Name":"Vanguard FTSE Emerging Markets ETF", "Tags":["Emerging Markets","International","Low Fee"], "Theme":"Emerging Markets", "Category":"Geography", "Expense":0.08},
    {"Ticker":"QUAL", "Name":"iShares MSCI USA Quality Factor ETF", "Tags":["Quality","Factor","Profitability","Stable"], "Theme":"Quality", "Category":"Style", "Expense":0.15},
    {"Ticker":"SPHQ", "Name":"Invesco S&P 500 Quality ETF", "Tags":["Quality","Factor","Profitability","Stable"], "Theme":"Quality", "Category":"Style", "Expense":0.15},
    {"Ticker":"MTUM", "Name":"iShares MSCI USA Momentum Factor ETF", "Tags":["Momentum","Factor","Trend"], "Theme":"Momentum", "Category":"Style", "Expense":0.15},
    {"Ticker":"PDP", "Name":"Invesco Dorsey Wright Momentum ETF", "Tags":["Momentum","Factor","Trend"], "Theme":"Momentum", "Category":"Style", "Expense":0.62},
    {"Ticker":"VLUE", "Name":"iShares MSCI USA Value Factor ETF", "Tags":["Value","Factor","Cheap"], "Theme":"Value", "Category":"Style", "Expense":0.15},
    {"Ticker":"VTV", "Name":"Vanguard Value ETF", "Tags":["Value","Factor","Low Fee"], "Theme":"Value", "Category":"Style", "Expense":0.04},
]

# Fill expense table with ETF catalog values where available.
for _row in ETF_CATALOG:
    ETF_EXPENSES.setdefault(_row["Ticker"], _row.get("Expense", np.nan))

ETF_TAGS = sorted({tag for row in ETF_CATALOG for tag in row.get("Tags", [])})
ETF_CATEGORIES = sorted({row.get("Category", "Other") for row in ETF_CATALOG})


def search_etf_catalog(query: str = "", selected_tags=None, categories=None, match_mode: str = "Any") -> pd.DataFrame:
    """Search ETFs by ticker/name/theme/tags, like a small tag-based search engine."""
    selected_tags = selected_tags or []
    categories = categories or []
    q = (query or "").strip().lower()
    rows = []
    for item in ETF_CATALOG:
        haystack = " ".join([
            item.get("Ticker", ""), item.get("Name", ""), item.get("Theme", ""),
            item.get("Category", ""), " ".join(item.get("Tags", []))
        ]).lower()
        if q and q not in haystack:
            continue
        if categories and item.get("Category") not in categories:
            continue
        item_tags = set(item.get("Tags", []))
        if selected_tags:
            wanted = set(selected_tags)
            if match_mode == "All" and not wanted.issubset(item_tags):
                continue
            if match_mode == "Any" and not (wanted & item_tags):
                continue
        tag_score = len(set(selected_tags) & set(item.get("Tags", []))) if selected_tags else 0
        text_score = 1 if q and q in haystack else 0
        expense = item.get("Expense", ETF_EXPENSES.get(item.get("Ticker"), np.nan))
        rows.append({
            "Ticker": item.get("Ticker"),
            "Name": item.get("Name"),
            "Theme": item.get("Theme"),
            "Category": item.get("Category"),
            "Tags": ", ".join(item.get("Tags", [])),
            "Expense %": expense,
            "Match Score": tag_score * 10 + text_score,
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["Match Score", "Expense %", "Ticker"], ascending=[False, True, True])


# Stock discovery catalog: same tag/search engine concept, but for individual companies.
# This is a curated starter universe. It is meant to be expanded over time or replaced by an API-backed screener.
STOCK_CATALOG = [
    {"Ticker":"NVDA", "Name":"Nvidia", "Sector":"Information Technology", "Theme":"AI / Semiconductors", "Tags":["AI","AI Infrastructure","Semiconductors","Chips","Data Center","Momentum","Mega Cap","Quality"]},
    {"Ticker":"AMD", "Name":"Advanced Micro Devices", "Sector":"Information Technology", "Theme":"AI / Semiconductors", "Tags":["AI","Semiconductors","Chips","Data Center","High Beta","Growth"]},
    {"Ticker":"AVGO", "Name":"Broadcom", "Sector":"Information Technology", "Theme":"AI Infrastructure", "Tags":["AI Infrastructure","Semiconductors","Networking","Data Center","Quality","Dividend"]},
    {"Ticker":"TSM", "Name":"Taiwan Semiconductor", "Sector":"Information Technology", "Theme":"Semiconductors", "Tags":["Semiconductors","Foundry","AI Infrastructure","Chips","International","Quality"]},
    {"Ticker":"ASML", "Name":"ASML Holding", "Sector":"Information Technology", "Theme":"Semiconductor Equipment", "Tags":["Semiconductors","Equipment","Europe","Monopoly","Quality"]},
    {"Ticker":"MU", "Name":"Micron", "Sector":"Information Technology", "Theme":"Memory / AI", "Tags":["Semiconductors","Memory","AI Infrastructure","Cyclical","High Beta"]},
    {"Ticker":"SMCI", "Name":"Super Micro Computer", "Sector":"Information Technology", "Theme":"AI Infrastructure", "Tags":["AI Infrastructure","Servers","Data Center","High Beta"]},
    {"Ticker":"VRT", "Name":"Vertiv", "Sector":"Industrials", "Theme":"AI Infrastructure", "Tags":["AI Infrastructure","Data Center","Power","Cooling","Industrials","Momentum"]},
    {"Ticker":"ETN", "Name":"Eaton", "Sector":"Industrials", "Theme":"Electrification", "Tags":["AI Infrastructure","Power","Grid","Infrastructure","Quality","Industrials"]},
    {"Ticker":"PWR", "Name":"Quanta Services", "Sector":"Industrials", "Theme":"Grid Infrastructure", "Tags":["Infrastructure","Grid","Power","Clean Energy","Industrials"]},
    {"Ticker":"PLTR", "Name":"Palantir", "Sector":"Information Technology", "Theme":"AI / Defense Software", "Tags":["AI","Software","Defense","Government Spending","High Beta","Momentum"]},
    {"Ticker":"MSFT", "Name":"Microsoft", "Sector":"Information Technology", "Theme":"AI / Cloud", "Tags":["AI","Cloud","Software","Mega Cap","Quality","Dividend"]},
    {"Ticker":"GOOGL", "Name":"Alphabet", "Sector":"Communication Services", "Theme":"AI / Digital Ads", "Tags":["AI","Cloud","Advertising","Mega Cap","Quality"]},
    {"Ticker":"META", "Name":"Meta Platforms", "Sector":"Communication Services", "Theme":"AI / Digital Ads", "Tags":["AI","Advertising","Social Media","Mega Cap","Quality","Momentum"]},
    {"Ticker":"AMZN", "Name":"Amazon", "Sector":"Consumer Discretionary", "Theme":"Cloud / Consumer", "Tags":["Cloud","AI","E-commerce","Mega Cap","Growth"]},
    {"Ticker":"AAPL", "Name":"Apple", "Sector":"Information Technology", "Theme":"Consumer Tech", "Tags":["Mega Cap","Quality","Hardware","Consumer","Dividend"]},
    {"Ticker":"CRWD", "Name":"CrowdStrike", "Sector":"Information Technology", "Theme":"Cybersecurity", "Tags":["Cybersecurity","Software","Growth","High Beta"]},
    {"Ticker":"PANW", "Name":"Palo Alto Networks", "Sector":"Information Technology", "Theme":"Cybersecurity", "Tags":["Cybersecurity","Software","Quality","Growth"]},
    {"Ticker":"NET", "Name":"Cloudflare", "Sector":"Information Technology", "Theme":"Cybersecurity / Cloud", "Tags":["Cybersecurity","Cloud","Software","High Beta","Growth"]},
    {"Ticker":"LMT", "Name":"Lockheed Martin", "Sector":"Industrials", "Theme":"Defense", "Tags":["Defense","Aerospace","Government Spending","Dividend","Quality"]},
    {"Ticker":"RTX", "Name":"RTX", "Sector":"Industrials", "Theme":"Defense", "Tags":["Defense","Aerospace","Government Spending","Dividend"]},
    {"Ticker":"NOC", "Name":"Northrop Grumman", "Sector":"Industrials", "Theme":"Defense", "Tags":["Defense","Aerospace","Government Spending","Quality"]},
    {"Ticker":"GD", "Name":"General Dynamics", "Sector":"Industrials", "Theme":"Defense", "Tags":["Defense","Aerospace","Government Spending","Dividend"]},
    {"Ticker":"HWM", "Name":"Howmet Aerospace", "Sector":"Industrials", "Theme":"Aerospace", "Tags":["Aerospace","Defense","Industrials","Quality","Momentum"]},
    {"Ticker":"CLS", "Name":"Celestica", "Sector":"Information Technology", "Theme":"AI Supply Chain", "Tags":["AI Infrastructure","Manufacturing","Electronics","Cash Flow","Hidden Gem","Canada"]},
    {"Ticker":"FLEX", "Name":"Flex", "Sector":"Information Technology", "Theme":"Electronics Manufacturing", "Tags":["Manufacturing","Electronics","Cash Flow","Hidden Gem","Value"]},
    {"Ticker":"JBL", "Name":"Jabil", "Sector":"Information Technology", "Theme":"Electronics Manufacturing", "Tags":["Manufacturing","Electronics","Cash Flow","Hidden Gem","Value"]},
    {"Ticker":"SANM", "Name":"Sanmina", "Sector":"Information Technology", "Theme":"Electronics Manufacturing", "Tags":["Manufacturing","Electronics","Cash Flow","Hidden Gem","Value"]},
    {"Ticker":"XOM", "Name":"Exxon Mobil", "Sector":"Energy", "Theme":"Energy", "Tags":["Energy","Oil","Dividend","Cash Flow","Inflation"]},
    {"Ticker":"CVX", "Name":"Chevron", "Sector":"Energy", "Theme":"Energy", "Tags":["Energy","Oil","Dividend","Cash Flow","Quality"]},
    {"Ticker":"CNQ.TO", "Name":"Canadian Natural Resources", "Sector":"Energy", "Theme":"Canadian Energy", "Tags":["Energy","Oil","Canada","TSX","Dividend","Cash Flow"]},
    {"Ticker":"SU.TO", "Name":"Suncor Energy", "Sector":"Energy", "Theme":"Canadian Energy", "Tags":["Energy","Oil","Canada","TSX","Value","Dividend"]},
    {"Ticker":"WCP.TO", "Name":"Whitecap Resources", "Sector":"Energy", "Theme":"Canadian Energy", "Tags":["Energy","Oil","Canada","TSX","Dividend","Small Cap"]},
    {"Ticker":"TVE.TO", "Name":"Tamarack Valley Energy", "Sector":"Energy", "Theme":"Canadian Energy", "Tags":["Energy","Oil","Canada","TSX","Small Cap","High Beta"]},
    {"Ticker":"CVE.TO", "Name":"Cenovus Energy", "Sector":"Energy", "Theme":"Canadian Energy", "Tags":["Energy","Oil","Canada","TSX","Value"]},
    {"Ticker":"ENB.TO", "Name":"Enbridge", "Sector":"Energy", "Theme":"Pipelines", "Tags":["Energy","Pipelines","Canada","TSX","Dividend","Income"]},
    {"Ticker":"TRP.TO", "Name":"TC Energy", "Sector":"Energy", "Theme":"Pipelines", "Tags":["Energy","Pipelines","Canada","TSX","Dividend","Income"]},
    {"Ticker":"CCO.TO", "Name":"Cameco", "Sector":"Energy", "Theme":"Uranium", "Tags":["Uranium","Nuclear","Energy","Canada","TSX","Commodity"]},
    {"Ticker":"UEC", "Name":"Uranium Energy", "Sector":"Energy", "Theme":"Uranium", "Tags":["Uranium","Nuclear","Energy","High Beta","Commodity"]},
    {"Ticker":"FCX", "Name":"Freeport-McMoRan", "Sector":"Materials", "Theme":"Copper", "Tags":["Copper","Materials","Commodity","Inflation","Cyclical"]},
    {"Ticker":"TECK.B.TO", "Name":"Teck Resources", "Sector":"Materials", "Theme":"Copper / Materials", "Tags":["Copper","Materials","Canada","TSX","Commodity","Value"]},
    {"Ticker":"NEM", "Name":"Newmont", "Sector":"Materials", "Theme":"Gold Miners", "Tags":["Gold","Gold Miners","Materials","Dividend","Commodity"]},
    {"Ticker":"AEM.TO", "Name":"Agnico Eagle Mines", "Sector":"Materials", "Theme":"Gold Miners", "Tags":["Gold","Gold Miners","Canada","TSX","Quality","Commodity"]},
    {"Ticker":"WPM.TO", "Name":"Wheaton Precious Metals", "Sector":"Materials", "Theme":"Precious Metals Royalty", "Tags":["Gold","Silver","Royalty","Canada","TSX","Quality"]},
    {"Ticker":"JPM", "Name":"JPMorgan Chase", "Sector":"Financials", "Theme":"Banks", "Tags":["Banks","Financials","Dividend","Quality"]},
    {"Ticker":"RY.TO", "Name":"Royal Bank of Canada", "Sector":"Financials", "Theme":"Canadian Banks", "Tags":["Banks","Financials","Canada","TSX","Dividend","Quality"]},
    {"Ticker":"TD.TO", "Name":"TD Bank", "Sector":"Financials", "Theme":"Canadian Banks", "Tags":["Banks","Financials","Canada","TSX","Dividend"]},
    {"Ticker":"SHOP.TO", "Name":"Shopify", "Sector":"Information Technology", "Theme":"E-commerce Software", "Tags":["Software","E-commerce","Canada","TSX","Growth","High Beta"]},
    {"Ticker":"CSU.TO", "Name":"Constellation Software", "Sector":"Information Technology", "Theme":"Vertical Software", "Tags":["Software","Canada","TSX","Quality","Compounder"]},
    {"Ticker":"TOI.V", "Name":"Topicus", "Sector":"Information Technology", "Theme":"Vertical Software", "Tags":["Software","Canada","TSX","Compounder","Small Cap"]},
    {"Ticker":"ATD.TO", "Name":"Alimentation Couche-Tard", "Sector":"Consumer Staples", "Theme":"Convenience Retail", "Tags":["Consumer Staples","Canada","TSX","Quality","Defensive"]},
    {"Ticker":"COST", "Name":"Costco", "Sector":"Consumer Staples", "Theme":"Consumer Staples", "Tags":["Consumer Staples","Defensive","Quality","Retail"]},
    {"Ticker":"WMT", "Name":"Walmart", "Sector":"Consumer Staples", "Theme":"Consumer Staples", "Tags":["Consumer Staples","Defensive","Dividend","Retail"]},
    {"Ticker":"UNH", "Name":"UnitedHealth", "Sector":"Health Care", "Theme":"Health Care", "Tags":["Healthcare","Defensive","Quality","Insurance"]},
    {"Ticker":"LLY", "Name":"Eli Lilly", "Sector":"Health Care", "Theme":"GLP-1 / Pharma", "Tags":["Healthcare","Pharma","GLP-1","Growth","Quality"]},
    {"Ticker":"NVO", "Name":"Novo Nordisk", "Sector":"Health Care", "Theme":"GLP-1 / Pharma", "Tags":["Healthcare","Pharma","GLP-1","International","Quality"]},
    {"Ticker":"CAT", "Name":"Caterpillar", "Sector":"Industrials", "Theme":"Infrastructure", "Tags":["Industrials","Infrastructure","Commodity","Dividend","Cyclical"]},
    {"Ticker":"DE", "Name":"Deere", "Sector":"Industrials", "Theme":"Agriculture Equipment", "Tags":["Industrials","Agriculture","Equipment","Cyclical"]},
    {"Ticker":"URI", "Name":"United Rentals", "Sector":"Industrials", "Theme":"Infrastructure", "Tags":["Industrials","Infrastructure","Construction","Quality"]},
    {"Ticker":"TSLA", "Name":"Tesla", "Sector":"Consumer Discretionary", "Theme":"EV / Robotics", "Tags":["EV","Robotics & Automation","High Beta","Growth","Momentum"]},
    {"Ticker":"RIVN", "Name":"Rivian", "Sector":"Consumer Discretionary", "Theme":"EV", "Tags":["EV","High Beta","Growth"]},
    {"Ticker":"MSTR", "Name":"MicroStrategy", "Sector":"Information Technology", "Theme":"Bitcoin / Crypto", "Tags":["Bitcoin / Crypto","Bitcoin","High Beta","Momentum"]},
    {"Ticker":"COIN", "Name":"Coinbase", "Sector":"Financials", "Theme":"Bitcoin / Crypto", "Tags":["Bitcoin / Crypto","Crypto","High Beta","Financials"]},
]

STOCK_TAGS = sorted({tag for row in STOCK_CATALOG for tag in row.get("Tags", [])})
STOCK_CATEGORIES = sorted({row.get("Sector", "Other") for row in STOCK_CATALOG})


def search_stock_catalog(query: str = "", selected_tags=None, sectors=None, match_mode: str = "Any") -> pd.DataFrame:
    """Search individual stocks by ticker/name/sector/theme/tags."""
    selected_tags = selected_tags or []
    sectors = sectors or []
    q = (query or "").strip().lower()
    rows = []
    for item in STOCK_CATALOG:
        haystack = " ".join([
            item.get("Ticker", ""), item.get("Name", ""), item.get("Sector", ""),
            item.get("Theme", ""), " ".join(item.get("Tags", []))
        ]).lower()
        if q and q not in haystack:
            continue
        if sectors and item.get("Sector") not in sectors:
            continue
        item_tags = set(item.get("Tags", []))
        if selected_tags:
            wanted = set(selected_tags)
            if match_mode == "All" and not wanted.issubset(item_tags):
                continue
            if match_mode == "Any" and not (wanted & item_tags):
                continue
        tag_score = len(set(selected_tags) & item_tags) if selected_tags else 0
        text_score = 1 if q and q in haystack else 0
        rows.append({
            "Ticker": item.get("Ticker"),
            "Name": item.get("Name"),
            "Sector": item.get("Sector"),
            "Theme": item.get("Theme"),
            "Tags": ", ".join(item.get("Tags", [])),
            "Match Score": tag_score * 10 + text_score,
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["Match Score", "Ticker"], ascending=[False, True])

# Manual map for common individual tickers. yfinance/FMP sector data is still preferred when available.
SECTOR_MAP = {
    "SPY": "Index", "QQQ": "Index", "DIA": "Index", "IWM": "Index",
    "XLK": "Information Technology", "XLV": "Health Care", "XLF": "Financials", "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples", "XLI": "Industrials", "XLE": "Energy", "XLB": "Materials",
    "XLU": "Utilities", "XLRE": "Real Estate", "XLC": "Communication Services",
    "ITA": "Defense / Aerospace", "XAR": "Defense / Aerospace",
    "SMH": "Semiconductors", "SOXX": "Semiconductors",
    "QQQ": "AI / Nasdaq Growth",
    "HACK": "Cybersecurity", "CIBR": "Cybersecurity",
    "URA": "Uranium", "URNM": "Uranium",
    "OIH": "Oil Services", "XOP": "Oil & Gas Exploration",
    "GDX": "Gold Miners", "GDXJ": "Junior Gold Miners",
    "PAVE": "Infrastructure", "IFRA": "Infrastructure",
    "XBI": "Biotech", "IBB": "Biotech",
    "XHB": "Homebuilders", "ITB": "Homebuilders",
    "IYT": "Transportation",
    "KBE": "Banks", "KRE": "Regional Banks",
    "SOXL": "Information Technology", "SOXS": "Information Technology", "SMH": "Information Technology",
    "NVDA": "Information Technology", "AMD": "Information Technology", "INTC": "Information Technology", "AVGO": "Information Technology", "TSM": "Information Technology",
    "AAPL": "Information Technology", "MSFT": "Information Technology", "SHOP": "Information Technology", "SHOP.TO": "Information Technology",
    "GOOGL": "Communication Services", "GOOG": "Communication Services", "META": "Communication Services", "NFLX": "Communication Services",
    "TSLA": "Consumer Discretionary", "AMZN": "Consumer Discretionary", "HD": "Consumer Discretionary",
    "WMT": "Consumer Staples", "COST": "Consumer Staples", "PG": "Consumer Staples", "KO": "Consumer Staples",
    "UNH": "Health Care", "JNJ": "Health Care", "PFE": "Health Care", "LLY": "Health Care",
    "JPM": "Financials", "BAC": "Financials", "GS": "Financials", "RY.TO": "Financials", "TD.TO": "Financials", "BNS.TO": "Financials",
    "CAT": "Industrials", "GE": "Industrials", "BA": "Industrials", "LMT": "Industrials", "RTX": "Industrials", "NOC": "Industrials", "GD": "Industrials",
    "HACK": "Information Technology", "PANW": "Information Technology", "CRWD": "Information Technology", "ZS": "Information Technology",
    "USO": "Energy", "HUC.TO": "Energy", "CNQ.TO": "Energy", "SU.TO": "Energy", "XOM": "Energy", "CVX": "Energy",
    "GLD": "Materials", "GDX": "Materials", "GDXU": "Materials", "KGC": "Materials", "ABX.TO": "Materials", "AEM.TO": "Materials",
    "NEE": "Utilities", "DUK": "Utilities", "SO": "Utilities",
    "PLD": "Real Estate", "AMT": "Real Estate", "O": "Real Estate",
    "BTC-USD": "Crypto", "ETH-USD": "Crypto", "X:BTCUSD": "Crypto", "X:ETHUSD": "Crypto",
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
    news_impact_alert_threshold = st.slider("News impact alert threshold", 40, 100, 75)
    news_confirmation_alert_threshold = st.slider("News + whale confirmation threshold", 40, 100, 70)
    enable_real_alerts = st.toggle("Enable real alerts", value=False, help="Sends webhook messages when fresh high-conviction signals or news catalysts appear.")
    discord_webhook = st.text_input("Discord webhook URL", type="password", help="Optional. Create a Discord channel webhook and paste it here.")
    telegram_bot_token = st.text_input("Telegram bot token", type="password", help="Optional. Use BotFather to create one.")
    telegram_chat_id = st.text_input("Telegram chat ID", help="Optional. Needed with Telegram bot token.")

    st.divider()
    st.subheader("Better Fundamentals")
    fmp_api_key = st.text_input("Financial Modeling Prep API key", type="password", help="Optional. If blank, Hidden Gem Scanner falls back to yfinance fundamentals.")

    st.divider()
    realtime_on = st.toggle("Auto-refresh", value=False)
    refresh_interval = st.selectbox("Refresh every", [30, 60, 120, 300], index=1, disabled=not realtime_on)


# =========================================================
# LOCAL STORAGE, ALERTS, AND PORTFOLIO HELPERS
# =========================================================
APP_DIR = Path.home() / ".institutional_flow_pro"
APP_DIR.mkdir(exist_ok=True)
PORTFOLIO_FILE = APP_DIR / "portfolio_positions.csv"
ALERT_LOG_FILE = APP_DIR / "sent_alerts.json"


def load_alert_log() -> dict:
    try:
        return json.loads(ALERT_LOG_FILE.read_text())
    except Exception:
        return {}


def save_alert_log(log: dict) -> None:
    try:
        ALERT_LOG_FILE.write_text(json.dumps(log, indent=2))
    except Exception:
        pass


def send_discord_alert(webhook_url: str, message: str) -> tuple[bool, str]:
    if not webhook_url:
        return False, "No Discord webhook configured."
    try:
        r = requests.post(webhook_url, json={"content": message}, timeout=10)
        return r.status_code in (200, 204), f"Discord status {r.status_code}"
    except Exception as e:
        return False, str(e)


def send_telegram_alert(bot_token: str, chat_id: str, message: str) -> tuple[bool, str]:
    if not bot_token or not chat_id:
        return False, "No Telegram bot token/chat ID configured."
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        r = requests.post(url, data={"chat_id": chat_id, "text": message}, timeout=10)
        return r.ok, f"Telegram status {r.status_code}"
    except Exception as e:
        return False, str(e)


def maybe_send_signal_alert(ticker: str, scores: dict, regime: str, price: float) -> list[str]:
    """Send one alert per ticker/signal/date to avoid spamming."""
    messages = []
    if not enable_real_alerts:
        return messages
    side = None
    score = None
    if scores["buy"] >= buy_alert_threshold and scores["buy"] > scores["sell"]:
        side, score = "BUY", scores["buy"]
    elif scores["sell"] >= sell_alert_threshold and scores["sell"] > scores["buy"]:
        side, score = "SELL/AVOID", scores["sell"]
    if side is None:
        return messages

    today_key = datetime.now().strftime("%Y-%m-%d")
    key = f"{ticker}:{side}:{today_key}:{int(score)}"
    log = load_alert_log()
    if log.get(key):
        return [f"Alert already sent today for {ticker} {side}."]

    msg = (
        f"🐋 Institutional Flow Alert\n"
        f"Ticker: {ticker}\n"
        f"Signal: {side}\n"
        f"Buy/Sell: {scores['buy']}/{scores['sell']}\n"
        f"Regime: {regime}\n"
        f"Price: {price:,.2f}\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    sent_any = False
    if discord_webhook:
        ok, detail = send_discord_alert(discord_webhook, msg)
        messages.append(("✅" if ok else "❌") + " Discord: " + detail)
        sent_any = sent_any or ok
    if telegram_bot_token and telegram_chat_id:
        ok, detail = send_telegram_alert(telegram_bot_token, telegram_chat_id, msg)
        messages.append(("✅" if ok else "❌") + " Telegram: " + detail)
        sent_any = sent_any or ok
    if sent_any:
        log[key] = True
        save_alert_log(log)
    if not messages:
        messages.append("Real alerts are enabled, but no Discord or Telegram destination is configured.")
    return messages


def maybe_send_news_alert(ticker: str, articles: list[dict], confirmation: dict, scores: dict, price: float) -> list[str]:
    """Send catalyst alerts when high-impact news aligns with whale/flow confirmation.

    One alert per ticker/article/day is logged to avoid duplicate webhook spam.
    """
    messages = []
    if not enable_real_alerts:
        return messages

    high_items = [
        a for a in articles
        if a.get("impact", 0) >= news_impact_alert_threshold
        and a.get("age_hrs", 999) <= 24
    ]
    if confirmation.get("score", 0) < news_confirmation_alert_threshold and not high_items:
        return messages

    if high_items:
        top = sorted(high_items, key=lambda a: (-a.get("impact", 0), a.get("age_hrs", 999)))[0]
    else:
        top = {"title": "News + whale confirmation", "impact": confirmation.get("score", 0), "url": "", "source": "Flow engine", "sentiment": 0}

    today_key = datetime.now().strftime("%Y-%m-%d")
    safe_title = re.sub(r"\W+", "_", top.get("title", "news"))[:80]
    key = f"NEWS:{ticker}:{today_key}:{safe_title}:{int(top.get('impact', 0))}"
    log = load_alert_log()
    if log.get(key):
        return [f"News alert already sent today for {ticker}."]

    sentiment_label = "bullish" if top.get("sentiment", 0) > 0 else "bearish" if top.get("sentiment", 0) < 0 else "neutral"
    msg = (
        f"🚨 News + Flow Alert\n"
        f"Ticker: {ticker}\n"
        f"Headline: {top.get('title', '')}\n"
        f"Source: {top.get('source', '')}\n"
        f"Impact: {top.get('impact', 0)}/100 · Sentiment: {sentiment_label}\n"
        f"Whale confirmation: {confirmation.get('score', 0)}/100 — {confirmation.get('label', '')}\n"
        f"Buy/Sell score: {scores.get('buy', 0)}/{scores.get('sell', 0)}\n"
        f"Price: {price:,.2f}\n"
        f"URL: {top.get('url', '')}\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    sent_any = False
    if discord_webhook:
        ok, detail = send_discord_alert(discord_webhook, msg)
        messages.append(("✅" if ok else "❌") + " Discord: " + detail)
        sent_any = sent_any or ok
    if telegram_bot_token and telegram_chat_id:
        ok, detail = send_telegram_alert(telegram_bot_token, telegram_chat_id, msg)
        messages.append(("✅" if ok else "❌") + " Telegram: " + detail)
        sent_any = sent_any or ok
    if sent_any:
        log[key] = True
        save_alert_log(log)
    if not messages:
        messages.append("Real alerts are enabled, but no Discord or Telegram destination is configured.")
    return messages


def load_portfolio() -> pd.DataFrame:
    cols = ["Ticker", "Quantity", "EntryPrice", "Stop", "Target", "Sector", "Notes"]
    if PORTFOLIO_FILE.exists():
        try:
            dfp = pd.read_csv(PORTFOLIO_FILE)
            for c in cols:
                if c not in dfp.columns:
                    dfp[c] = "" if c in ["Ticker", "Sector", "Notes"] else np.nan
            return dfp[cols]
        except Exception:
            pass
    return pd.DataFrame(columns=cols)


def save_portfolio(dfp: pd.DataFrame) -> None:
    try:
        dfp.to_csv(PORTFOLIO_FILE, index=False)
    except Exception:
        pass


def get_latest_price_fast(ticker: str) -> float:
    px = fetch_yfinance(ticker, "5d", "1d", False)
    if px.empty:
        return np.nan
    return float(px["Close"].dropna().iloc[-1])

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



# =========================================================
# PRECIOUS METALS SMART MONEY / STRESS HELPERS
# =========================================================
METAL_FUTURES = {
    "Gold": {"ticker": "GC=F", "contract_size": 100, "unit": "oz", "color": "#F59E0B"},
    "Silver": {"ticker": "SI=F", "contract_size": 5000, "unit": "oz", "color": "#9CA3AF"},
    "Platinum": {"ticker": "PL=F", "contract_size": 50, "unit": "oz", "color": "#64748B"},
    "Copper": {"ticker": "HG=F", "contract_size": 25000, "unit": "lb", "color": "#B45309"},
}

@st.cache_data(ttl=300)
def scan_metals(period: str = "3mo", interval: str = "1d") -> pd.DataFrame:
    rows = []
    for metal, meta in METAL_FUTURES.items():
        raw = fetch_yfinance(meta["ticker"], period, interval, False)
        if raw.empty or len(raw) < 35:
            continue
        frame = add_indicators(raw)
        if frame.empty or len(frame) < 35:
            continue
        last = frame.iloc[-1]
        prev = frame.iloc[-2]
        ret_20 = (last["Close"] / frame["Close"].iloc[-20] - 1) * 100 if len(frame) >= 20 else np.nan
        whale_20 = int((frame.tail(20)["Whale_Tier"] >= 2).sum())
        accum_20 = int(frame.tail(20)["DarkPool_Accum"].sum())
        dist_20 = int(frame.tail(20)["DarkPool_Dist"].sum())
        obv_20 = frame["OBV"].iloc[-1] - frame["OBV"].iloc[-20] if len(frame) >= 20 else np.nan
        # Smart-money meter: flow + VWAP + whale + momentum, normalized 0-100.
        meter = 50
        meter += 15 if last["Close"] > last["VWAP"] else -15
        meter += 15 if obv_20 > 0 else -15
        meter += min(15, whale_20 * 3)
        meter += 10 if accum_20 > dist_20 else -10 if dist_20 > accum_20 else 0
        meter += 10 if last["MACD"] > last["Signal"] else -10
        meter += 5 if 40 <= last["RSI"] <= 70 else -5 if last["RSI"] > 75 else 0
        meter = int(max(0, min(100, meter)))
        if meter >= 65:
            signal = "🟢 More buying than selling"
        elif meter <= 35:
            signal = "🔴 More selling than buying"
        else:
            signal = "⚖️ Balanced / unclear"
        rows.append({
            "Metal": metal,
            "Ticker": meta["ticker"],
            "Price": float(last["Close"]),
            "1-Bar Change %": float((last["Close"] / prev["Close"] - 1) * 100),
            "20-Bar Return %": float(ret_20),
            "RSI": float(last["RSI"]),
            "Smart Money Meter": meter,
            "Signal": signal,
            "Whale Bars 20": whale_20,
            "Accum Signals 20": accum_20,
            "Dist Signals 20": dist_20,
            "Above VWAP": bool(last["Close"] > last["VWAP"]),
            "OBV 20-Bar Direction": "Up" if obv_20 > 0 else "Down",
            "Contract Size": meta["contract_size"],
            "Unit": meta["unit"],
        })
    return pd.DataFrame(rows).sort_values("Smart Money Meter", ascending=False) if rows else pd.DataFrame()

def metal_meter_figure(value: int, title: str):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        title={"text": title},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "#111827"},
            "steps": [
                {"range": [0, 35], "color": "#FCA5A5"},
                {"range": [35, 65], "color": "#FDE68A"},
                {"range": [65, 100], "color": "#86EFAC"},
            ],
            "threshold": {"line": {"color": "#111827", "width": 4}, "thickness": 0.75, "value": value},
        },
    ))
    fig.update_layout(height=260, margin=dict(l=20, r=20, t=60, b=10))
    return fig

def calculate_comex_stress(open_interest_contracts: float, registered_units: float, contract_size: float,
                           delivery_notices: float = 0.0, daily_withdrawal_units: float = 0.0) -> dict:
    paper_claim_units = max(0.0, open_interest_contracts) * contract_size
    leverage = paper_claim_units / registered_units if registered_units and registered_units > 0 else np.nan
    delivery_coverage = registered_units / paper_claim_units * 100 if paper_claim_units > 0 and registered_units > 0 else np.nan
    notice_coverage = registered_units / (delivery_notices * contract_size) * 100 if delivery_notices and delivery_notices > 0 and registered_units > 0 else np.nan
    depletion_days = registered_units / daily_withdrawal_units if daily_withdrawal_units and daily_withdrawal_units > 0 else np.nan
    stress = 0
    if not np.isnan(leverage):
        stress += min(40, leverage * 4)
    if not np.isnan(delivery_coverage):
        stress += max(0, min(30, (25 - delivery_coverage) * 1.5)) if delivery_coverage < 25 else 0
    if not np.isnan(depletion_days):
        stress += max(0, min(30, (180 - depletion_days) / 6)) if depletion_days < 180 else 0
    return {
        "paper_claim_units": paper_claim_units,
        "paper_leverage": leverage,
        "delivery_coverage_pct": delivery_coverage,
        "notice_coverage_pct": notice_coverage,
        "depletion_days": depletion_days,
        "stress_score": int(max(0, min(100, stress))) if not np.isnan(stress) else 0,
    }

# =========================================================
# SECTOR/THEME ROTATION HELPERS — FULL 11 GICS SECTORS + THEMES
# =========================================================

def classify_sector_extreme_signal(rsi: float, close: float, vwap: float, obv_lookback: float,
                                   rel_strength: float, accum_count: int, dist_count: int,
                                   whale_count: int) -> tuple[str, str, int]:
    """Classify oversold/overbought sectors into actionable rotation buckets.

    The goal is not to buy every oversold sector. It separates:
    - oversold + improving flow = possible next inflow
    - oversold + weak flow = avoid / falling knife
    - overbought + strong flow = momentum continuation
    - overbought + weakening flow = distribution risk
    """
    above_vwap = close >= vwap
    obv_up = obv_lookback > 0
    rel_up = rel_strength > 0
    accum_edge = accum_count > dist_count
    dist_edge = dist_count > accum_count
    active_whales = whale_count >= 1

    if pd.isna(rsi):
        return "⚪ No RSI data", "Wait", 0

    # Oversold sectors: only bullish if flow is improving.
    if rsi <= 35:
        if obv_up and (above_vwap or accum_edge or rel_up):
            bonus = 18 + (5 if active_whales else 0) + (5 if rel_up else 0)
            return "🟢 Oversold accumulation", "Possible next inflow", bonus
        return "🔴 Oversold weakness", "Avoid / still outflow", -18

    # Early turn before full confirmation.
    if 35 < rsi <= 45:
        if obv_up and (rel_up or accum_edge):
            bonus = 10 + (4 if active_whales else 0)
            return "🟡 Early rotation watch", "Watch for inflow", bonus
        if not obv_up and not above_vwap:
            return "🔴 Weak bounce risk", "Avoid / weak bounce", -8
        return "⚪ Neutral oversold recovery", "Wait", 0

    # Overbought sectors: can keep running, but distribution risk matters.
    if rsi >= 70:
        if (not obv_up) or dist_edge or not above_vwap:
            penalty = -16 - (4 if dist_edge else 0)
            return "🔴 Overbought distribution", "Possible next outflow", penalty
        if obv_up and above_vwap and rel_up:
            bonus = 8 + (4 if active_whales else 0)
            return "🟢 Overbought momentum", "Momentum still inflowing", bonus
        return "🟠 Overbought caution", "Do not chase", -5

    # Late-cycle caution: high RSI but flow weakens.
    if 60 <= rsi < 70:
        if (not obv_up) and (dist_edge or not above_vwap):
            return "🟠 Late-cycle caution", "Possible rotation out", -8
        if obv_up and rel_up:
            return "🟢 Healthy momentum", "Inflow continuing", 6

    # Normal regime.
    if obv_up and rel_up and above_vwap:
        return "🟢 Healthy inflow", "Inflow continuing", 5
    if (not obv_up) and (not above_vwap):
        return "🔴 Weak flow", "Outflow risk", -5
    return "⚪ Neutral", "Wait", 0

@st.cache_data(ttl=300)
def scan_sector_rotation(period: str = "3mo", interval: str = "1d") -> pd.DataFrame:
    """Scan the 11 GICS sector ETFs plus thematic ETF proxies and rank inflow/outflow.

    Adds oversold/overbought rotation signals to help identify where money may flow next.
    """
    rows = []

    benchmark = fetch_yfinance("SPY", period, interval, extended=False)
    benchmark_close = benchmark["Close"].copy() if not benchmark.empty else pd.Series(dtype=float)

    for sector_name, etf in ROTATION_ETFS.items():
        raw = fetch_yfinance(etf, period, interval, extended=False)
        if raw.empty or len(raw) < 30:
            continue
        frame = add_indicators(raw)
        scores = compute_scores(frame)
        last = frame.iloc[-1]
        lookback = min(20, len(frame) - 1)
        perf_lookback = (last["Close"] / frame["Close"].iloc[-lookback] - 1) * 100 if lookback > 1 else np.nan

        # Relative strength vs SPY over the same lookback.
        spy_perf = 0.0
        rel_strength = 0.0
        if not benchmark_close.empty:
            joined = pd.concat([frame["Close"].rename("SectorClose"), benchmark_close.rename("SPYClose")], axis=1).dropna()
            if len(joined) > lookback:
                sector_perf_joined = (joined["SectorClose"].iloc[-1] / joined["SectorClose"].iloc[-lookback] - 1) * 100
                spy_perf = (joined["SPYClose"].iloc[-1] / joined["SPYClose"].iloc[-lookback] - 1) * 100
                rel_strength = sector_perf_joined - spy_perf

        obv_lookback = frame["OBV"].diff().tail(lookback).sum()
        whale_count = int((frame["Whale_Tier"].tail(20) >= 2).sum())
        accum_count = int(frame["Smart_Accum"].tail(20).sum() + frame["DarkPool_Accum"].tail(20).sum())
        dist_count = int(frame["Smart_Dist"].tail(20).sum() + frame["DarkPool_Dist"].tail(20).sum())
        net_flow = scores["buy"] - scores["sell"]

        extreme_signal, money_flow_next, extreme_modifier = classify_sector_extreme_signal(
            float(last["RSI"]), float(last["Close"]), float(last["VWAP"]), float(obv_lookback),
            float(rel_strength), accum_count, dist_count, whale_count
        )

        # Rotation score mixes current signal, price trend, relative strength, OBV direction,
        # accumulation clusters, and oversold/overbought confirmation.
        rotation_score = (
            net_flow * 0.40
            + np.clip(perf_lookback, -20, 20) * 0.90
            + np.clip(rel_strength, -20, 20) * 1.35
            + (10 if obv_lookback > 0 else -10)
            + (accum_count - dist_count) * 3
            + whale_count * 1.5
            + extreme_modifier
        )
        rows.append({
            "Sector": sector_name,
            "Type": "GICS Sector" if sector_name in GICS_SECTOR_ETFS else "Theme",
            "ETF": etf,
            "Price": float(last["Close"]),
            "RSI": round(float(last["RSI"]), 1),
            "Extreme Signal": extreme_signal,
            "Money Flow Next": money_flow_next,
            "BuyScore": scores["buy"],
            "SellScore": scores["sell"],
            "NetFlow": net_flow,
            "RotationScore": round(float(rotation_score), 1),
            "20-Bar Return %": round(float(perf_lookback), 2),
            "Rel Strength vs SPY %": round(float(rel_strength), 2),
            "SPY 20-Bar Return %": round(float(spy_perf), 2),
            "OBV Direction": "Rising" if obv_lookback > 0 else "Falling",
            "Whale Bars 20": whale_count,
            "Accum Signals 20": accum_count,
            "Dist Signals 20": dist_count,
            "Regime": classify_regime(frame),
        })
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows).sort_values("RotationScore", ascending=False).reset_index(drop=True)
    out["Rank"] = np.arange(1, len(out) + 1)
    return out


@st.cache_data(ttl=300)
def build_sector_rotation_timeline(period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    """Create a sector rotation timeline using rolling 20-bar relative returns vs SPY."""
    if not YF_AVAILABLE:
        return pd.DataFrame()
    benchmark = fetch_yfinance("SPY", period, interval, extended=False)
    if benchmark.empty:
        return pd.DataFrame()
    bench_close = benchmark["Close"].copy()
    rows = []
    for sector_name, etf in ROTATION_ETFS.items():
        raw = fetch_yfinance(etf, period, interval, extended=False)
        if raw.empty:
            continue
        joined = pd.concat([raw["Close"].rename("SectorClose"), bench_close.rename("SPYClose")], axis=1).dropna()
        if len(joined) < 30:
            continue
        sector_ret = joined["SectorClose"].pct_change(20) * 100
        spy_ret = joined["SPYClose"].pct_change(20) * 100
        rel_strength = sector_ret - spy_ret
        tmp = pd.DataFrame({"Date": joined.index, "Sector": sector_name, "Type": "GICS Sector" if sector_name in GICS_SECTOR_ETFS else "Theme", "ETF": etf, "RelativeStrength": rel_strength.values})
        rows.append(tmp.dropna())
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def sector_leaders_text(sector_df: pd.DataFrame) -> tuple[str, str]:
    """Return readable top inflow and outflow sector summaries."""
    if sector_df.empty:
        return "—", "—"
    top_in = sector_df.sort_values("RotationScore", ascending=False).head(3)
    top_out = sector_df.sort_values("RotationScore", ascending=True).head(3)
    inflow = ", ".join([f"{r.Sector} ({r.ETF}, {r.RotationScore:+.1f})" for r in top_in.itertuples()])
    outflow = ", ".join([f"{r.Sector} ({r.ETF}, {r.RotationScore:+.1f})" for r in top_out.itertuples()])
    return inflow, outflow

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
# NEWS + PRESS RELEASE IMPACT ENGINE
# =========================================================
PRESS_RELEASE_WORDS = [
    "announces", "reports", "declares", "launches", "introduces", "agreement",
    "contract", "award", "acquisition", "merger", "partnership", "collaboration",
    "earnings", "results", "guidance", "approval", "fda", "trial", "phase",
    "offering", "dividend", "buyback", "repurchase", "appoints", "expands"
]

HIGH_IMPACT_WORDS = [
    "earnings", "guidance", "raises guidance", "cuts guidance", "acquisition", "merger",
    "contract", "deal", "partnership", "approval", "fda", "lawsuit", "investigation",
    "sec", "doj", "recall", "bankruptcy", "offering", "buyback", "dividend",
    "strategic review", "restructuring", "layoff", "cyberattack", "breach", "government contract"
]

PRESS_SOURCE_HINTS = [
    "pr newswire", "business wire", "globenewswire", "accesswire", "newsfile",
    "ein presswire", "issuer direct", "company news", "press release"
]

def score_headline(text: str) -> int:
    """Transparent phrase-first headline sentiment score.

    Phrase detection avoids common false positives such as "falls despite strong earnings".
    The score is intentionally simple and auditable; positive = bullish, negative = bearish.
    """
    t = text.lower()
    score = 0

    positive_patterns = [
        r"shares?\s+(surge|soar|rally|jump|gain|rise|rebound)",
        r"(beat|beats|exceed|exceeds|tops).*expectations?",
        r"raises?\s+(guidance|outlook|forecast)",
        r"(wins?|awarded|secures?)\s+.*(contract|deal|order)",
        r"(fda|regulatory)\s+(approval|clears?|clearance)",
        r"(buyback|repurchase|strategic investment|acquisition offer)",
    ]
    negative_patterns = [
        r"shares?\s+(plunge|crash|tank|drop|fall|slump|slide)",
        r"(miss|misses|below).*expectations?",
        r"cuts?\s+(guidance|outlook|forecast)",
        r"(lawsuit|investigation|probe|sec charges|doj)",
        r"(bankruptcy|going concern|delisting|halted)",
        r"(offering|dilution|secondary offering)",
    ]

    for pat in positive_patterns:
        if re.search(pat, t):
            score += 2
    for pat in negative_patterns:
        if re.search(pat, t):
            score -= 2

    # Low-weight fallback words.
    score += sum(1 for w in BULLISH_WORDS if re.search(r"\b" + re.escape(w) + r"\b", t))
    score -= sum(1 for w in BEARISH_WORDS if re.search(r"\b" + re.escape(w) + r"\b", t))
    return int(max(-5, min(5, score)))

def is_press_release(title: str, source: str = "") -> bool:
    """Detect official company/PR-style announcements by source and title patterns."""
    t = f"{title} {source}".lower()
    if any(s in t for s in PRESS_SOURCE_HINTS):
        return True
    pr_patterns = [
        r"reports?\s+(q\d|fiscal|annual|quarter|results)",
        r"announces?\s+",
        r"declares?\s+",
        r"appoints?|names?\s+.*(ceo|cfo|president|director)",
        r"(acquires?|acquisition|merger|definitive agreement)",
        r"(partnership|collaboration|agreement)\s+with",
        r"(launches?|introduces?|unveils?)",
        r"(contract|award|order)\s+(from|with|worth|valued)",
    ]
    return any(re.search(p, t) for p in pr_patterns) or any(w in t for w in PRESS_RELEASE_WORDS)

def is_high_impact_news(title: str) -> bool:
    t = title.lower()
    return any(w in t for w in HIGH_IMPACT_WORDS)

def ticker_relevance(title: str, ticker: str) -> bool:
    """Keep broad feeds from becoming noisy. We allow a few non-exact results from Google/Yahoo, but prefer exact ticker/name matches."""
    clean = re.sub(r"^[A-Z]+:", "", ticker.upper()).replace("-USD", "").replace(".TO", "")
    title_up = title.upper()
    if clean and (clean in title_up or f"({clean})" in title_up or f" {clean} " in f" {title_up} "):
        return True
    return False

def compute_news_impact_score(article: dict) -> int:
    """0-100 score based on source type, impact keywords, sentiment strength, and freshness."""
    title = article.get("title", "")
    age = float(article.get("age_hrs", 999))
    sentiment = int(article.get("sentiment", 0))
    score = 0

    if article.get("is_press"):
        score += 25
    if article.get("is_high_impact"):
        score += 30
    if abs(sentiment) >= 2:
        score += 15
    elif abs(sentiment) == 1:
        score += 8

    if age <= 6:
        score += 20
    elif age <= 24:
        score += 12
    elif age <= 72:
        score += 5

    # Official/press-release sources usually matter more than recycled headlines.
    src = article.get("source", "").lower()
    if any(s in src for s in PRESS_SOURCE_HINTS) or "benzinga" in src:
        score += 10

    return int(max(0, min(score, 100)))

@st.cache_data(ttl=900)
def fetch_news(ticker: str, max_age_days: int = 30, include_unknown_dates: bool = False) -> list[dict]:
    """
    Fetch recent RSS headlines from market news + press-release sources.
    Sources are best-effort free RSS endpoints; paid APIs will be more complete.
    """
    if not FEEDPARSER_AVAILABLE:
        return []

    clean = re.sub(r"^[A-Z]+:", "", ticker.upper()).replace("-", " ")
    exact = re.sub(r"^[A-Z]+:", "", ticker.upper())

    feeds = [
        # Ticker-specific / market headlines
        ("Yahoo Finance", f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US", True),
        ("Google News", f"https://news.google.com/rss/search?q={clean}+stock+OR+{clean}+earnings+OR+{clean}+press+release&hl=en-US&gl=US&ceid=US:en", True),
        ("Seeking Alpha", f"https://seekingalpha.com/api/sa/combined/{ticker}.xml", True),
        ("Benzinga", "https://www.benzinga.com/feed", False),

        # Press-release sources / official company announcements
        ("PR Newswire", "https://www.prnewswire.com/rss/news-releases-list.rss", False),
        ("PR Newswire Financial", "https://www.prnewswire.com/rss/financial-services-latest-news/financial-services-latest-news-list.rss", False),
        ("PR Newswire via Google", f"https://news.google.com/rss/search?q={clean}+site:prnewswire.com&hl=en-US&gl=US&ceid=US:en", True),
        ("Business Wire", "https://feed.businesswire.com/rss/home/?rss=G1QFDERJXkJeGVtQWA==", False),
        ("Business Wire via Google", f"https://news.google.com/rss/search?q={clean}+site:businesswire.com&hl=en-US&gl=US&ceid=US:en", True),
        ("GlobeNewswire", "https://www.globenewswire.com/RssFeed/orgclass/1/feedTitle/GlobeNewswire%20-%20News%20about%20Public%20Companies", False),
        ("GlobeNewswire via Google", f"https://news.google.com/rss/search?q={clean}+site:globenewswire.com&hl=en-US&gl=US&ceid=US:en", True),
        ("Accesswire", "https://www.accesswire.com/rss/newsroom", False),
        ("Accesswire via Google", f"https://news.google.com/rss/search?q={clean}+site:accesswire.com&hl=en-US&gl=US&ceid=US:en", True),
        ("Newsfile", "https://www.newsfilecorp.com/rss/news-releases", False),
        ("Newsfile via Google", f"https://news.google.com/rss/search?q={clean}+site:newsfilecorp.com&hl=en-US&gl=US&ceid=US:en", True),
        ("EIN Presswire", "https://www.einpresswire.com/rss/financial-news", False),
        ("MarketWatch", "https://www.marketwatch.com/rss/realtimeheadlines", False),
    ]

    articles, seen = [], set()
    for source_name, url, ticker_specific in feeds:
        try:
            feed = feedparser.parse(url)
            feed_source = feed.feed.get("title", source_name) or source_name
            for entry in feed.entries[:25]:
                title = entry.get("title", "").strip()
                if not title:
                    continue
                key = re.sub(r"\s+", " ", title.lower())
                if key in seen:
                    continue

                # Broad feeds must match the ticker symbol. Ticker-specific feeds can pass through.
                if not ticker_specific and not ticker_relevance(title, exact):
                    continue

                seen.add(key)
                pub = entry.get("published", entry.get("updated", ""))
                try:
                    pub_dt = pd.to_datetime(pub, utc=True)
                    age_hrs = (datetime.utcnow() - pub_dt.replace(tzinfo=None)).total_seconds() / 3600
                    pub_str = pub_dt.strftime("%Y-%m-%d %H:%M UTC")
                except Exception:
                    age_hrs = 999
                    pub_str = pub[:24] if pub else "—"

                # User-controlled freshness filter. This prevents old items (for example Q3 2025)
                # from affecting today's news/whale confirmation score.
                if age_hrs == 999 and not include_unknown_dates:
                    continue
                if age_hrs != 999 and age_hrs > max_age_days * 24:
                    continue

                article = {
                    "title": title,
                    "url": entry.get("link", "#"),
                    # Keep the configured source label visible, so PR Newswire / Business Wire / etc.
                    # are clear even when feeds expose a generic title.
                    "source": source_name,
                    "published": pub_str,
                    "sentiment": score_headline(title),
                    "age_hrs": age_hrs,
                    "is_press": is_press_release(title, feed_source),
                    "is_high_impact": is_high_impact_news(title),
                }
                article["impact"] = compute_news_impact_score(article)
                articles.append(article)
        except Exception:
            continue

    # Sort high-impact recent items first, then recency.
    return sorted(articles, key=lambda x: (-x.get("impact", 0), x.get("age_hrs", 999)))[:40]

def news_momentum(articles: list[dict]) -> dict:
    if not articles:
        return {"score": 0, "impact": 0, "label": "No data", "bullish": 0, "bearish": 0, "neutral": 0, "press": 0, "high_impact": 0, "total": 0}
    scores = [a.get("sentiment", 0) for a in articles]
    impacts = [a.get("impact", 0) for a in articles]
    avg = sum(scores) / len(scores)
    avg_impact = sum(impacts) / len(impacts)
    if avg >= 0.75:
        label = "📈 Bullish"
    elif avg <= -0.75:
        label = "📉 Bearish"
    else:
        label = "➡️ Neutral"
    return {
        "score": round(avg, 2),
        "impact": round(avg_impact, 1),
        "label": label,
        "bullish": int(sum(s > 0 for s in scores)),
        "bearish": int(sum(s < 0 for s in scores)),
        "neutral": int(sum(s == 0 for s in scores)),
        "press": int(sum(a.get("is_press", False) for a in articles)),
        "high_impact": int(sum(a.get("is_high_impact", False) for a in articles)),
        "total": len(scores),
    }

def whale_news_confirmation(articles: list[dict], frame: pd.DataFrame) -> dict:
    """Combine recent news impact with the latest whale/flow context."""
    recent_news = [a for a in articles if a.get("age_hrs", 999) <= 72 and a.get("impact", 0) >= 45]
    if frame is None or frame.empty:
        return {"label": "No market data", "score": 0, "details": []}
    last = frame.iloc[-1]
    recent_flow = frame.tail(5)
    details = []
    score = 0

    if recent_news:
        score += min(35, max(a.get("impact", 0) for a in recent_news) * 0.35)
        details.append(f"{len(recent_news)} high-impact headline(s) in last 72h")
    if bool((recent_flow.get("Whale_Tier", pd.Series(dtype=float)) >= 2).any()):
        score += 20
        details.append("Recent whale-volume bar")
    if float(recent_flow.get("Whale_Cluster", pd.Series([0])).max()) >= 2:
        score += 15
        details.append("Whale cluster active")
    if bool(last.get("Close", np.nan) > last.get("VWAP", np.inf)):
        score += 10
        details.append("Price above VWAP")
    if bool(last.get("OBV_Slope", 0) > 0):
        score += 10
        details.append("OBV rising")
    if bool(last.get("DarkPool_Accum", False) or last.get("Smart_Accum", False)):
        score += 10
        details.append("Accumulation proxy active")

    score = int(min(100, round(score)))
    if score >= 75:
        label = "🚀 News + Whale Confirmation"
    elif score >= 55:
        label = "🟢 Watch: news supported by flow"
    elif recent_news:
        label = "🟡 News present, flow not confirmed yet"
    else:
        label = "⚪ No high-impact news/flow confirmation"
    return {"label": label, "score": score, "details": details}


# =========================================================
# CATALYST / EARNINGS CALENDAR
# =========================================================
def _safe_date(value):
    try:
        if isinstance(value, (list, tuple, pd.Series, np.ndarray)):
            value = value[0] if len(value) else None
        if isinstance(value, pd.DataFrame):
            return None
        dt = pd.to_datetime(value, errors="coerce")
        if pd.isna(dt):
            return None
        if getattr(dt, "tzinfo", None) is not None:
            dt = dt.tz_convert(None) if hasattr(dt, "tz_convert") else dt.tz_localize(None)
        return dt.to_pydatetime() if hasattr(dt, "to_pydatetime") else dt
    except Exception:
        return None

def fetch_yf_calendar_single(ticker: str) -> list[dict]:
    """Best-effort upcoming catalyst calendar using free yfinance fields.

    Availability varies heavily by ticker. Paid calendar APIs are more reliable.
    """
    if not YF_AVAILABLE:
        return []
    events = []
    try:
        tk = yf.Ticker(ticker)
        cal = None
        try:
            cal = tk.calendar
        except Exception:
            cal = None

        if isinstance(cal, pd.DataFrame) and not cal.empty:
            # yfinance sometimes returns fields as index rows.
            for field in cal.index:
                val = cal.loc[field].dropna().iloc[0] if len(cal.loc[field].dropna()) else None
                dt = _safe_date(val)
                if dt:
                    events.append({"Ticker": ticker, "Event": str(field), "Date": dt.date(), "Source": "yfinance calendar"})
        elif isinstance(cal, dict):
            for field, val in cal.items():
                dt = _safe_date(val)
                if dt:
                    events.append({"Ticker": ticker, "Event": str(field), "Date": dt.date(), "Source": "yfinance calendar"})

        # Earnings dates endpoint, when available.
        try:
            ed = tk.get_earnings_dates(limit=8)
            if ed is not None and not ed.empty:
                for idx, row in ed.iterrows():
                    dt = _safe_date(idx)
                    if dt:
                        eps_est = row.get("EPS Estimate", np.nan) if hasattr(row, "get") else np.nan
                        events.append({
                            "Ticker": ticker,
                            "Event": "Earnings",
                            "Date": dt.date(),
                            "Source": "yfinance earnings",
                            "EPS Estimate": eps_est,
                        })
        except Exception:
            pass

        # Upcoming dividends from actions are usually historical, but keep future rows if present.
        try:
            actions = tk.actions
            if actions is not None and not actions.empty and "Dividends" in actions.columns:
                today = datetime.now().date()
                future = actions[actions.index.date >= today]
                for idx, row in future.tail(5).iterrows():
                    div = row.get("Dividends", 0)
                    if div and div > 0:
                        events.append({"Ticker": ticker, "Event": f"Dividend {div:g}", "Date": idx.date(), "Source": "yfinance actions"})
        except Exception:
            pass
    except Exception:
        pass
    return events

@st.cache_data(ttl=3600)
def fetch_catalyst_calendar(tickers: list[str], lookahead_days: int = 45) -> pd.DataFrame:
    rows = []
    today = datetime.now().date()
    end = today + timedelta(days=lookahead_days)
    for tk in tickers:
        tk = tk.strip().upper()
        if not tk:
            continue
        for ev in fetch_yf_calendar_single(tk):
            d = ev.get("Date")
            if d and today <= d <= end:
                ev["Days Away"] = (d - today).days
                rows.append(ev)
    if not rows:
        return pd.DataFrame(columns=["Ticker", "Event", "Date", "Days Away", "Source", "EPS Estimate"])
    out = pd.DataFrame(rows)
    # Deduplicate noisy duplicate yfinance rows.
    out = out.drop_duplicates(subset=["Ticker", "Event", "Date"]).sort_values(["Days Away", "Ticker", "Event"])
    return out


def catalyst_alert_message(ticker: str, calendar_df: pd.DataFrame, confirmation: dict, scores: dict) -> str | None:
    if calendar_df is None or calendar_df.empty:
        return None
    near = calendar_df[(calendar_df["Ticker"].str.upper() == ticker.upper()) & (calendar_df["Days Away"] <= 3)]
    if near.empty:
        return None
    ev = near.iloc[0]
    return (
        f"📅 Catalyst Watch\n"
        f"Ticker: {ticker}\n"
        f"Upcoming: {ev['Event']} on {ev['Date']} ({int(ev['Days Away'])} day(s))\n"
        f"Whale/news confirmation: {confirmation.get('score', 0)}/100\n"
        f"Buy/Sell score: {scores.get('buy', 0)}/{scores.get('sell', 0)}"
    )


# =========================================================
# GOAT-STYLE QUALITY SCORE AND ETF DISCOVERY HELPERS
# =========================================================
def pct_or_nan(x):
    try:
        if x is None or pd.isna(x):
            return np.nan
        return float(x) * 100 if abs(float(x)) <= 1 else float(x)
    except Exception:
        return np.nan


def letter_grade(score: float) -> str:
    if pd.isna(score): return "—"
    if score >= 90: return "A+"
    if score >= 82: return "A"
    if score >= 75: return "B+"
    if score >= 68: return "B"
    if score >= 60: return "C+"
    if score >= 50: return "C"
    return "D"


def goat_badge(score: int) -> str:
    if score >= 80: return "🟢 Excellent"
    if score >= 70: return "🟢 Strong"
    if score >= 60: return "🟡 Cautiously optimistic"
    if score >= 50: return "🟠 Mixed"
    return "🔴 Weak / risky"


def score_goat_quality(fund: dict) -> dict:
    """Simple GOAT-style 0-100 quality score: profit + cash + stability."""
    fcf = fund.get("FCF", np.nan)
    fcf_prev = fund.get("FCF_Prev", np.nan)
    ocf = fund.get("OCF", np.nan)
    revenue = fund.get("Revenue", np.nan)
    revenue_prev = fund.get("Revenue_Prev", np.nan)
    op = fund.get("OperatingIncome", np.nan)
    op_prev = fund.get("OperatingIncome_Prev", np.nan)
    debt = fund.get("Debt", np.nan)
    debt_prev = fund.get("Debt_Prev", np.nan)
    cash = fund.get("Cash", np.nan)
    market_cap = fund.get("MarketCap", np.nan)

    fcf_growth = safe_growth(fcf, fcf_prev)
    rev_growth = safe_growth(revenue, revenue_prev)
    op_growth = safe_growth(op, op_prev)
    debt_change = safe_growth(debt, debt_prev)
    fcf_yield = fcf / market_cap * 100 if pd.notna(market_cap) and market_cap > 0 and pd.notna(fcf) else np.nan
    net_cash_ratio = (cash - debt) / market_cap * 100 if pd.notna(cash) and pd.notna(debt) and pd.notna(market_cap) and market_cap > 0 else np.nan

    profit = 0
    if pd.notna(op) and op > 0: profit += 25
    if pd.notna(op_growth):
        if op_growth > 20: profit += 20
        elif op_growth > 10: profit += 15
        elif op_growth > 0: profit += 8
    if pd.notna(rev_growth):
        if rev_growth > 15: profit += 15
        elif rev_growth > 5: profit += 10
        elif rev_growth > 0: profit += 5
    profit = min(100, int(profit * 100 / 60))

    cash_score = 0
    if pd.notna(fcf) and fcf > 0: cash_score += 35
    if pd.notna(fcf_growth):
        if fcf_growth > 25: cash_score += 25
        elif fcf_growth > 10: cash_score += 18
        elif fcf_growth > 0: cash_score += 10
    if pd.notna(fcf_yield):
        if fcf_yield > 8: cash_score += 20
        elif fcf_yield > 4: cash_score += 12
        elif fcf_yield > 1: cash_score += 6
    if pd.notna(ocf) and ocf > 0: cash_score += 10
    cash_score = min(100, int(cash_score))

    stable = 0
    if pd.notna(debt_change) and debt_change <= 0: stable += 25
    if pd.notna(net_cash_ratio):
        if net_cash_ratio > 0: stable += 20
        elif net_cash_ratio > -10: stable += 10
    if pd.notna(rev_growth) and rev_growth > 0: stable += 15
    if pd.notna(fcf) and fcf > 0: stable += 15
    beta = fund.get("Beta", np.nan)
    if pd.notna(beta):
        if beta < 1.1: stable += 15
        elif beta < 1.5: stable += 8
    stable = min(100, int(stable))

    total = int(round(0.35 * profit + 0.40 * cash_score + 0.25 * stable))
    return {
        "GOATScore": total,
        "ProfitScore": profit,
        "CashScore": cash_score,
        "StableScore": stable,
        "ProfitGrade": letter_grade(profit),
        "CashGrade": letter_grade(cash_score),
        "StableGrade": letter_grade(stable),
        "FCFGrowth%": fcf_growth,
        "RevenueGrowth%": rev_growth,
        "DebtChange%": debt_change,
        "FCFYield%": fcf_yield,
        "NetCash%MktCap": net_cash_ratio,
        "Verdict": goat_badge(total),
    }


@st.cache_data(ttl=3600)
def scan_goat_quality(tickers: tuple[str, ...]) -> pd.DataFrame:
    rows = []
    for t in tickers:
        fund = fetch_fundamentals(t, fmp_api_key)
        if not fund:
            continue
        q = score_goat_quality(fund)
        rows.append({
            "Ticker": t,
            "Company": fund.get("Name", t),
            "Sector": fund.get("Sector", SECTOR_MAP.get(t, "Other")),
            "GOAT": q["GOATScore"],
            "Rating": q["Verdict"],
            "Profit": q["ProfitGrade"],
            "Cash": q["CashGrade"],
            "Stable": q["StableGrade"],
            "ProfitScore": q["ProfitScore"],
            "CashScore": q["CashScore"],
            "StableScore": q["StableScore"],
            "FCF Growth %": q["FCFGrowth%"],
            "Revenue Growth %": q["RevenueGrowth%"],
            "FCF Yield %": q["FCFYield%"],
            "Debt Change %": q["DebtChange%"],
            "Source": fund.get("FundamentalSource", "yfinance"),
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("GOAT", ascending=False)


def etf_fee_saver_table(holdings: str, investment_amount: float) -> pd.DataFrame:
    tickers = [x.strip().upper() for x in re.split(r"[,\n]+", holdings) if x.strip()]
    rows = []
    for t in tickers:
        er = ETF_EXPENSES.get(t, np.nan)
        candidates = []
        # Very simple same-index/theme cheaper alternatives.
        if t in ["SPY"]: candidates = ["VOO", "IVV"]
        elif t in ["QQQ"]: candidates = ["QQQM"]
        elif t in ["GDXJ"]: candidates = ["GDX"]
        elif t in ["URA", "URNM"]: candidates = ["URA"]
        else:
            # compare within theme groups
            for group in ETF_DISCOVERY_THEMES.values():
                for _, vals in group.items():
                    if t in vals:
                        candidates = vals
                        break
                if candidates: break
        cheapest = None
        cheapest_er = np.nan
        for c in candidates:
            c_er = ETF_EXPENSES.get(c, np.nan)
            if pd.notna(c_er) and (pd.isna(cheapest_er) or c_er < cheapest_er):
                cheapest, cheapest_er = c, c_er
        save = np.nan
        if pd.notna(er) and pd.notna(cheapest_er) and cheapest != t:
            save = investment_amount * (er - cheapest_er) / 100
        rows.append({"ETF": t, "Expense %": er, "Cheaper Alternative": cheapest or "—", "Alt Expense %": cheapest_er, "Est. Annual Savings": save})
    return pd.DataFrame(rows)


def etf_hall_of_shame() -> pd.DataFrame:
    rows = [{"ETF": k, "Expense %": v} for k, v in ETF_EXPENSES.items()]
    return pd.DataFrame(rows).sort_values("Expense %", ascending=False).head(15)

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


@st.cache_data(ttl=3600)
def fetch_fundamentals_fmp(ticker: str, key: str) -> dict:
    """Better fundamentals via Financial Modeling Prep. Falls back silently if unavailable."""
    if not key:
        return {}
    try:
        base = "https://financialmodelingprep.com/api/v3"
        symbol = ticker.replace(".TO", ".TO")
        profile = requests.get(f"{base}/profile/{symbol}?apikey={key}", timeout=12).json()
        ratios = requests.get(f"{base}/ratios-ttm/{symbol}?apikey={key}", timeout=12).json()
        cash = requests.get(f"{base}/cash-flow-statement/{symbol}?limit=2&apikey={key}", timeout=12).json()
        income = requests.get(f"{base}/income-statement/{symbol}?limit=2&apikey={key}", timeout=12).json()
        balance = requests.get(f"{base}/balance-sheet-statement/{symbol}?limit=2&apikey={key}", timeout=12).json()
        if isinstance(profile, dict) and profile.get("Error Message"):
            return {}
        prof = profile[0] if isinstance(profile, list) and profile else {}
        rat = ratios[0] if isinstance(ratios, list) and ratios else {}
        cf0 = cash[0] if isinstance(cash, list) and len(cash) > 0 else {}
        cf1 = cash[1] if isinstance(cash, list) and len(cash) > 1 else {}
        inc0 = income[0] if isinstance(income, list) and len(income) > 0 else {}
        inc1 = income[1] if isinstance(income, list) and len(income) > 1 else {}
        bs0 = balance[0] if isinstance(balance, list) and len(balance) > 0 else {}
        bs1 = balance[1] if isinstance(balance, list) and len(balance) > 1 else {}
        return {
            "Name": prof.get("companyName", ticker),
            "Sector": prof.get("sector", SECTOR_MAP.get(ticker.upper(), "Other")),
            "MarketCap": prof.get("mktCap", np.nan),
            "EnterpriseValue": prof.get("mktCap", np.nan),
            "EBITDA": inc0.get("ebitda", np.nan),
            "FCF": cf0.get("freeCashFlow", np.nan),
            "FCF_Prev": cf1.get("freeCashFlow", np.nan),
            "OCF": cf0.get("operatingCashFlow", np.nan),
            "Revenue": inc0.get("revenue", np.nan),
            "Revenue_Prev": inc1.get("revenue", np.nan),
            "OperatingIncome": inc0.get("operatingIncome", np.nan),
            "OperatingIncome_Prev": inc1.get("operatingIncome", np.nan),
            "Debt": bs0.get("totalDebt", np.nan),
            "Debt_Prev": bs1.get("totalDebt", np.nan),
            "Cash": bs0.get("cashAndCashEquivalents", np.nan),
            "PE": rat.get("peRatioTTM", np.nan),
            "ForwardPE": np.nan,
            "Shares": prof.get("sharesOutstanding", np.nan),
            "InstitutionalPct": np.nan,
            "Beta": prof.get("beta", np.nan),
            "FundamentalSource": "FMP",
        }
    except Exception:
        return {}


def fetch_fundamentals(ticker: str, key: str = "") -> dict:
    f = fetch_fundamentals_fmp(ticker, key)
    if f:
        return f
    f = fetch_fundamentals_yf(ticker)
    if f:
        f["FundamentalSource"] = "yfinance"
    return f

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
        fund = fetch_fundamentals(t, fmp_api_key)
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
    # Volume Profile: approximates where the most volume traded by price level
    n_bins = 40
    price_bins = np.linspace(df["Low"].min(), df["High"].max(), n_bins)
    vol_profile = np.zeros(n_bins - 1)
    for _, row in df.iterrows():
        mask = (price_bins[:-1] <= row["High"]) & (price_bins[1:] >= row["Low"])
        count = int(mask.sum())
        if count > 0:
            vol_profile[mask] += row["Volume"] / count
    bin_mids = (price_bins[:-1] + price_bins[1:]) / 2
    fig_vp = go.Figure(go.Bar(
        x=vol_profile,
        y=bin_mids,
        orientation="h",
        name="Volume Profile",
    ))
    fig_vp.update_layout(
        height=500,
        title="Volume Profile — Price-at-Volume",
        xaxis_title="Accumulated Volume",
        yaxis_title="Price",
    )

    fig_score = go.Figure()
    fig_score.add_trace(go.Scatter(x=df.index, y=df["Whale_Score"], fill="tozeroy", name="Whale Score"))
    fig_score.add_hline(y=60, line_dash="dash", annotation_text="High conviction")
    fig_score.add_hline(y=80, line_dash="dash", annotation_text="Mega-whale")
    fig_score.update_layout(height=320, title="Whale Composite Score", yaxis=dict(range=[0, 105]))

    whale = df[df["Whale_Tier"] >= 2]
    fig_bs = go.Figure()
    fig_bs.add_bar(x=whale.index, y=whale["Buy_Vol"], name="Whale Buy Pressure")
    fig_bs.add_bar(x=whale.index, y=-whale["Sell_Vol"], name="Whale Sell Pressure")
    fig_bs.add_hline(y=0, line_width=1)
    fig_bs.update_layout(height=320, title="Whale Buy vs Sell Pressure", barmode="relative")

    fig_cluster = go.Figure()
    fig_cluster.add_bar(x=df.index, y=df["Whale_Cluster"], name="5-bar cluster")
    fig_cluster.add_hline(y=2, line_dash="dash", annotation_text="Cluster threshold")
    fig_cluster.update_layout(height=280, title="Whale Clustering — Sustained Institutional Activity", yaxis=dict(range=[0,5]))
    return fig_vp, fig_score, fig_bs, fig_cluster

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
tab_overview, tab_goat, tab_etfs, tab_price, tab_volume, tab_indicators, tab_watchlist, tab_hidden, tab_sector, tab_metals, tab_portfolio, tab_alerts, tab_news, tab_calendar, tab_backtest, tab_settings = st.tabs([
    "Overview",
    "GOAT Quality",
    "Discovery",
    "Price Chart",
    "Volume / Whale Flow",
    "Indicators",
    "Watchlist Scanner",
    "Hidden Gem Scanner",
    "Sector Flow",
    "Precious Metals",
    "Portfolio",
    "Alerts",
    "News",
    "Catalyst Calendar",
    "Backtest/Risk",
    "API Hooks",
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


with tab_goat:
    st.subheader("🐐 GOAT-Style Quality Score")
    st.caption("Inspired by the screenshot idea: simple grades for Profit, Cash and Stability. Uses FMP if provided, otherwise yfinance best-effort fundamentals.")

    fund_main = fetch_fundamentals(ticker, fmp_api_key)
    if fund_main:
        q = score_goat_quality(fund_main)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("GOAT Score", f"{q['GOATScore']}/100", q["Verdict"])
        c2.metric("Profit", q["ProfitGrade"], f"{q['ProfitScore']}/100")
        c3.metric("Cash", q["CashGrade"], f"{q['CashScore']}/100")
        c4.metric("Stable", q["StableGrade"], f"{q['StableScore']}/100")

        st.markdown("#### Company quality detail")
        detail = pd.DataFrame([
            {"Metric": "FCF Growth %", "Value": q["FCFGrowth%"]},
            {"Metric": "Revenue Growth %", "Value": q["RevenueGrowth%"]},
            {"Metric": "FCF Yield %", "Value": q["FCFYield%"]},
            {"Metric": "Debt Change %", "Value": q["DebtChange%"]},
            {"Metric": "Net Cash % of Market Cap", "Value": q["NetCash%MktCap"]},
        ])
        st.dataframe(detail, use_container_width=True, hide_index=True)
    else:
        st.warning("No fundamentals available for the main ticker. Add an FMP API key or try another ticker.")

    st.markdown("#### High Quality Screener")
    goat_default = "AAPL, MSFT, NVDA, GOOGL, META, AMZN, PLTR, TSLA, CLS, SANM, FLEX, JBL, VRT, LMT, RTX, NOC, COST, WMT"
    goat_tickers = st.text_area("Quality screener tickers", goat_default, height=90)
    if st.button("Run GOAT quality scan"):
        gt = tuple([x.strip().upper() for x in re.split(r"[,\n]+", goat_tickers) if x.strip()][:80])
        goat_df = scan_goat_quality(gt)
        if goat_df.empty:
            st.warning("No quality data returned.")
        else:
            st.dataframe(goat_df, use_container_width=True, hide_index=True)
            fig_goat = go.Figure(go.Bar(x=goat_df.head(15)["Ticker"], y=goat_df.head(15)["GOAT"], name="GOAT Score"))
            fig_goat.update_layout(height=380, title="Top Quality Scores", yaxis=dict(range=[0,100]))
            st.plotly_chart(fig_goat, use_container_width=True)


with tab_etfs:
    st.subheader("🧭 Discovery Search Engine")
    st.caption("Search either ETFs or individual company stocks with the same tag-based search engine. Use tags like AI, Defense, Gold, Dividend, Canada, Quality, Low Fee, Cash Flow, Hidden Gem, etc.")

    mode = st.radio("Search universe", ["ETFs", "Stocks"], horizontal=True, key="discovery_mode")
    is_etf_mode = mode == "ETFs"

    search_cols = st.columns([2, 1, 1])
    with search_cols[0]:
        discovery_query = st.text_input(
            f"Search {mode}",
            placeholder="Examples: AI, defense, gold, dividend, Japan, Canada, cash flow, hidden gem"
        )
    with search_cols[1]:
        discovery_match_mode = st.radio("Tag match", ["Any", "All"], horizontal=True, key="discovery_match_mode")
    with search_cols[2]:
        max_results = st.slider("Max results", 5, 150, 25, key="discovery_max_results")

    # Different filters depending on the selected universe.
    filter_cols = st.columns([2, 2])
    if is_etf_mode:
        all_tags = ETF_TAGS
        all_categories = ETF_CATEGORIES
        category_label = "ETF Categories"
        tag_session_key = "etf_quick_tags"
    else:
        all_tags = STOCK_TAGS
        all_categories = STOCK_CATEGORIES
        category_label = "Stock Sectors"
        tag_session_key = "stock_quick_tags"

    with filter_cols[0]:
        selected_categories = st.multiselect(category_label, all_categories, default=[], key=f"{mode}_categories")
    with filter_cols[1]:
        selected_tags = st.multiselect("Tags", all_tags, default=[], key=f"{mode}_tags")

    # Quick tag buttons/pills, similar to the screenshot.
    st.markdown("### Browse by investing theme")
    quick_sections = {
        "Hot Themes": ["AI", "AI Infrastructure", "Semiconductors", "Defense", "Energy", "Nuclear", "Uranium", "Gold", "Bitcoin / Crypto", "Cybersecurity", "Robotics & Automation", "Space", "Lithium / EV", "Clean Energy"],
        "Income / Defensive": ["Dividend", "Income", "REITs", "Bonds", "Treasuries", "Cash", "Defensive", "Consumer Staples", "Healthcare"],
        "Geography": ["US Large Cap", "US Small Cap", "Europe", "UK", "Japan", "China", "India", "Emerging Markets", "Canada", "TSX", "International"],
        "Style / Factors": ["Quality", "Momentum", "Value", "Low Fee", "Cash Flow", "Hidden Gem", "Growth", "High Beta", "Small Cap"],
        "Industries": ["Software", "Cloud", "Data Center", "Power", "Grid", "Manufacturing", "Copper", "Gold Miners", "Pipelines", "Banks", "Pharma", "Infrastructure"],
    }

    if tag_session_key not in st.session_state:
        st.session_state[tag_session_key] = []

    for section, tags in quick_sections.items():
        st.markdown(f"**{section}**")
        cols = st.columns(6)
        for i, tag in enumerate(tags):
            # Only show quick tags that exist in the current universe.
            if tag not in all_tags:
                continue
            with cols[i % 6]:
                if st.button(tag, key=f"disc_tag_{mode}_{section}_{tag}"):
                    if tag not in st.session_state[tag_session_key]:
                        st.session_state[tag_session_key].append(tag)
                    st.rerun()

    active_tags = list(dict.fromkeys((selected_tags or []) + st.session_state.get(tag_session_key, [])))
    if active_tags:
        st.info("Active tags: " + ", ".join(active_tags))
        if st.button(f"Clear active {mode} tags"):
            st.session_state[tag_session_key] = []
            st.rerun()

    if is_etf_mode:
        results = search_etf_catalog(discovery_query, active_tags, selected_categories, discovery_match_mode)
        st.markdown(f"### Results ({len(results)} ETFs found)")
        if results.empty:
            st.warning("No ETFs matched. Try fewer tags, switch from All to Any, or search a broader keyword.")
        else:
            st.dataframe(results.head(max_results), use_container_width=True, hide_index=True)
            st.caption("Top ETF matches: " + ", ".join(results.head(12)["Ticker"].astype(str).tolist()))
    else:
        results = search_stock_catalog(discovery_query, active_tags, selected_categories, discovery_match_mode)
        st.markdown(f"### Results ({len(results)} stocks found)")
        if results.empty:
            st.warning("No stocks matched. Try fewer tags, switch from All to Any, or search a broader keyword.")
        else:
            st.dataframe(results.head(max_results), use_container_width=True, hide_index=True)
            st.caption("Top stock matches: " + ", ".join(results.head(12)["Ticker"].astype(str).tolist()))
            st.info("Tip: copy a ticker into the main ticker box to analyze flow, news, fundamentals and charts.")

    st.markdown("---")
    st.markdown("### 💸 ETF Fee Saver")
    st.caption("This section only applies to ETFs. Enter ETFs you hold; the tool estimates whether a cheaper similar ETF exists in the searchable catalog.")
    fee_cols = st.columns([2,1])
    with fee_cols[0]:
        fee_holdings = st.text_area("ETF holdings", "SPY, QQQ, GDXJ, URA", height=80)
    with fee_cols[1]:
        fee_amount = st.number_input("Assumed $ per ETF", min_value=100.0, value=10000.0, step=500.0)
    fee_df = etf_fee_saver_table(fee_holdings, fee_amount)
    if not fee_df.empty:
        total_savings = pd.to_numeric(fee_df["Est. Annual Savings"], errors="coerce").fillna(0).sum()
        st.success(f"Estimated annual fee savings found: ${total_savings:,.2f}/yr")
        st.dataframe(fee_df, use_container_width=True, hide_index=True)

    st.markdown("### 🚩 ETF Hall of Shame")
    st.caption("Highest-expense ETFs in the catalog. High fees are not always bad, but they need to earn their keep.")
    st.dataframe(etf_hall_of_shame(), use_container_width=True, hide_index=True)

with tab_price:
    st.plotly_chart(make_price_chart(main_df, ticker, currency_symbol), use_container_width=True)

with tab_volume:
    st.subheader("Volume Analysis")
    fig_vp, fig_score, fig_bs, fig_cluster = make_volume_charts(main_df)
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        st.plotly_chart(fig_vp, use_container_width=True)
    with col_v2:
        st.plotly_chart(fig_score, use_container_width=True)
    st.plotly_chart(fig_bs, use_container_width=True)
    st.plotly_chart(fig_cluster, use_container_width=True)

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
    st.subheader("Sector + Theme Rotation Dashboard")
    st.caption("Uses all 11 GICS sector ETFs plus thematic proxies like Defense (ITA), Semiconductors (SMH), Uranium (URA), Oil Services (OIH), Gold Miners (GDX), Infrastructure (PAVE), Cybersecurity (HACK), and more.")

    c0, c1, c2 = st.columns([1, 1, 2])
    with c0:
        sector_period = st.selectbox("Sector period", ["1mo", "3mo", "6mo", "1y", "2y"], index=1, key="sector_period")
    with c1:
        sector_interval = st.selectbox("Sector interval", ["1d", "1wk"], index=0, key="sector_interval")
    with c2:
        st.info("Green sectors show stronger accumulation/relative strength. Red sectors show weaker flow or distribution.")

    sector_df = scan_sector_rotation(sector_period, sector_interval)
    if sector_df.empty:
        st.warning("No sector data returned. Check your connection or try another period/interval.")
    else:
        inflow_text, outflow_text = sector_leaders_text(sector_df)
        m1, m2, m3 = st.columns(3)
        m1.metric("Top inflow sector", f"{sector_df.iloc[0]['Sector']}", f"{sector_df.iloc[0]['RotationScore']:+.1f}")
        m2.metric("Top outflow sector", f"{sector_df.iloc[-1]['Sector']}", f"{sector_df.iloc[-1]['RotationScore']:+.1f}")
        risk_on_count = int((sector_df["RotationScore"] > 0).sum())
        m3.metric("Positive sectors/themes", f"{risk_on_count}/{len(sector_df)}")

        st.write("### Oversold / Overbought Rotation Signals")
        sig_cols = st.columns(3)
        possible_inflow = sector_df[sector_df["Money Flow Next"].isin(["Possible next inflow", "Watch for inflow"])]
        possible_outflow = sector_df[sector_df["Money Flow Next"].isin(["Possible next outflow", "Possible rotation out", "Avoid / still outflow"])]
        momentum_inflow = sector_df[sector_df["Money Flow Next"].isin(["Momentum still inflowing", "Inflow continuing"])]
        with sig_cols[0]:
            st.success("Potential next inflow")
            st.dataframe(
                possible_inflow.sort_values("RotationScore", ascending=False).head(5)[["Type", "Sector", "ETF", "RSI", "Extreme Signal", "Money Flow Next", "RotationScore", "Rel Strength vs SPY %", "OBV Direction"]],
                use_container_width=True,
                hide_index=True,
            )
        with sig_cols[1]:
            st.warning("Overbought / outflow risk")
            st.dataframe(
                possible_outflow.sort_values("RotationScore", ascending=True).head(5)[["Type", "Sector", "ETF", "RSI", "Extreme Signal", "Money Flow Next", "RotationScore", "Rel Strength vs SPY %", "OBV Direction"]],
                use_container_width=True,
                hide_index=True,
            )
        with sig_cols[2]:
            st.info("Momentum inflow")
            st.dataframe(
                momentum_inflow.sort_values("RotationScore", ascending=False).head(5)[["Type", "Sector", "ETF", "RSI", "Extreme Signal", "Money Flow Next", "RotationScore", "Rel Strength vs SPY %", "OBV Direction"]],
                use_container_width=True,
                hide_index=True,
            )

        st.write("### Live sector ranking")
        st.dataframe(
            sector_df[[
                "Rank", "Type", "Sector", "ETF", "RotationScore", "RSI", "Extreme Signal", "Money Flow Next", "NetFlow", "BuyScore", "SellScore",
                "20-Bar Return %", "Rel Strength vs SPY %", "OBV Direction", "Whale Bars 20", "Accum Signals 20", "Dist Signals 20", "Regime"
            ]],
            use_container_width=True,
            hide_index=True,
        )

        st.write("### GICS sectors vs thematic groups")
        gics_only = sector_df[sector_df["Type"] == "GICS Sector"].sort_values("RotationScore", ascending=False)
        themes_only = sector_df[sector_df["Type"] == "Theme"].sort_values("RotationScore", ascending=False)
        gcol1, gcol2 = st.columns(2)
        with gcol1:
            st.write("**Top official GICS sectors**")
            st.dataframe(gics_only.head(6)[["Sector", "ETF", "RotationScore", "RSI", "Extreme Signal", "Money Flow Next"]], use_container_width=True, hide_index=True)
        with gcol2:
            st.write("**Top thematic flows**")
            st.dataframe(themes_only.head(8)[["Sector", "ETF", "RotationScore", "RSI", "Extreme Signal", "Money Flow Next"]], use_container_width=True, hide_index=True)

        st.write("### Top inflow / outflow sectors and themes")
        ic1, ic2 = st.columns(2)
        with ic1:
            st.success(f"Strongest inflows: {inflow_text}")
            st.dataframe(
                sector_df.sort_values("RotationScore", ascending=False).head(5)[["Type", "Sector", "ETF", "RotationScore", "RSI", "Extreme Signal", "Money Flow Next", "NetFlow", "OBV Direction", "Regime"]],
                use_container_width=True,
                hide_index=True,
            )
        with ic2:
            st.error(f"Weakest outflows: {outflow_text}")
            st.dataframe(
                sector_df.sort_values("RotationScore", ascending=True).head(5)[["Type", "Sector", "ETF", "RotationScore", "RSI", "Extreme Signal", "Money Flow Next", "NetFlow", "OBV Direction", "Regime"]],
                use_container_width=True,
                hide_index=True,
            )

        tree_labels = list(sector_df["Type"].unique()) + sector_df["Sector"].tolist()
        tree_parents = [""] * len(sector_df["Type"].unique()) + sector_df["Type"].tolist()
        type_values = [float((sector_df.loc[sector_df["Type"] == t, "RotationScore"].abs() + 5).sum()) for t in sector_df["Type"].unique()]
        tree_values = type_values + (sector_df["RotationScore"].abs() + 5).tolist()
        tree_colors = [0] * len(sector_df["Type"].unique()) + sector_df["RotationScore"].tolist()
        fig_tree = go.Figure(go.Treemap(
            labels=tree_labels,
            parents=tree_parents,
            values=tree_values,
            marker=dict(
                colors=tree_colors,
                colorscale="RdYlGn",
                cmid=0,
                colorbar=dict(title="Rotation Score")
            ),
            customdata=np.vstack([
                np.array([["", "", "", "", "", "", ""] for _ in sector_df["Type"].unique()], dtype=object),
                np.stack([
                    sector_df["ETF"],
                    sector_df["BuyScore"].round(1),
                    sector_df["SellScore"].round(1),
                    sector_df["NetFlow"].round(1),
                    sector_df["20-Bar Return %"].round(2),
                    sector_df["Whale Bars 20"],
                    sector_df["Regime"],
                ], axis=-1)
            ]),
            hovertemplate=(
                "<b>%{label}</b> (%{customdata[0]})<br>"
                "Rotation Score: %{color:.1f}<br>"
                "Buy/Sell: %{customdata[1]} / %{customdata[2]}<br>"
                "Net Flow: %{customdata[3]}<br>"
                "20-Bar Return: %{customdata[4]}%<br>"
                "Whale Bars 20: %{customdata[5]}<br>"
                "Regime: %{customdata[6]}<extra></extra>"
            ),
        ))
        fig_tree.update_layout(height=560, title="Sector + Theme Heatmap")
        st.plotly_chart(fig_tree, use_container_width=True)

        fig_rank = go.Figure(go.Bar(
            x=sector_df["Sector"],
            y=sector_df["RotationScore"],
            marker=dict(color=sector_df["RotationScore"], colorscale="RdYlGn", cmid=0),
            customdata=np.stack([sector_df["ETF"], sector_df["NetFlow"], sector_df["20-Bar Return %"]], axis=-1),
            hovertemplate="<b>%{x}</b> (%{customdata[0]})<br>Rotation: %{y:.1f}<br>Net Flow: %{customdata[1]:.1f}<br>20-Bar Return: %{customdata[2]:.2f}%<extra></extra>",
        ))
        fig_rank.update_layout(height=440, title="Sector + Theme Ranking — Rotation Score", yaxis_title="Rotation Score")
        st.plotly_chart(fig_rank, use_container_width=True)

        st.write("### Oversold/Overbought Flow Map")
        fig_extreme = go.Figure(go.Scatter(
            x=sector_df["RSI"],
            y=sector_df["RotationScore"],
            mode="markers+text",
            text=sector_df["ETF"],
            textposition="top center",
            marker=dict(
                size=(sector_df["Whale Bars 20"] + 1) * 7,
                color=sector_df["Rel Strength vs SPY %"],
                colorscale="RdYlGn",
                cmid=0,
                showscale=True,
                colorbar=dict(title="Rel Strength vs SPY %"),
                line=dict(width=1, color="white"),
            ),
            customdata=np.stack([
                sector_df["Sector"],
                sector_df["Extreme Signal"],
                sector_df["Money Flow Next"],
                sector_df["OBV Direction"],
                sector_df["Whale Bars 20"],
            ], axis=-1),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "RSI: %{x:.1f}<br>"
                "Rotation Score: %{y:.1f}<br>"
                "Signal: %{customdata[1]}<br>"
                "Money Flow Next: %{customdata[2]}<br>"
                "OBV: %{customdata[3]}<br>"
                "Whale Bars 20: %{customdata[4]}<extra></extra>"
            ),
        ))
        fig_extreme.add_vrect(x0=0, x1=35, fillcolor="green", opacity=0.08, line_width=0, annotation_text="Oversold")
        fig_extreme.add_vrect(x0=70, x1=100, fillcolor="red", opacity=0.08, line_width=0, annotation_text="Overbought")
        fig_extreme.add_hline(y=0, line_dash="dash", line_color="gray")
        fig_extreme.update_layout(
            height=480,
            title="Where Money May Flow Next — RSI Extreme vs Rotation Score",
            xaxis_title="RSI",
            yaxis_title="Rotation Score",
            xaxis=dict(range=[20, 85]),
        )
        st.plotly_chart(fig_extreme, use_container_width=True)

        st.write("### Rotation timeline")
        timeline_df = build_sector_rotation_timeline("6mo" if sector_period in ["1mo", "3mo"] else sector_period, sector_interval)
        if timeline_df.empty:
            st.info("Rotation timeline unavailable for this period/interval.")
        else:
            fig_timeline = go.Figure()
            # Plot all sectors/themes as relative strength vs SPY.
            for sector_name, sub in timeline_df.groupby("Sector"):
                fig_timeline.add_trace(go.Scatter(
                    x=sub["Date"],
                    y=sub["RelativeStrength"],
                    mode="lines",
                    name=sector_name,
                    hovertemplate=f"<b>{sector_name}</b><br>Date: %{{x}}<br>Rel Strength vs SPY: %{{y:.2f}}%<extra></extra>",
                ))
            fig_timeline.add_hline(y=0, line_dash="dash", line_color="gray")
            fig_timeline.update_layout(
                height=560,
                title="Sector + Theme Rotation Timeline — 20-Bar Relative Strength vs SPY",
                yaxis_title="Relative Strength vs SPY (%)",
                legend=dict(orientation="h", y=-0.2),
            )
            st.plotly_chart(fig_timeline, use_container_width=True)

        st.write("### Current sector ETF proxy details")
        for sec in sector_df["Sector"]:
            row = sector_df[sector_df["Sector"] == sec].iloc[0]
            with st.expander(f"{row['Sector']} — {row['ETF']} — Rotation {row['RotationScore']:+.1f}"):
                st.write(
                    f"Buy score: **{row['BuyScore']}** · Sell score: **{row['SellScore']}** · "
                    f"Net flow: **{row['NetFlow']}** · Regime: **{row['Regime']}**"
                )
                st.write(
                    f"20-bar return: **{row['20-Bar Return %']}%** · Relative strength vs SPY: **{row['Rel Strength vs SPY %']}%** · "
                    f"RSI: **{row['RSI']}** · Signal: **{row['Extreme Signal']}** · Next flow: **{row['Money Flow Next']}**"
                )
                st.write(
                    f"OBV: **{row['OBV Direction']}** · Whale bars in last 20: **{row['Whale Bars 20']}** · "
                    f"Accum/dist signals: **{row['Accum Signals 20']} / {row['Dist Signals 20']}**"
                )

        st.caption("Sector/theme ETFs are proxies, not perfect ownership maps. Use this to detect rotation, then confirm with individual tickers.")


with tab_metals:
    st.subheader("🥇 Precious Metals Smart Money Meter")
    st.caption("Tracks gold, silver, platinum, and copper using live futures proxies. CFTC/CME warehouse values can be entered manually until you connect a paid/official feed.")

    mcol1, mcol2, mcol3 = st.columns([1, 1, 2])
    with mcol1:
        metals_period = st.selectbox("Metals period", ["5d", "1mo", "3mo", "6mo", "1y", "2y"], index=2, key="metals_period")
    with mcol2:
        metals_interval = st.selectbox("Metals interval", ["1h", "1d", "1wk"], index=1, key="metals_interval")
    with mcol3:
        selected_metal = st.selectbox("Stress calculator metal", list(METAL_FUTURES.keys()), index=0)

    metals_df = scan_metals(metals_period, metals_interval)
    if metals_df.empty:
        st.warning("No metals data returned. Try another period/interval or check yfinance availability.")
    else:
        leader = metals_df.iloc[0]
        a, b, c, d = st.columns(4)
        a.metric("Top smart-money metal", leader["Metal"], f"{leader['Smart Money Meter']}/100")
        b.metric("Price", f"{leader['Price']:,.2f}", f"{leader['1-Bar Change %']:+.2f}%")
        c.metric("20-bar return", f"{leader['20-Bar Return %']:+.2f}%")
        d.metric("Flow", leader["Signal"])

        st.plotly_chart(metal_meter_figure(int(leader["Smart Money Meter"]), f"{leader['Metal']} Smart Money Meter"), use_container_width=True)
        st.dataframe(
            metals_df[["Metal", "Ticker", "Price", "1-Bar Change %", "20-Bar Return %", "RSI", "Smart Money Meter", "Signal", "Whale Bars 20", "Accum Signals 20", "Dist Signals 20", "Above VWAP", "OBV 20-Bar Direction"]],
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    st.subheader("📦 Paper vs Physical Stress Calculator")
    st.caption("Manual inputs let you reproduce COMEX-style stress metrics from CME warehouse/open-interest data. This avoids pretending to have official warehouse data when no feed is connected.")
    meta = METAL_FUTURES[selected_metal]
    stress_cols = st.columns(5)
    with stress_cols[0]:
        oi_contracts = st.number_input("Open interest contracts", min_value=0.0, value=0.0, step=1000.0, key="pm_oi")
    with stress_cols[1]:
        registered_units = st.number_input(f"Registered physical ({meta['unit']})", min_value=0.0, value=0.0, step=10000.0, key="pm_registered")
    with stress_cols[2]:
        delivery_notices = st.number_input("Delivery notices/contracts", min_value=0.0, value=0.0, step=100.0, key="pm_notices")
    with stress_cols[3]:
        daily_withdrawal = st.number_input(f"Daily withdrawal ({meta['unit']}/day)", min_value=0.0, value=0.0, step=1000.0, key="pm_withdrawal")
    with stress_cols[4]:
        contract_size = st.number_input(f"Contract size ({meta['unit']})", min_value=1.0, value=float(meta["contract_size"]), step=1.0, key="pm_contract")

    stress = calculate_comex_stress(oi_contracts, registered_units, contract_size, delivery_notices, daily_withdrawal)
    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("Stress score", f"{stress['stress_score']}/100")
    s2.metric("Paper leverage", "—" if np.isnan(stress["paper_leverage"]) else f"{stress['paper_leverage']:.1f}x")
    s3.metric("Delivery coverage", "—" if np.isnan(stress["delivery_coverage_pct"]) else f"{stress['delivery_coverage_pct']:.1f}%")
    s4.metric("Notice coverage", "—" if np.isnan(stress["notice_coverage_pct"]) else f"{stress['notice_coverage_pct']:.1f}%")
    s5.metric("Depletion estimate", "—" if np.isnan(stress["depletion_days"]) else f"{stress['depletion_days']:.0f} days")

    st.divider()
    st.subheader("🗺️ Metals Intelligence Checklist")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
        - ✅ Live gold, silver, platinum, copper futures prices
        - ✅ Smart-money meter from VWAP, OBV, whale flow, MACD, RSI
        - ✅ Paper-vs-physical stress calculator
        """)
    with c2:
        st.markdown("""
        - 🔌 CFTC Commitments of Traders hook can be connected next
        - 🔌 CME warehouse data hook can be connected next
        - 🔌 Shanghai premium monitor can be connected next
        """)

with tab_portfolio:
    st.subheader("Portfolio Tracker & Trading Journal")
    st.caption(f"Saved locally at: `{PORTFOLIO_FILE}`")
    pf = load_portfolio()

    with st.form("add_position"):
        st.write("### Add / update position")
        pc1, pc2, pc3, pc4, pc5 = st.columns(5)
        pticker = pc1.text_input("Ticker", ticker).strip().upper()
        qty = pc2.number_input("Quantity", value=0.0, step=1.0)
        entry = pc3.number_input("Entry price", value=0.0, step=0.01)
        stop = pc4.number_input("Stop", value=0.0, step=0.01)
        target = pc5.number_input("Target", value=0.0, step=0.01)
        notes = st.text_input("Notes", "")
        submitted = st.form_submit_button("Save position")
        if submitted and pticker and qty != 0 and entry > 0:
            row = {"Ticker": pticker, "Quantity": qty, "EntryPrice": entry, "Stop": stop if stop > 0 else np.nan, "Target": target if target > 0 else np.nan, "Sector": SECTOR_MAP.get(pticker, "Other"), "Notes": notes}
            pf = pf[pf["Ticker"].astype(str).str.upper() != pticker]
            pf = pd.concat([pf, pd.DataFrame([row])], ignore_index=True)
            save_portfolio(pf)
            st.success(f"Saved {pticker}.")

    if pf.empty:
        st.info("No portfolio positions saved yet.")
    else:
        enrich = []
        for _, r in pf.iterrows():
            t = str(r["Ticker"]).upper()
            last_px = get_latest_price_fast(t)
            qty = float(r["Quantity"])
            entry_px = float(r["EntryPrice"])
            market_value = qty * last_px if pd.notna(last_px) else np.nan
            cost = qty * entry_px
            pnl = market_value - cost if pd.notna(market_value) else np.nan
            pnl_pct = pnl / cost * 100 if cost else np.nan
            risk_amt = abs(entry_px - float(r["Stop"])) * abs(qty) if pd.notna(r.get("Stop", np.nan)) else np.nan
            enrich.append({**r.to_dict(), "LastPrice": last_px, "MarketValue": market_value, "Cost": cost, "UnrealizedPnL": pnl, "PnL%": pnl_pct, "Risk$": risk_amt})
        pf_live = pd.DataFrame(enrich)
        st.dataframe(pf_live, use_container_width=True, hide_index=True)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total market value", f"{currency_symbol}{pf_live['MarketValue'].sum(skipna=True):,.2f}")
        m2.metric("Total cost", f"{currency_symbol}{pf_live['Cost'].sum(skipna=True):,.2f}")
        m3.metric("Unrealized P&L", f"{currency_symbol}{pf_live['UnrealizedPnL'].sum(skipna=True):,.2f}")
        total_cost = pf_live['Cost'].sum(skipna=True)
        total_pnl = pf_live['UnrealizedPnL'].sum(skipna=True)
        m4.metric("P&L %", f"{(total_pnl/total_cost*100 if total_cost else 0):+.2f}%")

        sector_exp = pf_live.groupby("Sector", as_index=False)["MarketValue"].sum().sort_values("MarketValue", ascending=False)
        fig_exp = go.Figure(go.Pie(labels=sector_exp["Sector"], values=sector_exp["MarketValue"], hole=0.45))
        fig_exp.update_layout(height=420, title="Portfolio Sector Exposure")
        st.plotly_chart(fig_exp, use_container_width=True)

        edited = st.data_editor(pf, use_container_width=True, num_rows="dynamic")
        if st.button("Save edited portfolio"):
            save_portfolio(edited)
            st.success("Portfolio saved.")


with tab_alerts:
    st.subheader("Real Alert System")
    st.write("Alerts can be sent to Discord and/or Telegram when the main ticker produces a fresh buy/sell signal above your thresholds.")
    st.write(f"Current signal: **{scores['signal']}** · Buy {scores['buy']} / Sell {scores['sell']} · Regime: {regime}")
    if not enable_real_alerts:
        st.info("Enable real alerts in the sidebar to activate sending.")
    else:
        if st.button("Send test alert"):
            test_msg = f"Test alert from Institutional Flow Pro for {ticker} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            results = []
            if discord_webhook:
                results.append(send_discord_alert(discord_webhook, test_msg))
            if telegram_bot_token and telegram_chat_id:
                results.append(send_telegram_alert(telegram_bot_token, telegram_chat_id, test_msg))
            if not results:
                st.warning("No alert destination configured.")
            for ok, detail in results:
                st.write(("✅" if ok else "❌") + " " + detail)
        if st.button("Force-send current signal alert"):
            # bypass duplicate log by adding timestamp to ticker key through direct send
            msg = f"🐋 Forced alert\nTicker: {ticker}\nSignal: {scores['signal']}\nBuy/Sell: {scores['buy']}/{scores['sell']}\nRegime: {regime}\nPrice: {latest['Close']:,.2f}"
            if discord_webhook:
                st.write(send_discord_alert(discord_webhook, msg))
            if telegram_bot_token and telegram_chat_id:
                st.write(send_telegram_alert(telegram_bot_token, telegram_chat_id, msg))
    st.write("### Sent alert log")
    st.json(load_alert_log())


with tab_news:
    st.subheader(f"News, Press Releases & Impact — {ticker}")

    news_controls = st.columns([2, 1, 1])
    with news_controls[0]:
        news_max_age_days = st.slider(
            "News date range",
            min_value=1,
            max_value=365,
            value=1,
            step=1,
            help="Only load headlines/press releases published within this many days. Default is 1 day for fresh, actionable catalysts."
        )
    with news_controls[1]:
        include_unknown_news_dates = st.toggle(
            "Include undated items",
            value=False,
            help="Turn on only if a source is missing dates. Leaving this off prevents stale items from polluting the score."
        )
    with news_controls[2]:
        if st.button("Clear news cache"):
            try:
                fetch_news.clear()
            except Exception:
                st.cache_data.clear()
            st.rerun()

    articles = fetch_news(ticker, news_max_age_days, include_unknown_news_dates)
    momentum = news_momentum(articles)
    confirmation = whale_news_confirmation(articles, main_df)

    cols = st.columns(7)
    cols[0].metric("Sentiment", momentum["label"], momentum["score"])
    cols[1].metric("News Impact", f"{momentum['impact']}/100")
    cols[2].metric("Headlines", momentum["total"])
    cols[3].metric("Press Releases", momentum["press"])
    cols[4].metric("High Impact", momentum["high_impact"])
    cols[5].metric("Bullish", momentum["bullish"])
    cols[6].metric("Bearish", momentum["bearish"])

    st.write("### 🐋 News + Whale Confirmation")
    conf_cols = st.columns([1, 3])
    conf_cols[0].metric("Confirmation Score", f"{confirmation['score']}/100")
    if confirmation["score"] >= 75:
        conf_cols[1].success(f"{confirmation['label']} — " + " · ".join(confirmation["details"]))
    elif confirmation["score"] >= 55:
        conf_cols[1].info(f"{confirmation['label']} — " + " · ".join(confirmation["details"]))
    elif confirmation["score"] > 0:
        conf_cols[1].warning(f"{confirmation['label']} — " + (" · ".join(confirmation["details"]) if confirmation["details"] else "No flow confirmation yet"))
    else:
        conf_cols[1].info(confirmation["label"])

    st.write("### 🔔 News-triggered alerts")
    st.caption("Triggers when a fresh high-impact headline/press release aligns with whale/flow confirmation.")
    if enable_real_alerts:
        if st.button("Send news + whale alert if conditions are met"):
            results = maybe_send_news_alert(ticker, articles, confirmation, scores, float(latest["Close"]))
            if results:
                for r in results:
                    st.write(r)
            else:
                st.info("No news alert condition met right now.")
        # Also auto-check on page load; duplicate log prevents repeated sends.
        auto_results = maybe_send_news_alert(ticker, articles, confirmation, scores, float(latest["Close"]))
        for r in auto_results:
            st.caption(r)
    else:
        st.info("Enable real alerts in the sidebar to send news + whale confirmation alerts.")

    if not articles:
        st.info("No RSS news available. Install feedparser or check the ticker.")
    else:
        st.write("### 🚨 High-Impact News / Press Releases")
        high_impact = [a for a in articles if a.get("is_high_impact") or a.get("impact", 0) >= 60]
        if high_impact:
            for a in high_impact[:10]:
                icon = "🟢" if a["sentiment"] > 0 else "🔴" if a["sentiment"] < 0 else "⚪"
                press = "📢 Press release" if a.get("is_press") else "📰 News"
                age = f"{a['age_hrs']:.0f}h ago" if a["age_hrs"] < 48 else f"{a['age_hrs']/24:.0f}d ago"
                st.markdown(
                    f"{icon} **Impact {a.get('impact', 0)}/100** · {press} · "
                    f"[{a['title']}]({a['url']})  \n"
                    f"<small>{a['source']} · {age}</small>",
                    unsafe_allow_html=True,
                )
        else:
            st.info("No high-impact press release/news item found for this ticker right now.")

        st.write("### 📢 Press Releases")
        press_articles = [a for a in articles if a.get("is_press")]
        if press_articles:
            for a in press_articles[:12]:
                icon = "🟢" if a["sentiment"] > 0 else "🔴" if a["sentiment"] < 0 else "⚪"
                age = f"{a['age_hrs']:.0f}h ago" if a["age_hrs"] < 48 else f"{a['age_hrs']/24:.0f}d ago"
                st.markdown(
                    f"{icon} **Impact {a.get('impact', 0)}/100** · "
                    f"[{a['title']}]({a['url']})  \n"
                    f"<small>{a['source']} · {age}</small>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No ticker-matched press releases found in the free RSS feeds.")

        st.write("### All Recent Headlines")
        news_rows = []
        for a in articles:
            news_rows.append({
                "Impact": a.get("impact", 0),
                "Sentiment": a.get("sentiment", 0),
                "Press": "Yes" if a.get("is_press") else "No",
                "High Impact": "Yes" if a.get("is_high_impact") else "No",
                "Source": a.get("source", ""),
                "Age (hrs)": round(float(a.get("age_hrs", 999)), 1),
                "Title": a.get("title", ""),
                "URL": a.get("url", ""),
            })
        news_table = pd.DataFrame(news_rows)
        st.dataframe(news_table, use_container_width=True, hide_index=True)

        st.caption(
            f"Showing news from the last {news_max_age_days} day(s). Free RSS feeds can be incomplete or delayed. "
            "For professional alerts, wire this section to paid Benzinga, PR Newswire, BusinessWire, or Polygon news APIs."
        )

with tab_calendar:
    st.subheader("📅 Earnings & Catalyst Calendar")
    st.caption("Forward-looking catalysts from free yfinance fields. Coverage varies by ticker; paid APIs such as Benzinga, Polygon, FMP, or Nasdaq calendars are more complete.")
    cal_cols = st.columns([2, 1, 1])
    with cal_cols[0]:
        cal_source = st.radio("Calendar scope", ["Main ticker", "Watchlist"], horizontal=True)
    with cal_cols[1]:
        lookahead_days = st.slider("Lookahead days", 7, 120, 45, step=1)
    with cal_cols[2]:
        if st.button("Clear calendar cache"):
            try:
                fetch_catalyst_calendar.clear()
            except Exception:
                st.cache_data.clear()
            st.rerun()

    if cal_source == "Watchlist":
        cal_tickers = parse_tickers(watchlist_text)[:max_scan]
    else:
        cal_tickers = [ticker]
    calendar_df = fetch_catalyst_calendar(cal_tickers, lookahead_days)

    if calendar_df.empty:
        st.info("No upcoming catalyst/earnings data found from the free calendar source for the selected ticker(s).")
    else:
        upcoming_7 = calendar_df[calendar_df["Days Away"] <= 7]
        c1, c2, c3 = st.columns(3)
        c1.metric("Upcoming events", len(calendar_df))
        c2.metric("Within 7 days", len(upcoming_7))
        c3.metric("Tickers covered", calendar_df["Ticker"].nunique())

        st.dataframe(calendar_df, use_container_width=True, hide_index=True)

        # Timeline-style bar chart.
        fig_cal = go.Figure(go.Bar(
            x=calendar_df["Days Away"],
            y=calendar_df["Ticker"].astype(str) + " · " + calendar_df["Event"].astype(str),
            orientation="h",
            text=calendar_df["Date"].astype(str),
            hovertemplate="%{y}<br>Date: %{text}<br>Days away: %{x}<extra></extra>",
        ))
        fig_cal.update_layout(height=max(360, 28 * len(calendar_df)), title="Catalyst Timeline", xaxis_title="Days Away", yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_cal, use_container_width=True)

        # Optional catalyst alert for main ticker when event is very close and flow/news is aligned.
        cat_msg = catalyst_alert_message(ticker, calendar_df, confirmation if 'confirmation' in globals() else {}, scores)
        if cat_msg:
            st.warning(cat_msg)
            if enable_real_alerts and st.button("Send catalyst alert"):
                out = []
                if discord_webhook:
                    out.append(send_discord_alert(discord_webhook, cat_msg))
                if telegram_bot_token and telegram_chat_id:
                    out.append(send_telegram_alert(telegram_bot_token, telegram_chat_id, cat_msg))
                for ok, detail in out:
                    st.write(("✅" if ok else "❌") + " " + detail)


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
# fetch_fundamentals_fmp(ticker, key) -> richer historical FCF/margins for Hidden Gem Scanner
""", language="python")
    st.write("Required packages:")
    st.code("pip install streamlit yfinance pandas numpy plotly requests feedparser", language="bash")

if realtime_on:
    time.sleep(refresh_interval)
    st.cache_data.clear()
    st.rerun()
