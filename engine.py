import requests
import yfinance as yf
import json
from datetime import datetime

def get_vix():
    vix = yf.Ticker("^INDIAVIX")
    data = vix.history(period="1d", interval="5m")
    return float(data["Close"].iloc[-1])

def get_index_price(symbol):
    ticker = yf.Ticker(symbol)
    data = ticker.history(period="1d", interval="5m")
    return float(data["Close"].iloc[-1])

def get_option_chain(symbol):
    url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
    headers = {"User-Agent": "Mozilla/5.0"}
    session = requests.Session()
    session.get("https://www.nseindia.com", headers=headers)
    data = session.get(url, headers=headers).json()
    return data["records"]["data"]

def analyze(symbol, yf_symbol):
    spot = get_index_price(yf_symbol)
    vix = get_vix()
    chain = get_option_chain(symbol)

    ce_oi = 0
    pe_oi = 0

    for item in chain:
        if "CE" in item and "PE" in item:
            ce_oi += item["CE"]["openInterest"]
            pe_oi += item["PE"]["openInterest"]

    if pe_oi > ce_oi * 1.2:
        trade = "Buy CE"
        condition = "Bullish Pressure from OI"
    elif ce_oi > pe_oi * 1.2:
        trade = "Buy PE"
        condition = "Bearish Pressure from OI"
    else:
        trade = "Straddle"
        condition = "Balanced OI, Expect Volatility"

    entry = round(spot + 20, 2)
    exit_zone = round(spot + 120, 2)
    invalid = round(spot - 80, 2)

    return {
        "market_condition": condition,
        "trade_type": trade,
        "entry_zone": entry,
        "exit_zone": exit_zone,
        "invalidation": invalid,
        "confidence": 75 if vix > 15 else 65,
        "vix": vix,
        "spot": spot,
        "time": datetime.now().strftime("%H:%M:%S")
    }

data = {
    "nifty": analyze("NIFTY", "^NSEI"),
    "banknifty": analyze("BANKNIFTY", "^NSEBANK")
}

with open("data.json", "w") as f:
    json.dump(data, f, indent=4)