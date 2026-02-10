import yfinance as yf
from datetime import datetime, timedelta
import json
import pandas as pd
import numpy as np

"""
OPENING RANGE BREAKOUT (ORB) STRATEGY FOR OPTIONS

Core Philosophy:
- Options premium moves on RANGE EXPANSION, not indicators
- Only trade 2-4 breakouts per day max
- Speed matters more than direction
- No indicator noise - just price levels and volatility

Rules:
1. Opening Range (9:15-9:45) = trap zone
2. Wait for clean break above/below
3. Confirm with ATR expansion
4. Enter only if VIX < 20
5. Use premium-based stops
"""

# ===================== HELPER FUNCTIONS =====================

def get_india_vix():
    """Check if VIX allows options buying"""
    try:
        vix = yf.Ticker("^INDIAVIX")
        # Yahoo doesn't provide reliable 5-min VIX data - use daily
        hist = vix.history(period="5d", interval="1d")
        if len(hist) > 0:
            current_vix = hist['Close'].iloc[-1]
            
            if current_vix < 15:
                signal = "LOW - Ideal for options"
            elif current_vix < 20:
                signal = "NORMAL - Safe to trade"
            else:
                signal = "HIGH - AVOID options buying"
            
            return {
                "value": round(current_vix, 2),
                "signal": signal,
                "safe_to_trade": current_vix < 20
            }
    except:
        pass
    
    return {"value": None, "signal": "UNAVAILABLE", "safe_to_trade": True}


def atr(df, period=14):
    """Calculate ATR for volatility expansion check"""
    if len(df) < period + 1:
        return None
    
    df = df.copy()
    df['H-L'] = df['High'] - df['Low']
    df['H-PC'] = abs(df['High'] - df['Close'].shift(1))
    df['L-PC'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    
    atr_series = df['TR'].rolling(window=period).mean()
    
    atr_current = atr_series.iloc[-1]
    atr_prev = atr_series.iloc[-2]
    
    return {
        "current": round(atr_current, 2) if not pd.isna(atr_current) else None,
        "expanding": atr_current > atr_prev if not pd.isna(atr_current) and not pd.isna(atr_prev) else False
    }


def get_previous_day_levels(symbol):
    """Get yesterday's high and low"""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="5d", interval="1d")
        
        if len(hist) >= 2:
            prev_day = hist.iloc[-2]
            return {
                "high": round(prev_day['High'], 2),
                "low": round(prev_day['Low'], 2),
                "close": round(prev_day['Close'], 2)
            }
    except:
        pass
    
    return None


def next_expiry():
    """Get next weekly expiry (Thursday)"""
    today = datetime.now()
    days = (3 - today.weekday()) % 7
    if days == 0:
        days = 7
    return (today + timedelta(days=days)).strftime("%d-%b-%Y")


def yahoo_expiry_format(symbol):
    """Get nearest expiry from Yahoo correctly"""
    try:
        ticker = yf.Ticker(symbol)
        exps = ticker.options
        if exps:
            return exps[0]
    except:
        pass
    return None


def get_strike_by_premium(symbol, option_type, expiry, premium_min=180, premium_max=350):
    """
    Select strike whose premium is in ideal options buying zone (₹180–₹350)
    Works at ANY index level (future proof)
    
    Why this range?
    - Below ₹180: Too cheap, likely deep OTM, low delta
    - Above ₹350: Too expensive, risking too much capital
    - ₹180-350: Sweet spot for risk/reward
    """
    try:
        ticker = yf.Ticker(symbol)
        chain = ticker.option_chain(expiry)
        options = chain.calls if option_type == "CALL" else chain.puts
        
        # Calculate mid price (more accurate than stale lastPrice)
        options['mid'] = (options['bid'] + options['ask']) / 2
        options['price'] = options['mid'].fillna(options['lastPrice'])
        
        # Filter strikes by premium zone AND liquidity
        # Liquidity filters adjusted for morning trading conditions
        filtered = options[
            (options['price'] >= premium_min) &
            (options['price'] <= premium_max) &
            (options['volume'] > 50) &             # Realistic morning volume
            (options['openInterest'] > 1500)       # Realistic morning OI
        ].copy()
        
        if len(filtered) == 0:
            return {"error": "No liquid strike in premium zone (₹180-350, vol>50, OI>1500)"}
        
        # Prefer highest OI + good volume (liquidity matters)
        # OI weighted 70%, Volume 30%
        filtered['score'] = filtered['openInterest'] * 0.7 + filtered['volume'] * 0.3
        best = filtered.sort_values(by='score', ascending=False).iloc[0]
        
        return {
            "strike": int(best['strike']),
            "premium": round(best['price'], 2),
            "oi": int(best['openInterest']),
            "volume": int(best['volume']),
            "bid_ask_spread": round(best['ask'] - best['bid'], 2) if 'ask' in best and 'bid' in best else None
        }
        
    except Exception as e:
        return {"error": f"Could not fetch option chain: {str(e)}"}


# ===================== CORE ORB LOGIC =====================

def analyze_orb(symbol, step, name):
    """
    Opening Range Breakout Analysis
    
    Strategy:
    1. Define opening range (9:15-9:45)
    2. Wait for price to CLOSE outside this range
    3. Check if ATR is expanding (volatility increasing)
    4. Check VIX < 20
    5. Enter on breakout with tight stops
    """
    
    try:
        ticker = yf.Ticker(symbol)
        
        # Get today's intraday data
        hist = ticker.history(period="1d", interval="5m")
        
        # Yahoo index data already in IST — do NOT convert timezone
        # Converting from UTC would shift candles by 5.5 hours!
        # Safe handling for both tz-aware and tz-naive data
        try:
            hist.index = hist.index.tz_localize(None)
        except:
            pass
        
        # Filter market hours only
        hist = hist.between_time("09:15", "15:30")
        
        if len(hist) < 10:
            return {"error": f"Not enough data for {name} - market might not be open"}
        
        # Convert to IST timezone aware
        current_time = datetime.now()
        
        # ===================== STEP 1: OPENING RANGE =====================
        
        # Opening range = first 30 mins (9:15-9:45) - LOCKED and time-safe
        # between_time ensures correct candles regardless of when script runs
        opening_candles = hist.between_time("09:15", "09:45")
        
        if len(opening_candles) < 7:
            return {
                "index": name,
                "status": "WAITING",
                "message": "Opening range not yet formed (wait till 9:45 AM)",
                "time": current_time.strftime("%H:%M:%S IST")
            }
        
        orb_high = opening_candles['High'].max()
        orb_low = opening_candles['Low'].min()
        orb_range = orb_high - orb_low
        
        # Current price from last CLOSED candle (not forming candle)
        current_price = hist['Close'].iloc[-2]
        current_high = hist['High'].iloc[-2]
        current_low = hist['Low'].iloc[-2]
        
        # Previous day levels
        prev_day = get_previous_day_levels(symbol)
        
        # ===================== STEP 2: BREAKOUT DETECTION =====================
        
        breakout = None
        breakout_strength = "NONE"
        
        # Use last CLOSED candle (not current forming candle)
        # iloc[-1] is current candle which may still be forming
        # iloc[-2] is last completed candle
        if len(hist) < 2:
            return {
                "index": name,
                "status": "WAITING",
                "message": "Not enough completed candles for breakout check",
                "time": current_time.strftime("%H:%M:%S IST")
            }
        
        last_closed = hist.iloc[-2]
        
        # Check if last closed candle CLOSED outside range
        if last_closed['Close'] > orb_high:
            # Bullish breakout
            breakout = "CALL"
            distance_from_orb = last_closed['Close'] - orb_high
            
            # Strength based on distance
            if distance_from_orb > orb_range * 0.5:
                breakout_strength = "STRONG"
            elif distance_from_orb > orb_range * 0.2:
                breakout_strength = "MODERATE"
            else:
                breakout_strength = "WEAK"
                
        elif last_closed['Close'] < orb_low:
            # Bearish breakout
            breakout = "PUT"
            distance_from_orb = orb_low - last_closed['Close']
            
            if distance_from_orb > orb_range * 0.5:
                breakout_strength = "STRONG"
            elif distance_from_orb > orb_range * 0.2:
                breakout_strength = "MODERATE"
            else:
                breakout_strength = "WEAK"
        
        # ===================== STEP 3: ATR EXPANSION CHECK =====================
        
        atr_data = atr(hist, period=14)
        atr_expanding = atr_data["expanding"] if atr_data else False
        
        # ===================== STEP 4: VIX CHECK =====================
        
        vix_data = get_india_vix()
        vix_safe = vix_data["safe_to_trade"]
        
        # ===================== STEP 5: TIME CHECK =====================
        
        current_hour = datetime.now().hour
        current_min = datetime.now().minute
        
        # Avoid late theta zone
        late_trade_warning = False
        if current_hour >= 14 and breakout_strength != "STRONG":
            late_trade_warning = True
        
        # ===================== STEP 6: SIGNAL GENERATION =====================
        
        signal = "WAIT"
        confidence = 0
        reasons = []
        
        if not breakout:
            reasons.append("⏳ Price still inside opening range - no breakout yet")
            reasons.append(f"📊 ORB High: ₹{orb_high}, ORB Low: ₹{orb_low}")
            reasons.append("💡 Wait for clean break and close outside range")
            
        elif late_trade_warning:
            signal = "WAIT"
            reasons.append("⏰ After 2 PM and breakout not strong - theta risk too high")
            reasons.append(f"📊 Breakout strength: {breakout_strength}")
            reasons.append("💡 Skip this trade or wait for stronger setup")
            
        elif not vix_safe:
            reasons.append("⚠️ India VIX too high - options premiums expensive")
            reasons.append(f"📊 VIX: {vix_data['value']} (need < 20)")
            reasons.append("💡 Wait for VIX to cool down")
            
        elif breakout_strength == "WEAK":
            reasons.append(f"⚠️ Breakout too weak - only {distance_from_orb:.2f} points")
            reasons.append(f"📊 Need > {orb_range * 0.2:.2f} points for valid signal")
            reasons.append("💡 Wait for stronger move or re-entry")
            
        elif not atr_expanding:
            reasons.append("⚠️ ATR not expanding - volatility not increasing")
            reasons.append("📊 Premium may not move enough despite spot move")
            reasons.append("💡 Wait for volatility pickup or skip trade")
            
        else:
            # VALID SIGNAL
            signal = f"BUY {breakout}"
            
            # Confidence based on breakout strength
            if breakout_strength == "STRONG":
                confidence = 85
                reasons.append(f"✅ STRONG {breakout} breakout detected")
            else:  # MODERATE
                confidence = 70
                reasons.append(f"✅ MODERATE {breakout} breakout detected")
            
            reasons.append(f"✅ Broke out of opening range (₹{orb_high}-₹{orb_low})")
            reasons.append(f"✅ ATR expanding - volatility increasing")
            reasons.append(f"✅ VIX at {vix_data['value']} - safe to trade")
            
            # Check previous day levels for confluence
            if prev_day:
                if breakout == "CALL" and current_price > prev_day['high']:
                    confidence += 5
                    reasons.append(f"✅ Also broke yesterday's high (₹{prev_day['high']})")
                elif breakout == "PUT" and current_price < prev_day['low']:
                    confidence += 5
                    reasons.append(f"✅ Also broke yesterday's low (₹{prev_day['low']})")
        
        # ===================== TARGETS & STOPS =====================
        
        if signal != "WAIT":
            if breakout == "CALL":
                entry = current_price
                
                # Target = ORB range size projected upward
                target = orb_high + (orb_range * 1.5)
                
                # Stop = just below ORB high (re-entry into range = failed breakout)
                stop_loss = orb_high - (orb_range * 0.2)
                
                # Premium stops (% based, not spot based)
                premium_stop = "30-40% of premium paid"
                premium_target = "80-120% of premium paid"
                
            else:  # PUT
                entry = current_price
                target = orb_low - (orb_range * 1.5)
                stop_loss = orb_low + (orb_range * 0.2)
                premium_stop = "30-40% of premium paid"
                premium_target = "80-120% of premium paid"
            
            risk_reward = abs(target - entry) / abs(entry - stop_loss)
            
            # ================= PREMIUM-BASED STRIKE SELECTION =================
            # Map index symbols to Yahoo Finance option symbols
            option_symbol = "NIFTY.NS" if name == "NIFTY" else "BANKNIFTY.NS"
            expiry = yahoo_expiry_format(option_symbol)
            
            if not expiry:
                strike_rec = {"error": "No expiry available from Yahoo"}
            else:
                strike_rec = get_strike_by_premium(option_symbol, breakout, expiry)
            
            # Time-based exit
            if current_hour >= 14:  # After 2 PM
                time_warning = "⚠️ Late in day - consider smaller position or skip"
            else:
                time_warning = "✅ Good time window for entry"
            
            trade_plan = {
                "entry": f"₹{entry:.2f} (current market price)",
                "spot_target": f"₹{target:.2f}",
                "spot_stop": f"₹{stop_loss:.2f}",
                "risk_reward": f"1:{risk_reward:.2f}",
                "premium_target": premium_target,
                "premium_stop": premium_stop,
                "time_warning": time_warning,
                "position_size": "1-2 lots max (risk 2% of capital)",
                "exit_time": "Exit all positions by 3:15 PM (no overnight)"
            }
            
        else:
            trade_plan = {
                "message": "No trade setup yet - be patient",
                "tip": "Options traders who wait make money. Traders who force trades lose money."
            }
            strike_rec = None
        
        # ===================== OUTPUT =====================
        
        return {
            "index": name,
            "signal": signal,
            "confidence": f"{confidence}%" if confidence > 0 else "N/A",
            "current_price": f"₹{current_price:.2f}",
            "expiry": next_expiry(),
            "opening_range": {
                "high": f"₹{orb_high}",
                "low": f"₹{orb_low}",
                "size": f"₹{orb_range:.2f}"
            },
            "breakout_status": {
                "type": breakout if breakout else "NONE",
                "strength": breakout_strength
            },
            "previous_day": prev_day,
            "volatility": {
                "atr": atr_data,
                "india_vix": vix_data
            },
            "recommended_option": strike_rec,
            "trade_plan": trade_plan,
            "signal_reasons": reasons,
            "time": current_time.strftime("%H:%M:%S IST")
        }
        
    except Exception as e:
        return {"error": str(e), "index": name}


# ===================== PREMIUM-BASED BACKTESTING =====================

def backtest_orb_premium_based(symbol, step, name, days_back=20):
    """
    Backtest with PREMIUM-based P&L, not spot-based
    
    Key differences:
    - Simulates actual option premium movement
    - Accounts for theta decay
    - Only counts fast moves as wins
    - Realistic for options trading
    """
    
    try:
        ticker = yf.Ticker(symbol)
        
        # Fetch data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        # Get daily data to identify trading days
        daily = ticker.history(start=start_date, end=end_date, interval="1d")
        
        trades = []
        capital = 10000
        equity_curve = [capital]
        
        # Process each trading day
        for day_idx in range(len(daily)):
            day_date = daily.index[day_idx].date()
            
            # Get that day's 5-min data
            day_start = datetime.combine(day_date, datetime.min.time())
            day_end = day_start + timedelta(days=1)
            
            try:
                intraday = ticker.history(start=day_start, end=day_end, interval="5m")
                
                # Yahoo index data already in IST — do NOT convert timezone
                # Safe handling for both tz-aware and tz-naive data
                try:
                    intraday.index = intraday.index.tz_localize(None)
                except:
                    pass
                
                intraday = intraday.between_time("09:15", "15:30")
                
                if len(intraday) < 10:
                    continue
                
                # Opening range - time-safe selection
                orb_candles = intraday.between_time("09:15", "09:45")
                orb_high = orb_candles['High'].max()
                orb_low = orb_candles['Low'].min()
                orb_range = orb_high - orb_low
                
                # Check for breakout in subsequent candles
                for i in range(6, len(intraday) - 12):  # Leave 12 candles (1 hour) for move
                    candle = intraday.iloc[i]
                    
                    breakout = None
                    # Use previous closed candle for entry, not current forming candle
                    entry_price = intraday.iloc[i-1]['Close']
                    
                    # Detect breakout
                    if candle['Close'] > orb_high and (candle['Close'] - orb_high) > orb_range * 0.2:
                        breakout = "CALL"
                    elif candle['Close'] < orb_low and (orb_low - candle['Close']) > orb_range * 0.2:
                        breakout = "PUT"
                    
                    if not breakout:
                        continue
                    
                    # Simulate option behavior over next 1 hour (12 candles)
                    future = intraday.iloc[i+1:i+13]
                    
                    if len(future) == 0:
                        continue
                    
                    # Premium simulation
                    # Initial premium for NIFTY ATM weekly ~1% of spot (realistic)
                    initial_premium = entry_price * 0.01
                    
                    max_profit = 0
                    hit_stop = False
                    
                    for j, future_candle in enumerate(future.iterrows()):
                        fc = future_candle[1]
                        time_elapsed = (j + 1) * 5  # minutes
                        
                        # Theta decay (lose ~2% per 15 minutes for weeklies)
                        theta_loss = (time_elapsed / 15) * 0.02
                        
                        if breakout == "CALL":
                            spot_move = fc['High'] - entry_price
                            
                            # Premium move = delta * spot_move - theta
                            # Assume delta = 0.6 for ATM
                            premium_gain = (spot_move / entry_price) * 0.6 - theta_loss
                            
                            # Check stop (re-entry into range)
                            if fc['Low'] < orb_high:
                                hit_stop = True
                                break
                            
                        else:  # PUT
                            spot_move = entry_price - fc['Low']
                            premium_gain = (spot_move / entry_price) * 0.6 - theta_loss
                            
                            if fc['High'] > orb_low:
                                hit_stop = True
                                break
                        
                        max_profit = max(max_profit, premium_gain)
                    
                    # Determine outcome
                    if hit_stop:
                        pnl_pct = -35  # Average stop loss
                        outcome = "STOP_HIT"
                    elif max_profit >= 0.8:  # 80%+ gain
                        pnl_pct = min(max_profit * 100, 120)  # Cap at 120%
                        outcome = "TARGET_HIT"
                    elif max_profit >= 0.4:  # 40%+ gain (partial profit)
                        pnl_pct = 40
                        outcome = "PARTIAL_PROFIT"
                    else:  # Theta killed it
                        pnl_pct = max(max_profit * 100, -50)
                        outcome = "THETA_DECAY"
                    
                    # Record trade
                    risk_amount = capital * 0.02  # Risk 2%
                    trade_pnl = risk_amount * (pnl_pct / 100)
                    capital += trade_pnl
                    equity_curve.append(capital)
                    
                    trades.append({
                        "date": day_date,
                        "type": breakout,
                        "entry": entry_price,
                        "outcome": outcome,
                        "pnl_pct": round(pnl_pct, 2),
                        "pnl_amount": round(trade_pnl, 2)
                    })
                    
                    break  # Only one trade per day
                    
            except:
                continue
        
        # Calculate stats
        wins = [t for t in trades if t['pnl_pct'] > 0]
        losses = [t for t in trades if t['pnl_pct'] <= 0]
        
        avg_win = sum(t['pnl_pct'] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t['pnl_pct'] for t in losses) / len(losses) if losses else 0
        
        win_rate = (len(wins) / len(trades) * 100) if trades else 0
        total_return = ((capital - 10000) / 10000 * 100)
        
        return {
            "index": name,
            "period": f"{days_back} days",
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": f"{win_rate:.1f}%",
            "avg_win": f"{avg_win:.1f}%",
            "avg_loss": f"{avg_loss:.1f}%",
            "expectancy": f"{(win_rate/100 * avg_win + (1-win_rate/100) * avg_loss):.2f}%",
            "total_return": f"{total_return:.2f}%",
            "final_capital": f"₹{capital:.2f}",
            "max_capital": f"₹{max(equity_curve):.2f}",
            "note": "Premium-based backtest with theta decay simulation"
        }
        
    except Exception as e:
        return {"error": str(e)}


# ===================== MAIN =====================

def main():
    print("\n" + "="*70)
    print("📊 OPENING RANGE BREAKOUT (ORB) ANALYZER - OPTIONS FOCUSED")
    print("="*70)
    print("\n⏰ Analyzing current market state...\n")
    
    # Real-time analysis
    nifty = analyze_orb("^NSEI", 50, "NIFTY")
    banknifty = analyze_orb("^NSEBANK", 100, "BANKNIFTY")
    
    # Print summary
    print(f"\n📈 NIFTY 50")
    print(f"   Signal: {nifty.get('signal', 'ERROR')}")
    if 'confidence' in nifty and nifty['confidence'] != 'N/A':
        print(f"   Confidence: {nifty['confidence']}")
    if 'current_price' in nifty:
        print(f"   Price: {nifty['current_price']}")
    if 'recommended_option' in nifty and nifty['recommended_option']:
        opt = nifty['recommended_option']
        if 'error' not in opt:
            print(f"   Recommended: {opt['strike']} @ ₹{opt['premium']} (OI: {opt['oi']:,})")
    
    print(f"\n📊 BANK NIFTY")
    print(f"   Signal: {banknifty.get('signal', 'ERROR')}")
    if 'confidence' in banknifty and banknifty['confidence'] != 'N/A':
        print(f"   Confidence: {banknifty['confidence']}")
    if 'current_price' in banknifty:
        print(f"   Price: {banknifty['current_price']}")
    if 'recommended_option' in banknifty and banknifty['recommended_option']:
        opt = banknifty['recommended_option']
        if 'error' not in opt:
            print(f"   Recommended: {opt['strike']} @ ₹{opt['premium']} (OI: {opt['oi']:,})")
    
    # Backtesting
    print("\n" + "="*70)
    print("📊 Running premium-based backtests (this may take 30-60 seconds)...")
    print("="*70)
    
    nifty_bt = backtest_orb_premium_based("^NSEI", 50, "NIFTY", days_back=20)
    banknifty_bt = backtest_orb_premium_based("^NSEBANK", 100, "BANKNIFTY", days_back=20)
    
    # Compile results
    data = {
        "strategy": "Opening Range Breakout (ORB)",
        "philosophy": "Premium moves on range expansion, not indicators",
        "live_signals": {
            "nifty": nifty,
            "banknifty": banknifty
        },
        "backtest_results": {
            "nifty": nifty_bt,
            "banknifty": banknifty_bt
        },
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
        "trading_rules": [
            "Rule 1: Only trade ORB breakouts (9:15-9:45 range)",
            "Rule 2: Require ATR expansion (volatility must increase)",
            "Rule 3: VIX must be < 20",
            "Rule 4: Use premium stops (30-40%), not spot stops",
            "Rule 5: Exit all positions by 3:15 PM",
            "Rule 6: Max 2-4 trades per day",
            "Rule 7: If signal says WAIT, then WAIT"
        ],
        "critical_notes": [
            "Options are NOT indicator-based - they're event-based",
            "Premium only moves on fast breakouts, not slow grinds",
            "Theta decay kills you if move is too slow",
            "This strategy gives fewer signals - that's GOOD",
            "Paper trade for 2 weeks minimum before going live"
        ],
        "disclaimer": "Educational only. Not financial advice. Trade at your own risk."
    }
    
    # Save
    with open("orb_analysis.json", "w") as f:
        json.dump(data, f, indent=2)
    
    print("\n" + "="*70)
    print("✅ Analysis complete! Check 'orb_analysis.json' for full details")
    print("="*70)
    print("\n💡 Remember: Options traders who WAIT make money.")
    print("   Don't force trades. Quality > Quantity.\n")


if __name__ == "__main__":
    main()
