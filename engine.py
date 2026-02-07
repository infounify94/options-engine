import yfinance as yf
from datetime import datetime, timedelta
import json
import sys
import math

def log(msg):
    """Simple logging"""
    print(f"{datetime.now().strftime('%H:%M:%S')} - {msg}")

def calculate_rsi(prices, period=14):
    """Calculate RSI"""
    if len(prices) < period + 1:
        return 50
    
    gains = []
    losses = []
    
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)

def calculate_support_resistance(prices):
    """Calculate key support and resistance levels"""
    if len(prices) < 20:
        return None, None
    
    recent = prices[-20:]
    high = max(recent)
    low = min(recent)
    current = prices[-1]
    
    # Simple pivot points
    pivot = (high + low + current) / 3
    resistance = (2 * pivot) - low
    support = (2 * pivot) - high
    
    return round(support, 2), round(resistance, 2)

def get_suggested_strikes(current_price, signal_type):
    """Calculate suggested strike prices for options"""
    # Round to nearest 50 or 100 based on index
    if current_price > 50000:  # BANKNIFTY
        base = 100
    else:  # NIFTY
        base = 50
    
    # Round current price to nearest strike
    atm_strike = round(current_price / base) * base
    
    if signal_type == "CALL":
        # For calls: ATM and slightly OTM
        strikes = [
            atm_strike,  # ATM
            atm_strike + base,  # 1 strike OTM
            atm_strike + (2 * base)  # 2 strikes OTM
        ]
    elif signal_type == "PUT":
        # For puts: ATM and slightly OTM
        strikes = [
            atm_strike,  # ATM
            atm_strike - base,  # 1 strike OTM
            atm_strike - (2 * base)  # 2 strikes OTM
        ]
    else:
        strikes = [atm_strike]
    
    return strikes

def calculate_target_stoploss(current_price, signal_type, vix):
    """Calculate target and stop loss based on volatility"""
    # Higher VIX = wider targets
    volatility_multiplier = 1 + (vix / 100) if vix else 1
    
    if current_price > 50000:  # BANKNIFTY
        base_move = 200 * volatility_multiplier
    else:  # NIFTY
        base_move = 100 * volatility_multiplier
    
    if signal_type == "CALL":
        target = current_price + base_move
        stop_loss = current_price - (base_move * 0.5)
    elif signal_type == "PUT":
        target = current_price - base_move
        stop_loss = current_price + (base_move * 0.5)
    else:
        target = current_price
        stop_loss = current_price
    
    return round(target, 2), round(stop_loss, 2)

def get_expiry_suggestion():
    """Suggest option expiry based on current date"""
    today = datetime.now()
    
    # Find next Thursday (weekly expiry)
    days_ahead = 3 - today.weekday()  # Thursday is 3
    if days_ahead <= 0:  # If today is Thursday or later
        days_ahead += 7
    
    next_thursday = today + timedelta(days=days_ahead)
    
    # If less than 2 days to expiry, suggest next week
    if days_ahead < 2:
        next_thursday = next_thursday + timedelta(days=7)
    
    return next_thursday.strftime("%d-%b-%Y")

def analyze_detailed(name, symbol, is_banknifty=False):
    """Detailed analysis with actionable trading recommendations"""
    try:
        log(f"\n{'='*60}")
        log(f"📊 Analyzing {name}")
        log(f"{'='*60}")
        
        # Get data
        stock = yf.Ticker(symbol)
        info = stock.info
        current_price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose', 0)
        
        if not current_price:
            log(f"❌ No price data for {name}")
            return create_error_result(name)
        
        # Get historical data
        hist = stock.history(period="5d", interval="5m")
        
        if hist.empty:
            log(f"❌ No historical data for {name}")
            return create_error_result(name)
        
        closes = hist['Close'].tolist()
        highs = hist['High'].tolist()
        lows = hist['Low'].tolist()
        
        # Calculate indicators
        sma_20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else current_price
        sma_50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else current_price
        rsi = calculate_rsi(closes)
        
        # Momentum
        momentum = ((current_price - closes[-10]) / closes[-10] * 100) if len(closes) >= 10 else 0
        
        # Support and Resistance
        support, resistance = calculate_support_resistance(closes)
        
        # Get VIX
        vix_ticker = yf.Ticker("^INDIAVIX")
        vix_info = vix_ticker.info
        vix = vix_info.get('regularMarketPrice') or vix_info.get('previousClose', 15)
        
        # Volume analysis
        volumes = hist['Volume'].tolist()
        avg_volume = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else volumes[-1]
        current_volume = volumes[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
        
        log(f"Price: ₹{current_price:.2f}")
        log(f"SMA(20): ₹{sma_20:.2f} | SMA(50): ₹{sma_50:.2f}")
        log(f"RSI: {rsi:.2f}")
        log(f"Momentum: {momentum:.2f}%")
        log(f"Support: ₹{support:.2f} | Resistance: ₹{resistance:.2f}")
        log(f"Volume Ratio: {volume_ratio:.2f}x")
        log(f"VIX: {vix:.2f}")
        
        # TRADING DECISION LOGIC
        signal = "AVOID"
        signal_strength = "WEAK"
        action = "No trade recommended"
        strikes = []
        target = current_price
        stop_loss = current_price
        
        # BULLISH CONDITIONS
        bullish_score = 0
        if current_price > sma_20: bullish_score += 1
        if current_price > sma_50: bullish_score += 1
        if rsi > 50 and rsi < 70: bullish_score += 1
        if momentum > 0.3: bullish_score += 1
        if volume_ratio > 1.2: bullish_score += 1
        if current_price > support: bullish_score += 0.5
        
        # BEARISH CONDITIONS
        bearish_score = 0
        if current_price < sma_20: bearish_score += 1
        if current_price < sma_50: bearish_score += 1
        if rsi < 50 and rsi > 30: bearish_score += 1
        if momentum < -0.3: bearish_score += 1
        if volume_ratio > 1.2: bearish_score += 1
        if current_price < resistance: bearish_score += 0.5
        
        log(f"\nBullish Score: {bullish_score}/5.5")
        log(f"Bearish Score: {bearish_score}/5.5")
        
        # DECISION
        if bullish_score >= 3.5:
            signal = "BUY CALL"
            signal_strength = "STRONG" if bullish_score >= 4.5 else "MODERATE"
            action = "Buy Call Options"
            strikes = get_suggested_strikes(current_price, "CALL")
            target, stop_loss = calculate_target_stoploss(current_price, "CALL", vix)
            log(f"✅ BULLISH SIGNAL - {signal_strength}")
            
        elif bearish_score >= 3.5:
            signal = "BUY PUT"
            signal_strength = "STRONG" if bearish_score >= 4.5 else "MODERATE"
            action = "Buy Put Options"
            strikes = get_suggested_strikes(current_price, "PUT")
            target, stop_loss = calculate_target_stoploss(current_price, "PUT", vix)
            log(f"✅ BEARISH SIGNAL - {signal_strength}")
            
        else:
            log(f"⚪ NEUTRAL - Conditions not met for trade")
            strikes = [round(current_price / (100 if is_banknifty else 50)) * (100 if is_banknifty else 50)]
        
        # Expiry suggestion
        expiry = get_expiry_suggestion()
        
        # Risk assessment
        risk_level = "HIGH" if vix > 20 else "MEDIUM" if vix > 15 else "LOW"
        
        # Create result
        result = {
            "signal": signal,
            "strength": signal_strength,
            "action": action,
            "current_price": f"₹{current_price:.2f}",
            "suggested_strikes": strikes,
            "expiry": expiry,
            "entry": {
                "condition": f"Enter when {name} is {'above' if signal == 'BUY CALL' else 'below' if signal == 'BUY PUT' else 'at'} ₹{current_price:.2f}",
                "premium_budget": "2-5% of capital per trade"
            },
            "targets": {
                "target_price": f"₹{target:.2f}",
                "stop_loss": f"₹{stop_loss:.2f}",
                "risk_reward": "1:2"
            },
            "indicators": {
                "rsi": rsi,
                "momentum": f"{momentum:.2f}%",
                "volume_ratio": f"{volume_ratio:.2f}x",
                "support": f"₹{support:.2f}",
                "resistance": f"₹{resistance:.2f}"
            },
            "risk": {
                "level": risk_level,
                "vix": vix,
                "max_loss": "Limited to premium paid",
                "position_size": "1-2 lots for beginners, 3-5 for experienced"
            },
            "confidence": f"{int((max(bullish_score, bearish_score) / 5.5) * 100)}%",
            "time": datetime.now().strftime("%H:%M:%S"),
            "market_context": get_market_context(current_price, sma_20, sma_50, rsi, vix)
        }
        
        return result
        
    except Exception as e:
        log(f"❌ Error analyzing {name}: {e}")
        import traceback
        traceback.print_exc()
        return create_error_result(name)

def get_market_context(price, sma20, sma50, rsi, vix):
    """Provide market context explanation"""
    context = []
    
    if price > sma20 and price > sma50:
        context.append("Strong uptrend")
    elif price < sma20 and price < sma50:
        context.append("Strong downtrend")
    else:
        context.append("Sideways/Consolidation")
    
    if rsi > 70:
        context.append("Overbought (caution)")
    elif rsi < 30:
        context.append("Oversold (potential reversal)")
    
    if vix > 20:
        context.append("High volatility - risky")
    elif vix < 12:
        context.append("Low volatility - stable")
    
    return " | ".join(context)

def create_error_result(name):
    """Create error result"""
    return {
        "signal": "ERROR",
        "strength": "NONE",
        "action": "No data available",
        "current_price": "N/A",
        "suggested_strikes": [],
        "time": datetime.now().strftime("%H:%M:%S"),
        "error": "Unable to fetch market data"
    }

def main():
    """Main execution"""
    log("="*60)
    log("🚀 Advanced Options Trading Engine")
    log(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
    log("="*60)
    
    result = {
        "nifty": analyze_detailed("NIFTY", "^NSEI", is_banknifty=False),
        "banknifty": analyze_detailed("BANKNIFTY", "^NSEBANK", is_banknifty=True),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
        "next_update": "10 minutes"
    }
    
    # Save results
    try:
        with open("data.json", "w", encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        log("\n" + "="*60)
        log("✅ data.json created successfully")
        log("="*60)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
    except Exception as e:
        log(f"💥 Could not create data.json: {e}")
        with open("data.json", "w") as f:
            f.write('{"error": "Failed to create results"}')
    
    log("\n✅ Analysis complete")
    sys.exit(0)

if __name__ == "__main__":
    main()
