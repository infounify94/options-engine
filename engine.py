import requests
from datetime import datetime
import json
import sys
import time

# NSE headers to mimic browser
NSE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Referer': 'https://www.nseindia.com/',
    'Connection': 'keep-alive',
    'Cache-Control': 'no-cache'
}

def log(msg):
    """Simple logging"""
    print(f"{datetime.now().strftime('%H:%M:%S')} - {msg}")

def get_nse_data(symbol):
    """Fetch NSE data with multiple attempts"""
    session = requests.Session()
    session.headers.update(NSE_HEADERS)
    
    try:
        # Step 1: Visit homepage to get cookies
        log(f"Initializing NSE session for {symbol}...")
        session.get('https://www.nseindia.com/', timeout=10)
        time.sleep(2)
        
        # Step 2: Get option chain
        log(f"Fetching option chain for {symbol}...")
        url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
        response = session.get(url, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            
            if 'records' in data and 'underlyingValue' in data['records']:
                price = float(data['records']['underlyingValue'])
                log(f"✅ Got {symbol} data - Price: ₹{price}")
                
                # Calculate PCR
                records_data = data['records'].get('data', [])
                total_call_oi = sum(item.get('CE', {}).get('openInterest', 0) for item in records_data[:10])
                total_put_oi = sum(item.get('PE', {}).get('openInterest', 0) for item in records_data[:10])
                pcr = round(total_put_oi / total_call_oi, 2) if total_call_oi > 0 else 1.0
                
                return {'price': price, 'pcr': pcr, 'success': True}
        
        log(f"❌ Failed to get {symbol} data (Status: {response.status_code})")
        return {'success': False}
        
    except Exception as e:
        log(f"❌ Error fetching {symbol}: {e}")
        return {'success': False}

def get_vix():
    """Get India VIX"""
    session = requests.Session()
    session.headers.update(NSE_HEADERS)
    
    try:
        session.get('https://www.nseindia.com/', timeout=10)
        time.sleep(1)
        
        url = "https://www.nseindia.com/api/allIndices"
        response = session.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            for item in data.get('data', []):
                if item.get('index') == 'INDIA VIX':
                    vix = float(item.get('last', 0))
                    log(f"✅ India VIX: {vix}")
                    return vix
    except Exception as e:
        log(f"⚠️ Could not fetch VIX: {e}")
    
    return None

def analyze_symbol(symbol, data):
    """Generate trading signal from data"""
    if not data['success']:
        return {
            "side": "ERROR - No NSE Data",
            "entry": "",
            "exit": "",
            "time": datetime.now().strftime("%H:%M"),
            "price": "N/A"
        }
    
    price = data['price']
    pcr = data['pcr']
    
    side = "AVOID"
    entry = ""
    exit = ""
    
    # PCR-based signals
    if pcr > 1.2:
        side = "BUY CALL (CE)"
        entry = f"Above ₹{price:.2f}"
        exit = f"Target ₹{price + 100:.2f}"
        log(f"✅ {symbol} Signal: BUY CALL (PCR: {pcr})")
    elif pcr < 0.8:
        side = "BUY PUT (PE)"
        entry = f"Below ₹{price:.2f}"
        exit = f"Target ₹{price - 100:.2f}"
        log(f"✅ {symbol} Signal: BUY PUT (PCR: {pcr})")
    else:
        log(f"⚪ {symbol} Signal: AVOID (PCR: {pcr})")
    
    return {
        "side": side,
        "entry": entry,
        "exit": exit,
        "time": datetime.now().strftime("%H:%M"),
        "price": f"₹{price:.2f}",
        "pcr": pcr
    }

def main():
    """Main execution - ALWAYS creates data.json"""
    log("="*60)
    log("🚀 NSE Options Engine Starting")
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
        # Fetch NIFTY
        log("\n📊 Fetching NIFTY data...")
        nifty_data = get_nse_data("NIFTY")
        time.sleep(3)  # Delay between requests
        
        # Fetch BANKNIFTY
        log("\n📊 Fetching BANKNIFTY data...")
        banknifty_data = get_nse_data("BANKNIFTY")
        time.sleep(2)
        
        # Get VIX
        log("\n📊 Fetching VIX...")
        vix = get_vix()
        
        # Generate signals
        result['nifty'] = analyze_symbol("NIFTY", nifty_data)
        result['banknifty'] = analyze_symbol("BANKNIFTY", banknifty_data)
        
        # Add VIX to both
        if vix:
            result['nifty']['vix'] = vix
            result['banknifty']['vix'] = vix
            if vix > 20:
                result['nifty']['side'] += f" | High Volatility (VIX: {vix:.2f})"
                result['banknifty']['side'] += f" | High Volatility (VIX: {vix:.2f})"
        
    except Exception as e:
        log(f"💥 Critical error: {e}")
        result['nifty']['error'] = str(e)
        result['banknifty']['error'] = str(e)
    
    # ALWAYS save data.json (even on complete failure)
    try:
        with open("data.json", "w") as f:
            json.dump(result, f, indent=2)
        log("\n" + "="*60)
        log("✅ data.json created successfully")
        log("="*60)
        print(json.dumps(result, indent=2))
    except Exception as e:
        log(f"💥 Could not create data.json: {e}")
        # Last resort - create minimal file
        with open("data.json", "w") as f:
            f.write('{"error": "Failed to create data.json"}')
    
    log("✅ Script completed")
    sys.exit(0)  # Always exit 0

if __name__ == "__main__":
    main()
