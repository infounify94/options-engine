import yfinance as yf
from datetime import datetime, timedelta
import json
import sys

# -------------------- HELPERS --------------------

def log(msg):
    print(f"{datetime.now().strftime('%H:%M:%S')} - {msg}")

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50
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

def calculate_support_resistance(prices):
    recent = prices[-20:]
    high = max(recent)
    low = min(recent)
    pivot = (high + low + prices[-1]) / 3
    resistance = (2 * pivot) - low
    support = (2 * pivot) - high
    return round(support, 2), round(resistance, 2)

# -------------------- OPTIONS BEHAVIOUR (NEW) --------------------

def get_options_behavior(closes, support, resistance, current_price):
    last_30 = closes[-30:]
    range_size = max(last_30) - min(last_30)

    if range_size < (current_price * 0.002):
        return (
            "RANGE (Premium Decay Zone)",
            "Market in tight range. Options premium will decay.",
            "Wait for breakout"
        )
    elif current_price > resistance:
        return (
            "BREAKOUT UP",
            "",
            "Immediate trade opportunity"
        )
    elif current_price < support:
        return (
            "BREAKOUT DOWN",
            "",
            "Immediate trade opportunity"
        )
    else:
        return (
            "CONSOLIDATION",
            "Inside range. Wait for breakout.",
            "10:45–12:15 best for options"
        )

# -------------------- STRIKES & TARGETS --------------------

def get_suggested_strikes(price, signal):
    base = 100 if price > 50000 else 50
    atm = round(price / base) * base
    if signal == "BUY CALL":
        return [atm, atm + base, atm + base * 2]
    if signal == "BUY PUT":
        return [atm, atm - base, atm - base * 2]
    return [atm]

def calculate_target_stoploss(price, signal, vix):
    move = (200 if price > 50000 else 100) * (1 + vix / 100)
    if signal == "BUY CALL":
        return round(price + move, 2), round(price - move * 0.5, 2)
    if signal == "BUY PUT":
        return round(price - move, 2), round(price + move * 0.5, 2)
    return price, price

def get_expiry():
    today = datetime.now()
    days = (3 - today.weekday()) % 7
    if days < 2:
        days += 7
    return (today + timedelta(days=days)).strftime("%d-%b-%Y")

# -------------------- MAIN ANALYSIS --------------------

def analyze(name, symbol):
    try:
        stock = yf.Ticker(symbol)
        hist = stock.history(period="5d", interval="5m")

        closes = hist['Close'].tolist()
        volumes = hist['Volume'].tolist()
        current_price = closes[-1]

        sma20 = sum(closes[-20:]) / 20
        sma50 = sum(closes[-50:]) / 50
        rsi = calculate_rsi(closes)
        momentum = ((current_price - closes[-10]) / closes[-10]) * 100
        support, resistance = calculate_support_resistance(closes)

        vix = yf.Ticker("^INDIAVIX").history(period="1d")['Close'][-1]

        phase, avoid_reason, best_window = get_options_behavior(
            closes, support, resistance, current_price
        )

        bullish = sum([
            current_price > sma20,
            current_price > sma50,
            50 < rsi < 70,
            momentum > 0.3
        ])

        bearish = sum([
            current_price < sma20,
            current_price < sma50,
            30 < rsi < 50,
            momentum < -0.3
        ])

        signal = "AVOID"
        if bullish >= 3 and "RANGE" not in phase:
            signal = "BUY CALL"
        elif bearish >= 3 and "RANGE" not in phase:
            signal = "BUY PUT"

        strikes = get_suggested_strikes(current_price, signal)
        target, sl = calculate_target_stoploss(current_price, signal, vix)

        return {
            "signal": signal,
            "current_price": f"₹{current_price:.2f}",
            "suggested_strikes": strikes,
            "expiry": get_expiry(),
            "targets": {
                "target": f"₹{target}",
                "stop_loss": f"₹{sl}"
            },
            "indicators": {
                "rsi": rsi,
                "momentum": f"{momentum:.2f}%",
                "support": f"₹{support}",
                "resistance": f"₹{resistance}"
            },
            "options_behavior": {
                "market_phase": phase,
                "best_time_window": best_window,
                "avoid_reason": avoid_reason,
                "breakout_above": f"₹{resistance}",
                "breakout_below": f"₹{support}"
            },
            "time": datetime.now().strftime("%H:%M:%S")
        }

    except Exception as e:
        return {"error": str(e)}

# -------------------- EXECUTION --------------------

def main():
    result = {
        "nifty": analyze("NIFTY", "^NSEI"),
        "banknifty": analyze("BANKNIFTY", "^NSEBANK"),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0)

if __name__ == "__main__":
    main()
