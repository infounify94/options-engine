import yfinance as yf
from datetime import datetime
import json
import sys

def log(msg):
    """Simple logging"""
    print(f"{datetime.now().strftime('%H:%M:%S')} - {msg}")

def get_stock_data(symbol):
    """
    Fetch stock data from Yahoo Finance
    symbol: '^NSEI' for NIFTY, '^NSEBANK' for BANKNIFTY
    """
    try:
        log(f"Fetching data for {symbol}...")
        
        # Get stock object
        stock = yf.Ticker(symbol)
        
        # Get current price
        info = stock.info
        current_price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose', 0)
        
        if not current_price:
            log(f"❌ Could not get price for {symbol}")
            return None
        
        # Get historical data for calculations
        hist = stock.history(period="5d", interval="5m")
        
        if hist.empty:
            log(f"❌ No historical data for {symbol}")
            return None
        
        closes = hist['Close'].tolist()
        
        # Calculate simple moving average (SMA)
        sma_20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else current_price
        
        # Calculate RSI
        rsi = calculate_rsi(closes)
        
        # Calculate momentum
        momentum = ((current_price - closes[-10]) / closes[-10] * 100) if len(closes) >= 10 else 0
        
        log(f"✅ {symbol} - Price: ₹{current_price:.2f}, RSI: {rsi:.2f}, Momentum: {momentum:.2f}%")
        
        return {
            'price': current_price,
            'sma': sma_20,
            'rsi': rsi,
            'momentum': momentum,
            'success': True
        }
        
    except Exception as e:
        log(f"❌ Error fetching {symbol}: {e}")
        return None

def calculate_rsi(prices, period=14):
    """Calculate RSI from price list"""
    if len(prices) < period + 1:
        return 50  # Neutral
    
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

def get_india_vix():
    """Get India VIX from Yahoo Finance"""
    try:
        log("Fetching India VIX...")
        vix = yf.Ticker("^INDIAVIX")
        info = vix.info
        current_vix = info.get('regularMarketPrice') or info.get('previousClose', 0)
        
        if current_vix:
            log(f"✅ India VIX: {current_vix:.2f}")
            return current_vix
        
        log("⚠️ Could not fetch VIX")
        return None
    except Exception as e:
        log(f"⚠️ VIX fetch failed: {e}")
        return None

def analyze_symbol(name, symbol, data):
    """Generate trading signal from data"""
    if not data or not data.get('success'):
        return {
            "side": "ERROR - No Data Available",
            "entry": "",
            "exit": "",
            "time": datetime.now().strftime("%H:%M"),
            "price": "N/A"
        }
    
    price = data['price']
    sma = data['sma']
    rsi = data['rsi']
    momentum = data['momentum']
    
    side = "AVOID"
    entry = ""
    exit = ""
    
    log(f"\n{name} Analysis:")
    log(f"  Price: ₹{price:.2f}")
    log(f"  SMA(20): ₹{sma:.2f}")
    log(f"  RSI: {rsi:.2f}")
    log(f"  Momentum: {momentum:.2f}%")
    
    # Trading logic
    # BULLISH: Price > SMA AND RSI > 50 AND Positive Momentum
    if price > sma and rsi > 50 and momentum > 0.5:
        side = "BUY CALL (CE)"
        entry = f"Above ₹{price:.2f}"
        exit = f"Target ₹{price + 100:.2f}"
        log(f"  ✅ Signal: BUY CALL (Bullish)")
    
    # BEARISH: Price < SMA AND RSI < 50 AND Negative Momentum
    elif price < sma and rsi < 50 and momentum < -0.5:
        side = "BUY PUT (PE)"
        entry = f"Below ₹{price:.2f}"
        exit = f"Target ₹{price - 100:.2f}"
        log(f"  ✅ Signal: BUY PUT (Bearish)")
    
    # NEUTRAL: Conditions not met
    else:
        log(f"  ⚪ Signal: AVOID (Neutral conditions)")
    
    return {
        "side": side,
        "entry": entry,
        "exit": exit,
        "time": datetime.now().strftime("%H:%M"),
        "price": f"₹{price:.2f}",
        "rsi": rsi,
        "momentum": f"{momentum:.2f}%"
    }

def main():
    """Main execution"""
    log("="*60)
    log("🚀 Yahoo Finance Options Engine")
    log(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
    log("="*60)
    
    # Default error result
    result = {
        "nifty": {
            "side": "ERROR - Script Failed",
            "entry": "",
            "exit": "",
            "time": datetime.now().strftime("%H:%M"),
            "price": "N/A"
        },
        "banknifty": {
            "side": "ERROR - Script Failed",
            "entry": "",
            "exit": "",
            "time": datetime.now().strftime("%H:%M"),
            "price": "N/A"
        }
    }
    
    try:
        # Fetch NIFTY (Yahoo symbol: ^NSEI)
        log("\n📊 Analyzing NIFTY...")
        nifty_data = get_stock_data("^NSEI")
        
        # Fetch BANKNIFTY (Yahoo symbol: ^NSEBANK)
        log("\n📊 Analyzing BANKNIFTY...")
        banknifty_data = get_stock_data("^NSEBANK")
        
        # Get VIX
        log("\n📊 Fetching VIX...")
        vix = get_india_vix()
        
        # Generate signals
        result['nifty'] = analyze_symbol("NIFTY", "^NSEI", nifty_data)
        result['banknifty'] = analyze_symbol("BANKNIFTY", "^NSEBANK", banknifty_data)
        
        # Add VIX to both
        if vix:
            result['nifty']['vix'] = vix
            result['banknifty']['vix'] = vix
            
            if vix > 20:
                result['nifty']['side'] += f" | High Volatility (VIX: {vix:.2f})"
                result['banknifty']['side'] += f" | High Volatility (VIX: {vix:.2f})"
                log(f"\n⚠️ HIGH VOLATILITY WARNING: VIX = {vix:.2f}")
        
    except Exception as e:
        log(f"💥 Critical error: {e}")
        import traceback
        traceback.print_exc()
        result['nifty']['error'] = str(e)
        result['banknifty']['error'] = str(e)
    
    # ALWAYS save data.json
    try:
        with open("data.json", "w") as f:
            json.dump(result, f, indent=2)
        
        log("\n" + "="*60)
        log("✅ data.json created successfully")
        log("="*60)
        log("\n📊 RESULTS:")
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        log(f"💥 Could not create data.json: {e}")
        with open("data.json", "w") as f:
            f.write('{"error": "Failed to create results"}')
    
    log("\n✅ Script completed successfully")
    sys.exit(0)

if __name__ == "__main__":
    main()
