import yfinance as yf
from datetime import datetime, timedelta
import json

# ---------- RSI ----------
def rsi(prices, period=14):
    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i-1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


# ---------- Support / Resistance ----------
def support_resistance(prices):
    recent = prices[-30:]
    high = max(recent)
    low = min(recent)
    return round(low, 2), round(high, 2)


# ---------- Strike Suggestion ----------
def strikes(price, step):
    atm = round(price / step) * step
    return [atm - step, atm, atm + step]


# ---------- Expiry ----------
def next_thursday():
    today = datetime.now()
    days = (3 - today.weekday()) % 7
    if days == 0:
        days = 7
    return (today + timedelta(days=days)).strftime("%d-%b-%Y")


# ---------- Core Logic ----------
def analyze(name, symbol, step):
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="5d", interval="5m")

    closes = hist["Close"].tolist()
    current_price = closes[-1]

    r = rsi(closes)
    support, resistance = support_resistance(closes)

    # Momentum (key logic)
    momentum = current_price - closes[-3]

    near_res = abs(current_price - resistance) < (resistance - support) * 0.15
    near_sup = abs(current_price - support) < (resistance - support) * 0.15

    signal = "AVOID"

    if near_res and r > 60 and momentum > 0:
        signal = "BUY CALL"

    elif near_sup and r < 40 and momentum < 0:
        signal = "BUY PUT"

    # Targets
    if signal == "BUY CALL":
        target = resistance
        sl = support
    elif signal == "BUY PUT":
        target = support
        sl = resistance
    else:
        target = resistance
        sl = support

    phase = "CONSOLIDATION"
    if current_price > resistance:
        phase = "BREAKOUT UP"
    elif current_price < support:
        phase = "BREAKOUT DOWN"
    elif near_res:
        phase = "NEAR RESISTANCE"
    elif near_sup:
        phase = "NEAR SUPPORT"

    return {
        "signal": signal,
        "current_price": f"₹{current_price:.2f}",
        "suggested_strikes": strikes(current_price, step),
        "expiry": next_thursday(),
        "targets": {
            "target": f"₹{target:.2f}",
            "stop_loss": f"₹{sl:.2f}"
        },
        "indicators": {
            "rsi": r,
            "support": f"₹{support:.2f}",
            "resistance": f"₹{resistance:.2f}"
        },
        "options_behavior": {
            "market_phase": phase,
            "breakout_above": f"₹{resistance:.2f}",
            "breakout_below": f"₹{support:.2f}"
        },
        "time": datetime.now().strftime("%H:%M:%S")
    }


# ---------- Main ----------
def main():
    result = {
        "nifty": analyze("NIFTY", "^NSEI", 50),
        "banknifty": analyze("BANKNIFTY", "^NSEBANK", 100),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
    }

    with open("data.json", "w") as f:
        json.dump(result, f, indent=2)

    print("data.json created")


if __name__ == "__main__":
    main()
