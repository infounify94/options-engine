import yfinance as yf
import pandas as pd
import numpy as np
import json
from datetime import datetime, time
import pytz

IST = pytz.timezone("Asia/Kolkata")
JSON_FILE = "orb_analysis.json"


# ---------------- TIME ----------------
def now_ist():
    return datetime.now(IST)


def market_open():
    t = now_ist().time()
    return time(9, 15) <= t <= time(15, 30)


# ---------------- HELPERS ----------------
def candle_body_pct(row):
    body = abs(row['Close'] - row['Open'])
    rng = row['High'] - row['Low']
    return (body / rng) * 100 if rng != 0 else 0


def calculate_atr(df, period=14):
    df['H-L'] = df['High'] - df['Low']
    df['H-PC'] = abs(df['High'] - df['Close'].shift(1))
    df['L-PC'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    df['ATR'] = df['TR'].rolling(period).mean()
    return df


def atr_expanding(df):
    a = df['ATR'].tail(3).values
    return a[2] > a[1] > a[0]


def vwap(df):
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    return (tp * df['Volume']).cumsum() / df['Volume'].cumsum()


def nearest_itm_strike(price, step, option_type):
    if option_type == "CALL":
        return int(price // step) * step
    else:
        return int((price // step) + 1) * step


# ---------------- ORB ----------------
def get_orb(df):
    orb_df = df.between_time("09:15", "09:45")
    return orb_df['High'].max(), orb_df['Low'].min()


# ---------------- SIGNAL LOGIC ----------------
def generate_signals(index, df, prev_day, orb_high, orb_low):
    signals = []

    df = calculate_atr(df)
    df['VWAP'] = vwap(df)

    avg_vol = df['Volume'].rolling(10).mean()

    for i in range(20, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]

        if row.name.time() > time(14, 45):
            continue

        body_pct = candle_body_pct(row)
        rng = row['High'] - row['Low']

        strong = (
            body_pct >= 60 and
            row['Volume'] >= 1.8 * avg_vol.iloc[i] and
            atr_expanding(df.iloc[:i+1])
        )

        if not strong:
            continue

        option_type = None

        # ORB breakout
        if row['Close'] > orb_high:
            option_type = "CALL"
            reason = "ORB Breakout"
        elif row['Close'] < orb_low:
            option_type = "PUT"
            reason = "ORB Breakdown"

        # VWAP reclaim / reject
        elif row['Close'] > row['VWAP'] and prev['Close'] < prev['VWAP']:
            option_type = "CALL"
            reason = "VWAP Reclaim"
        elif row['Close'] < row['VWAP'] and prev['Close'] > prev['VWAP']:
            option_type = "PUT"
            reason = "VWAP Breakdown"

        # Mid-range momentum
        elif rng > 0.4 * (orb_high - orb_low):
            if row['Close'] > row['Open']:
                option_type = "CALL"
                reason = "Momentum Expansion"
            else:
                option_type = "PUT"
                reason = "Momentum Expansion"

        if option_type:
            step = 50 if index == "NIFTY" else 100
            strike = nearest_itm_strike(row['Close'], step, option_type)

            signals.append({
                "index": index,
                "time": row.name.strftime("%H:%M"),
                "signal": option_type,
                "entry_spot_price": round(row['Close'], 2),
                "suggested_strike": strike,
                "target_pct": 25,
                "stoploss_pct": 35,
                "reason": reason
            })

    return signals[-15:]  # last 15 signals of the day


# ---------------- FETCH ----------------
def fetch(symbol):
    df = yf.download(symbol, interval="5m", period="2d", progress=False)
    df = df.tz_localize(None)
    df.index = df.index.tz_localize("UTC").tz_convert(IST)
    return df


def prev_levels(df):
    prev = df[df.index.date < now_ist().date()]
    p = prev.groupby(prev.index.date).last().iloc[-1]
    return {"high": p['High'], "low": p['Low']}


# ---------------- MAIN ----------------
def process(index, symbol):
    df = fetch(symbol)
    if df.empty:
        return []

    orb_high, orb_low = get_orb(df)
    prev_day = prev_levels(df)

    return generate_signals(index, df, prev_day, orb_high, orb_low)


def main():
    output = {
        "last_update": now_ist().strftime("%Y-%m-%d %H:%M:%S"),
        "market_open": market_open(),
        "signals": []
    }

    output["signals"] += process("NIFTY", "^NSEI")
    output["signals"] += process("BANKNIFTY", "^NSEBANK")

    with open(JSON_FILE, "w") as f:
        json.dump(output, f, indent=4)


if __name__ == "__main__":
    main()
