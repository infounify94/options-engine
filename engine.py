import requests
import yfinance as yf
import json
from datetime import datetime

# -------- OPTION CHAIN MIRROR (NOT NSE DIRECT) -------- #

def get_option_chain(symbol):
    if symbol == "NIFTY":
        url = "https://api.moneycontrol.com/mcapi/v1/optionchain/nifty"
    else:
        url = "https://api.moneycontrol.com/mcapi/v1/optionchain/banknifty"

    try:
        data = requests.get(url, timeout=10).json()
        return data["data"]
    except:
        return []


# -------- MARKET DATA -------- #

def get_vix():
    try:
        vix = yf.Ticker("^INDIAVIX")
        data = vix.history(period="1d", interval="5m")
        return float(data["Close"].iloc[-1])
    except:
        return 15.0


def get_index_price(symbol):
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="1d", interval="5m")
        return float(data["Close"].iloc[-1])
    except:
        return 0.0


# -------- LOGIC -------- #

def analyze(symbol, yf_symbol):
    spot = get_index_price(yf_symbol)
    vix = get_vix()
    chain = get_option_chain(symbol)

    ce_oi = 0
    pe_oi = 0

    for item in chain:
        ce_oi += int(item.get("CE_OI", 0))
        pe_oi += int(item.get("PE_OI", 0))

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
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


# -------- RUN -------- #

data = {
    "nifty": analyze("NIFTY", "^NSEI"),
    "banknifty": analyze("BANKNIFTY", "^NSEBANK")
}

with open("data.json", "w") as f:
    json.dump(data, f, indent=4)
