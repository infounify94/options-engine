import requests
import statistics
from datetime import datetime
import json

TWELVE_KEY = "1e88d174b30146ceb4b18045710afcfc"
NEWS_KEY = "dfbfbb2c1046406997fc9284575e5487"

def get_price(symbol):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=5min&outputsize=50&apikey={TWELVE_KEY}"
    r = requests.get(url).json()
    closes = [float(x["close"]) for x in r["values"]]
    return closes

def get_indicator(symbol, indicator):
    url = f"https://api.twelvedata.com/{indicator}?symbol={symbol}&interval=5min&apikey={TWELVE_KEY}"
    r = requests.get(url).json()
    key = indicator.lower()
    return float(r["values"][0][key])

def get_vix():
    url = f"https://api.twelvedata.com/quote?symbol=INDIAVIX&apikey={TWELVE_KEY}"
    r = requests.get(url).json()
    return float(r["close"])

def get_news_sentiment():
    url = f"https://newsapi.org/v2/everything?q=nifty OR banknifty OR rbi OR stock market india&apiKey={NEWS_KEY}"
    r = requests.get(url).json()
    titles = [a["title"].lower() for a in r["articles"][:10]]

    score = 0
    for t in titles:
        if any(w in t for w in ["crash","fall","fear","drop","war","inflation"]):
            score -= 1
        if any(w in t for w in ["rise","growth","profit","gain","bullish","record"]):
            score += 1
    return score

def decision(symbol):
    closes = get_price(symbol)
    ema = get_indicator(symbol, "ema")
    rsi = get_indicator(symbol, "rsi")
    macd = get_indicator(symbol, "macd")
    vix = get_vix()
    news = get_news_sentiment()

    last = closes[-1]

    side = "AVOID"
    entry = ""
    exit = ""

    if last > ema and rsi > 55 and macd > 0 and news >= 0:
        side = "BUY CALL (CE)"
        entry = f"Above {last}"
        exit = f"Near {last + 80}"

    elif last < ema and rsi < 45 and macd < 0 and news <= 0:
        side = "BUY PUT (PE)"
        entry = f"Below {last}"
        exit = f"Near {last - 80}"

    if vix > 20:
        side += " | High Volatility"

    return {
        "side": side,
        "entry": entry,
        "exit": exit,
        "time": datetime.now().strftime("%H:%M")
    }

result = {
    "nifty": decision("NIFTY"),
    "banknifty": decision("BANKNIFTY")
}

with open("data.json", "w") as f:
    json.dump(result, f, indent=2)
