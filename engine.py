import yfinance as yf
from datetime import datetime
import json
import math

# ---------- Helpers ----------

def get_price(symbol):
    t = yf.Ticker(symbol)
    data = t.history(period="1d", interval="5m")
    return float(data["Close"].iloc[-1])

def get_rsi(symbol, period=14):
    t = yf.Ticker(symbol)
    data = t.history(period="5d", interval="5m")["Close"]

    delta = data.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])

def get_support_resistance(symbol):
    t = yf.Ticker(symbol)
    data = t.history(period="2d", interval="5m")

    recent = data.tail(60)
    high = recent["High"].max()
    low = recent["Low"].min()

    return float(low), float(high)

def round_strike(price, step):
    base = round(price / step) * step
    return [base, base + step, base - step]

# ---------- Core Analyzer ----------

def analyze(name, symbol, step):
    price = get_price(symbol)
    rsi = get_rsi(symbol)
    support, resistance = get_support_resistance(symbol)

    range_size = resistance - support
    near_resistance = price > (resistance - range_size * 0.25)
    near_support = price < (support + range_size * 0.25)

    # Market phase
    if near_resistance:
        phase = "NEAR RESISTANCE"
    elif near_support:
        phase = "NEAR SUPPORT"
    else:
        phase = "MID RANGE"

    # Signal logic (REALISTIC)
    signal = "AVOID"

    if near_resistance and rsi > 60:
        signal = "BUY CALL"

    elif near_support and rsi < 40:
        signal = "BUY PUT"

    strikes = round_strike(price, step)

    return {
        "signal": signal,
        "current_price": f"₹{price:.2f}",
        "suggested_strikes": strikes,
        "expiry": get_next_thursday(),
        "targets": {
            "target": f"₹{resistance:.2f}",
            "stop_loss": f"₹{support:.2f}"
        },
        "indicators": {
            "rsi": round(rsi, 2),
            "support": f"₹{support:.2f}",
            "resistance": f"₹{resistance:.2f}"
        },
        "options_behavior": {
            "market_phase": phase,
            "best_time_window": "10:45–12:15 best for options",
            "avoid_reason": "Wait for price to come near S/R" if signal=="AVOID" else "",
            "breakout_above": f"₹{resistance:.2f}",
            "breakout_below": f"₹{support:.2f}"
        },
        "time": datetime.now().strftime("%H:%M:%S")
    }

# ---------- Expiry ----------

def get_next_thursday():
    today = datetime.now()
    days = (3 - today.weekday()) % 7
    if days == 0:
        days = 7
    next_thu = today.replace(hour=0, minute=0, second=0) + \
               timedelta(days=days)
    return next_thu.strftime("%d-%b-%Y")

# ---------- Main ----------

def main():
    result = {
        "nifty": analyze("NIFTY", "^NSEI", 50),
        "banknifty": analyze("BANKNIFTY", "^NSEBANK", 100),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    from datetime import timedelta
    main()
