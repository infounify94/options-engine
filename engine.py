import yfinance as yf
from datetime import datetime, timedelta, timezone
import json
import pandas as pd
import numpy as np

"""
OPENING RANGE BREAKOUT (ORB) STRATEGY FOR OPTIONS - MULTI-TRADE VERSION

Core Philosophy:
- Options premium moves on RANGE EXPANSION, not indicators
- Trade up to 10 breakouts per day max (quality > quantity)
- Speed matters more than direction
- No indicator noise - just price levels and volatility

Rules:
1. Opening Range (9:15-9:45) = trap zone
2. Wait for clean break above/below
3. Confirm with ATR expansion
4. Enter only if VIX < 20
5. Use premium-based stops
6. 10-minute cooldown between trades
7. Max 10 trades per day
"""

# ===================== HELPER FUNCTIONS =====================

def get_india_vix():
    """Check if VIX allows options buying"""
    try:
        vix = yf.Ticker("^INDIAVIX")
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
                "value": round(float(current_vix), 2),
                "signal": signal,
                "safe_to_trade": bool(current_vix < 20)
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
        "current": round(float(atr_current), 2) if not pd.isna(atr_current) else None,
        "expanding": bool(atr_current > atr_prev) if not pd.isna(atr_current) and not pd.isna(atr_prev) else False
    }


def get_previous_day_levels(symbol):
    """Get yesterday's high and low"""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="5d", interval="1d")
        
        if len(hist) >= 2:
            prev_day = hist.iloc[-2]
            return {
                "high": round(float(prev_day['High']), 2),
                "low": round(float(prev_day['Low']), 2),
                "close": round(float(prev_day['Close']), 2)
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
    """
    try:
        ticker = yf.Ticker(symbol)
        chain = ticker.option_chain(expiry)
        options = chain.calls if option_type == "CALL" else chain.puts
        
        # Calculate mid price (more accurate than stale lastPrice)
        options['mid'] = (options['bid'] + options['ask']) / 2
        options['price'] = options['mid'].fillna(options['lastPrice'])
        
        # Filter strikes by premium zone AND liquidity
        filtered = options[
            (options['price'] >= premium_min) &
            (options['price'] <= premium_max) &
            (options['volume'] > 50) &
            (options['openInterest'] > 1500)
        ].copy()
        
        if len(filtered) == 0:
            return {
                "strike": None,
                "premium": None,
                "option_type": option_type,
                "oi": None,
                "volume": None,
                "bid_ask_spread": None,
                "error": "No liquid strike in premium zone (₹180-350, vol>50, OI>1500)"
            }
        
        # Prefer highest OI + good volume (liquidity matters)
        filtered['score'] = filtered['openInterest'] * 0.7 + filtered['volume'] * 0.3
        best = filtered.sort_values(by='score', ascending=False).iloc[0]
        
        return {
            "strike": int(best['strike']),
            "premium": round(best['price'], 2),
            "option_type": option_type,
            "oi": int(best['openInterest']),
            "volume": int(best['volume']),
            "bid_ask_spread": round(best['ask'] - best['bid'], 2) if 'ask' in best and 'bid' in best else None,
            "error": None
        }
        
    except Exception as e:
        return {
            "strike": None,
            "premium": None,
            "option_type": option_type,
            "oi": None,
            "volume": None,
            "bid_ask_spread": None,
            "error": f"Could not fetch option chain: {str(e)}"
        }


def get_signal_color(signal, confidence):
    """Helper to add UI color coding"""
    if signal == "WAIT":
        return "gray"
    elif confidence >= 80:
        return "green"
    elif confidence >= 70:
        return "orange"
    else:
        return "yellow"


# ===================== CORE ORB LOGIC - MULTI-TRADE VERSION =====================

def analyze_orb(symbol, step, name, max_trades_per_day=10, cooldown_candles=2):
    """
    Opening Range Breakout Analysis - MULTI-TRADE VERSION
    
    Strategy:
    1. Define opening range (9:15-9:45)
    2. Scan all candles after opening range for breakouts
    3. Check if ATR is expanding (volatility increasing)
    4. Check VIX < 20
    5. Apply 10-min cooldown between trades (2 candles)
    6. Max 10 trades per day
    7. Return list of all valid trades
    """
    
    try:
        ticker = yf.Ticker(symbol)
        
        # Get today's intraday data
        hist = ticker.history(period="1d", interval="5m")
        
        # Check if we got any data
        if len(hist) == 0:
            return {
                "error": f"No data available for {name} - market might be closed or symbol delisted",
                "index": name,
                "status": "NO_DATA",
                "trades": []
            }
        
        # Yahoo index data already in IST — do NOT convert timezone
        try:
            hist.index = hist.index.tz_localize(None)
        except:
            pass
        
        # Filter market hours only
        hist = hist.between_time("09:15", "15:30")
        
        if len(hist) < 10:
            return {
                "error": f"Not enough data for {name} - market might not be open",
                "index": name,
                "status": "NO_DATA",
                "trades": []
            }
        
        current_time = datetime.now()
        
        # ===================== STEP 1: OPENING RANGE =====================
        
        opening_candles = hist.between_time("09:15", "09:45")
        
        if len(opening_candles) < 7:
            return {
                "index": name,
                "status": "WAITING",
                "message": "Opening range not yet formed (wait till 9:45 AM)",
                "time": current_time.strftime("%H:%M:%S IST"),
                "trades": []
            }
        
        orb_high = float(opening_candles['High'].max())
        orb_low = float(opening_candles['Low'].min())
        orb_range = orb_high - orb_low
        
        # Current price from last CLOSED candle
        current_price = float(hist['Close'].iloc[-2])
        
        # Previous day levels
        prev_day = get_previous_day_levels(symbol)
        
        # ATR and VIX data
        atr_data = atr(hist, period=14) or {
            "current": None,
            "expanding": False,
            "error": "Insufficient data for ATR calculation"
        }
        
        vix_data = get_india_vix()
        vix_safe = vix_data["safe_to_trade"]
        
        # ===================== STEP 2: SCAN FOR MULTIPLE BREAKOUTS =====================
        
        trades = []
        cooldown_until = -1  # Track cooldown period
        
        # Start scanning after opening range (index 6 onwards)
        # Use last closed candle, so check up to -2
        for i in range(6, len(hist) - 1):
            # Skip if in cooldown
            if i <= cooldown_until:
                continue
            
            # Check if max trades reached
            if len(trades) >= max_trades_per_day:
                break
            
            candle = hist.iloc[i]
            candle_time = hist.index[i]
            
            # Get previous closed candle for entry
            entry_candle = hist.iloc[i-1]
            entry_price = float(entry_candle['Close'])
            
            breakout = None
            breakout_strength = "NONE"
            distance_from_orb = 0
            
            # ===================== BREAKOUT DETECTION =====================
            
            if candle['Close'] > orb_high:
                # Bullish breakout
                distance_from_orb = candle['Close'] - orb_high
                
                # Check minimum strength
                if distance_from_orb > orb_range * 0.2:
                    breakout = "CALL"
                    
                    if distance_from_orb > orb_range * 0.5:
                        breakout_strength = "STRONG"
                    elif distance_from_orb > orb_range * 0.2:
                        breakout_strength = "MODERATE"
                    
            elif candle['Close'] < orb_low:
                # Bearish breakout
                distance_from_orb = orb_low - candle['Close']
                
                if distance_from_orb > orb_range * 0.2:
                    breakout = "PUT"
                    
                    if distance_from_orb > orb_range * 0.5:
                        breakout_strength = "STRONG"
                    elif distance_from_orb > orb_range * 0.2:
                        breakout_strength = "MODERATE"
            
            if not breakout:
                continue
            
            # ===================== VALIDATION CHECKS =====================
            
            signal = "WAIT"
            confidence = 0
            reasons = []
            
            # Get current hour/min for time check
            candle_hour = candle_time.hour
            candle_min = candle_time.minute
            
            # Late trade warning
            late_trade_warning = False
            if candle_hour >= 14 and breakout_strength != "STRONG":
                late_trade_warning = True
            
            # Validate trade
            if late_trade_warning:
                reasons.append("⏰ After 2 PM and breakout not strong - theta risk too high")
                reasons.append(f"📊 Breakout strength: {breakout_strength}")
                continue
                
            elif not vix_safe:
                reasons.append("⚠️ India VIX too high - options premiums expensive")
                reasons.append(f"📊 VIX: {vix_data['value']} (need < 20)")
                continue
                
            elif breakout_strength == "WEAK":
                reasons.append(f"⚠️ Breakout too weak - only {distance_from_orb:.2f} points")
                continue
                
            elif not atr_data.get("expanding", False):
                reasons.append("⚠️ ATR not expanding - volatility not increasing")
                continue
            
            # ===================== VALID TRADE FOUND =====================
            
            signal = f"BUY {breakout}"
            
            # Confidence based on breakout strength
            if breakout_strength == "STRONG":
                confidence = 85
                reasons.append(f"✅ STRONG {breakout} breakout detected")
            else:  # MODERATE
                confidence = 70
                reasons.append(f"✅ MODERATE {breakout} breakout detected")
            
            reasons.append(f"✅ Broke out of opening range (₹{orb_high:.2f}-₹{orb_low:.2f})")
            reasons.append(f"✅ ATR expanding - volatility increasing")
            reasons.append(f"✅ VIX at {vix_data['value']} - safe to trade")
            
            # Check previous day levels for confluence
            if prev_day:
                if breakout == "CALL" and entry_price > prev_day['high']:
                    confidence += 5
                    reasons.append(f"✅ Also broke yesterday's high (₹{prev_day['high']})")
                elif breakout == "PUT" and entry_price < prev_day['low']:
                    confidence += 5
                    reasons.append(f"✅ Also broke yesterday's low (₹{prev_day['low']})")
            
            # ===================== TARGETS & STOPS =====================
            
            if breakout == "CALL":
                target = orb_high + (orb_range * 1.5)
                stop_loss = orb_high - (orb_range * 0.2)
            else:  # PUT
                target = orb_low - (orb_range * 1.5)
                stop_loss = orb_low + (orb_range * 0.2)
            
            risk_reward = abs(target - entry_price) / abs(entry_price - stop_loss)
            
            # ===================== STRIKE SELECTION =====================
            
            option_symbol = "NIFTY.NS" if name == "NIFTY" else "BANKNIFTY.NS"
            expiry = yahoo_expiry_format(option_symbol)
            
            if not expiry:
                strike_rec = {
                    "strike": None,
                    "premium": None,
                    "option_type": breakout,
                    "error": "No expiry available from Yahoo"
                }
            else:
                strike_rec = get_strike_by_premium(option_symbol, breakout, expiry)
            
            # Time-based exit
            if candle_hour >= 14:
                time_warning = "⚠️ Late in day - consider smaller position or skip"
            else:
                time_warning = "✅ Good time window for entry"
            
            # ===================== BUILD TRADE OBJECT =====================
            
            trade = {
                "trade_number": len(trades) + 1,
                "signal": signal,
                "confidence": confidence,
                "confidence_str": f"{confidence}%",
                
                "entry_time": candle_time.strftime("%H:%M:%S"),
                "entry_price": round(entry_price, 2),
                "entry_price_str": f"₹{entry_price:.2f}",
                
                "breakout_type": breakout,
                "breakout_strength": breakout_strength,
                "strength_score": {"STRONG": 3, "MODERATE": 2, "WEAK": 1}.get(breakout_strength, 0),
                "distance_from_orb": round(distance_from_orb, 2),
                
                "recommended_option": strike_rec,
                
                "trade_plan": {
                    "entry_price": round(entry_price, 2),
                    "spot_target": round(target, 2),
                    "spot_stop": round(stop_loss, 2),
                    "risk_reward_ratio": round(risk_reward, 2),
                    
                    "entry_str": f"₹{entry_price:.2f}",
                    "spot_target_str": f"₹{target:.2f}",
                    "spot_stop_str": f"₹{stop_loss:.2f}",
                    "risk_reward_str": f"1:{risk_reward:.2f}",
                    
                    "premium_target": {
                        "min": 80,
                        "max": 120,
                        "description": "80-120% of premium paid"
                    },
                    "premium_stop": {
                        "value": 35,
                        "description": "30-40% of premium paid"
                    },
                    
                    "time_warning": time_warning,
                    "position_size": "1-2 lots max (risk 2% of capital)",
                    "exit_time": "Exit all positions by 3:15 PM (no overnight)"
                },
                
                "signal_reasons": reasons,
                
                "ui_metadata": {
                    "signal_color": get_signal_color(signal, confidence),
                    "alert_level": "high" if confidence >= 80 else "medium" if confidence >= 70 else "low",
                    "show_notification": True
                }
            }
            
            trades.append(trade)
            
            # Set cooldown
            cooldown_until = i + cooldown_candles
        
        # ===================== SUMMARY OUTPUT =====================
        
        # Prepare timestamp
        utc_time = datetime.now(timezone.utc)
        
        result = {
            "index": name,
            "status": "ACTIVE" if len(trades) > 0 else "NO_SIGNALS",
            "total_trades": len(trades),
            "max_trades_per_day": max_trades_per_day,
            
            "current_price": round(current_price, 2),
            "current_price_str": f"₹{current_price:.2f}",
            
            "expiry": next_expiry(),
            
            "opening_range": {
                "high": round(orb_high, 2),
                "high_str": f"₹{orb_high:.2f}",
                "low": round(orb_low, 2),
                "low_str": f"₹{orb_low:.2f}",
                "size": round(orb_range, 2),
                "size_str": f"₹{orb_range:.2f}"
            },
            
            "previous_day": prev_day,
            
            "volatility": {
                "atr": atr_data,
                "india_vix": vix_data
            },
            
            "trades": trades,
            
            "timestamp": {
                "local": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                "local_tz": "IST",
                "utc": utc_time.isoformat(),
                "unix": int(current_time.timestamp())
            }
        }
        
        # Add summary message if no trades
        if len(trades) == 0:
            result["message"] = "No valid breakout signals yet - opening range established, waiting for breakout"
            result["tip"] = "Options traders who wait make money. Be patient."
        
        return result
        
    except Exception as e:
        return {
            "error": str(e),
            "index": name,
            "status": "ERROR",
            "trades": []
        }


# ===================== PREMIUM-BASED BACKTESTING - MULTI-TRADE VERSION =====================

def backtest_orb_premium_based(symbol, step, name, days_back=20, max_trades_per_day=10, cooldown_candles=2):
    """
    Backtest with PREMIUM-based P&L, not spot-based - MULTI-TRADE VERSION
    
    Key features:
    - Simulates actual option premium movement
    - Accounts for theta decay
    - Only counts fast moves as wins
    - Allows up to 10 trades per day with cooldown
    """
    
    try:
        ticker = yf.Ticker(symbol)
        
        # Fetch data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        # Get daily data to identify trading days
        daily = ticker.history(start=start_date, end=end_date, interval="1d")
        
        if len(daily) == 0:
            return {
                "error": f"No historical data available for {name}",
                "index": name,
                "trades": []
            }
        
        all_trades = []
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
                
                # Yahoo index data already in IST
                try:
                    intraday.index = intraday.index.tz_localize(None)
                except:
                    pass
                
                intraday = intraday.between_time("09:15", "15:30")
                
                if len(intraday) < 10:
                    continue
                
                # Opening range
                orb_candles = intraday.between_time("09:15", "09:45")
                orb_high = orb_candles['High'].max()
                orb_low = orb_candles['Low'].min()
                orb_range = orb_high - orb_low
                
                # Track trades for this day
                day_trades = 0
                cooldown_until = -1
                
                # Check for breakouts (allow multiple per day)
                for i in range(6, len(intraday) - 12):  # Leave 12 candles (1 hour) for move
                    # Skip if in cooldown
                    if i <= cooldown_until:
                        continue
                    
                    # Check if max trades reached for this day
                    if day_trades >= max_trades_per_day:
                        break
                    
                    candle = intraday.iloc[i]
                    entry_price = intraday.iloc[i-1]['Close']
                    
                    breakout = None
                    
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
                            premium_gain = (spot_move / entry_price) * 0.6 - theta_loss
                            
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
                    elif max_profit >= 0.4:  # 40%+ gain
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
                    
                    all_trades.append({
                        "date": str(day_date),
                        "trade_number": day_trades + 1,
                        "type": breakout,
                        "entry": round(float(entry_price), 2),
                        "outcome": outcome,
                        "pnl_pct": round(float(pnl_pct), 2),
                        "pnl_amount": round(float(trade_pnl), 2),
                        "capital_after": round(float(capital), 2)
                    })
                    
                    day_trades += 1
                    
                    # Set cooldown
                    cooldown_until = i + cooldown_candles
                    
            except:
                continue
        
        # Calculate stats
        wins = [t for t in all_trades if t['pnl_pct'] > 0]
        losses = [t for t in all_trades if t['pnl_pct'] <= 0]
        
        avg_win = sum(t['pnl_pct'] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t['pnl_pct'] for t in losses) / len(losses) if losses else 0
        
        win_rate = (len(wins) / len(all_trades) * 100) if all_trades else 0
        total_return = ((capital - 10000) / 10000 * 100)
        expectancy = (win_rate/100 * avg_win + (1-win_rate/100) * avg_loss) if all_trades else 0
        
        # Calculate trades per day stats
        trades_by_day = {}
        for trade in all_trades:
            date = trade['date']
            trades_by_day[date] = trades_by_day.get(date, 0) + 1
        
        avg_trades_per_day = sum(trades_by_day.values()) / len(trades_by_day) if trades_by_day else 0
        max_trades_in_day = max(trades_by_day.values()) if trades_by_day else 0
        
        return {
            "index": name,
            "period": f"{days_back} days",
            "total_trades": len(all_trades),
            "wins": len(wins),
            "losses": len(losses),
            
            "win_rate_pct": round(win_rate, 1),
            "win_rate_str": f"{win_rate:.1f}%",
            
            "avg_win_pct": round(avg_win, 1),
            "avg_win_str": f"{avg_win:.1f}%",
            
            "avg_loss_pct": round(avg_loss, 1),
            "avg_loss_str": f"{avg_loss:.1f}%",
            
            "expectancy_pct": round(expectancy, 2),
            "expectancy_str": f"{expectancy:.2f}%",
            
            "total_return_pct": round(total_return, 2),
            "total_return_str": f"{total_return:.2f}%",
            
            "initial_capital": 10000,
            "final_capital": round(capital, 2),
            "final_capital_str": f"₹{capital:.2f}",
            
            "max_capital": round(max(equity_curve), 2),
            "max_capital_str": f"₹{max(equity_curve):.2f}",
            
            "avg_trades_per_day": round(avg_trades_per_day, 1),
            "max_trades_in_single_day": max_trades_in_day,
            "max_trades_per_day_limit": max_trades_per_day,
            
            "equity_curve": [round(x, 2) for x in equity_curve],
            
            "trades": all_trades,
            
            "note": "Premium-based backtest with theta decay simulation - Multi-trade version"
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "index": name,
            "trades": []
        }


# ===================== MAIN =====================

def main():
    print("\n" + "="*70)
    print("📊 OPENING RANGE BREAKOUT (ORB) ANALYZER - MULTI-TRADE VERSION")
    print("="*70)
    print("⏰ Analyzing current market state...\n")
    print("🔹 Max trades/day: 10")
    print("🔹 Cooldown between trades: 10 minutes (2 candles)")
    print("="*70 + "\n")
    
    # Real-time analysis with multi-trade capability
    nifty = analyze_orb("^NSEI", 50, "NIFTY", max_trades_per_day=10, cooldown_candles=2)
    banknifty = analyze_orb("^NSEBANK", 100, "BANKNIFTY", max_trades_per_day=10, cooldown_candles=2)
    
    # Print summary
    print(f"\n📈 NIFTY 50")
    print("="*70)
    if 'error' in nifty:
        print(f"   Error: {nifty.get('error', 'Unknown error')}")
    else:
        print(f"   Status: {nifty.get('status', 'UNKNOWN')}")
        print(f"   Current Price: {nifty.get('current_price_str', 'N/A')}")
        print(f"   Total Trades Today: {nifty.get('total_trades', 0)}")
        
        if nifty.get('total_trades', 0) > 0:
            print(f"\n   📋 Trade Signals:")
            for trade in nifty.get('trades', []):
                print(f"\n      Trade #{trade['trade_number']} at {trade['entry_time']}")
                print(f"      Signal: {trade['signal']} | Confidence: {trade['confidence_str']}")
                print(f"      Entry: {trade['entry_price_str']} | Strength: {trade['breakout_strength']}")
                if trade['recommended_option'].get('strike'):
                    opt = trade['recommended_option']
                    print(f"      Option: {opt['strike']} {opt['option_type']} @ ₹{opt['premium']}")
                print(f"      Target: {trade['trade_plan']['spot_target_str']} | Stop: {trade['trade_plan']['spot_stop_str']}")
        else:
            print(f"   Message: {nifty.get('message', 'Waiting for signals')}")
    
    print(f"\n\n📊 BANK NIFTY")
    print("="*70)
    if 'error' in banknifty:
        print(f"   Error: {banknifty.get('error', 'Unknown error')}")
    else:
        print(f"   Status: {banknifty.get('status', 'UNKNOWN')}")
        print(f"   Current Price: {banknifty.get('current_price_str', 'N/A')}")
        print(f"   Total Trades Today: {banknifty.get('total_trades', 0)}")
        
        if banknifty.get('total_trades', 0) > 0:
            print(f"\n   📋 Trade Signals:")
            for trade in banknifty.get('trades', []):
                print(f"\n      Trade #{trade['trade_number']} at {trade['entry_time']}")
                print(f"      Signal: {trade['signal']} | Confidence: {trade['confidence_str']}")
                print(f"      Entry: {trade['entry_price_str']} | Strength: {trade['breakout_strength']}")
                if trade['recommended_option'].get('strike'):
                    opt = trade['recommended_option']
                    print(f"      Option: {opt['strike']} {opt['option_type']} @ ₹{opt['premium']}")
                print(f"      Target: {trade['trade_plan']['spot_target_str']} | Stop: {trade['trade_plan']['spot_stop_str']}")
        else:
            print(f"   Message: {banknifty.get('message', 'Waiting for signals')}")
    
    # Only run backtest if we have valid live data
    if 'error' not in nifty and 'error' not in banknifty:
        print("\n" + "="*70)
        print("📊 Running premium-based backtests (multi-trade version)...")
        print("   This may take 60-90 seconds...")
        print("="*70)
        
        nifty_bt = backtest_orb_premium_based("^NSEI", 50, "NIFTY", days_back=20, max_trades_per_day=10)
        banknifty_bt = backtest_orb_premium_based("^NSEBANK", 100, "BANKNIFTY", days_back=20, max_trades_per_day=10)
        
        # Print backtest summary
        print(f"\n📈 NIFTY Backtest Results:")
        if 'error' not in nifty_bt:
            print(f"   Total Trades: {nifty_bt['total_trades']}")
            print(f"   Win Rate: {nifty_bt['win_rate_str']}")
            print(f"   Avg Win: {nifty_bt['avg_win_str']} | Avg Loss: {nifty_bt['avg_loss_str']}")
            print(f"   Total Return: {nifty_bt['total_return_str']}")
            print(f"   Final Capital: {nifty_bt['final_capital_str']}")
            print(f"   Avg Trades/Day: {nifty_bt['avg_trades_per_day']} | Max in Single Day: {nifty_bt['max_trades_in_single_day']}")
        
        print(f"\n📊 BANK NIFTY Backtest Results:")
        if 'error' not in banknifty_bt:
            print(f"   Total Trades: {banknifty_bt['total_trades']}")
            print(f"   Win Rate: {banknifty_bt['win_rate_str']}")
            print(f"   Avg Win: {banknifty_bt['avg_win_str']} | Avg Loss: {banknifty_bt['avg_loss_str']}")
            print(f"   Total Return: {banknifty_bt['total_return_str']}")
            print(f"   Final Capital: {banknifty_bt['final_capital_str']}")
            print(f"   Avg Trades/Day: {banknifty_bt['avg_trades_per_day']} | Max in Single Day: {banknifty_bt['max_trades_in_single_day']}")
    else:
        print("\n" + "="*70)
        print("⚠️  Skipping backtest - no live data available")
        print("="*70)
        nifty_bt = {"error": "Skipped - no live data", "trades": []}
        banknifty_bt = {"error": "Skipped - no live data", "trades": []}
    
    # Compile results
    data = {
        "strategy": "Opening Range Breakout (ORB) - Multi-Trade Version",
        "philosophy": "Premium moves on range expansion, not indicators",
        "multi_trade_config": {
            "max_trades_per_day": 10,
            "cooldown_minutes": 10,
            "cooldown_candles": 2
        },
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
            "Rule 6: Max 10 trades per day with 10-min cooldown",
            "Rule 7: If signal says WAIT, then WAIT",
            "Rule 8: Each breakout must be at least 20% of ORB range"
        ],
        "critical_notes": [
            "Options are NOT indicator-based - they're event-based",
            "Premium only moves on fast breakouts, not slow grinds",
            "Theta decay kills you if move is too slow",
            "Multiple trades/day increases risk - watch position sizing",
            "10-minute cooldown prevents overtrading same breakout",
            "Quality > Quantity even with multiple signals",
            "Paper trade for 2 weeks minimum before going live"
        ],
        "disclaimer": "Educational only. Not financial advice. Trade at your own risk."
    }
    
    # Save
    with open("orb_analysis_multi_trade.json", "w") as f:
        json.dump(data, f, indent=2)
    
    print("\n" + "="*70)
    print("✅ Analysis complete! Check 'orb_analysis_multi_trade.json' for full details")
    print("="*70)
    print("\n💡 Remember: Multiple trades/day = more opportunities BUT also more risk")
    print("   Stick to your rules. Quality > Quantity.\n")


if __name__ == "__main__":
    main()
