import requests
from datetime import datetime
import json
import logging
import sys
import time

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# NSE headers to mimic browser
NSE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Referer': 'https://www.nseindia.com/',
    'Connection': 'keep-alive'
}

# Session for NSE (maintains cookies)
nse_session = requests.Session()
nse_session.headers.update(NSE_HEADERS)

def init_nse_session():
    """Initialize NSE session by visiting homepage (gets cookies)"""
    try:
        logger.info("Initializing NSE session...")
        response = nse_session.get('https://www.nseindia.com/', timeout=10)
        logger.info(f"✅ NSE session initialized (Status: {response.status_code})")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to initialize NSE session: {e}")
        return False

def get_nse_option_chain(symbol):
    """
    Get option chain data from NSE
    symbol: 'NIFTY' or 'BANKNIFTY'
    """
    try:
        logger.info(f"Fetching option chain for {symbol}...")
        
        url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
        response = nse_session.get(url, timeout=15)
        
        if response.status_code != 200:
            logger.error(f"❌ NSE returned status {response.status_code}")
            return None
        
        data = response.json()
        logger.info(f"✅ Got option chain data for {symbol}")
        return data
        
    except requests.exceptions.Timeout:
        logger.error(f"⏱️ Timeout fetching {symbol} option chain")
        return None
    except Exception as e:
        logger.error(f"❌ Error fetching {symbol} option chain: {e}")
        return None

def get_nse_quote(symbol):
    """
    Get real-time quote from NSE
    symbol: 'NIFTY' or 'BANKNIFTY'
    """
    try:
        logger.info(f"Fetching quote for {symbol}...")
        
        # Map symbol to NSE format
        nse_symbol_map = {
            'NIFTY': 'NIFTY 50',
            'BANKNIFTY': 'NIFTY BANK'
        }
        
        nse_symbol = nse_symbol_map.get(symbol, symbol)
        url = f"https://www.nseindia.com/api/quote-equity?index={nse_symbol.replace(' ', '%20')}"
        
        response = nse_session.get(url, timeout=15)
        
        if response.status_code != 200:
            logger.error(f"❌ NSE quote returned status {response.status_code}")
            return None
        
        data = response.json()
        logger.info(f"✅ Got quote for {symbol}")
        return data
        
    except Exception as e:
        logger.error(f"❌ Error fetching {symbol} quote: {e}")
        return None

def get_india_vix():
    """Get India VIX from NSE"""
    try:
        logger.info("Fetching India VIX...")
        url = "https://www.nseindia.com/api/allIndices"
        response = nse_session.get(url, timeout=15)
        
        if response.status_code != 200:
            logger.error(f"❌ VIX request returned status {response.status_code}")
            return None
        
        data = response.json()
        
        # Find VIX in the list
        for item in data.get('data', []):
            if item.get('index') == 'INDIA VIX':
                vix = float(item.get('last', 0))
                logger.info(f"✅ India VIX: {vix}")
                return vix
        
        logger.warning("India VIX not found in response")
        return None
        
    except Exception as e:
        logger.error(f"❌ Error fetching VIX: {e}")
        return None

def calculate_rsi(prices, period=14):
    """Calculate RSI from price list"""
    if len(prices) < period + 1:
        return 50  # Default neutral
    
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

def analyze_symbol(symbol):
    """Analyze symbol using NSE data"""
    logger.info(f"\n{'='*60}")
    logger.info(f"Analyzing {symbol}")
    logger.info(f"{'='*60}")
    
    try:
        # Get option chain data
        option_data = get_nse_option_chain(symbol)
        
        if not option_data or 'records' not in option_data:
            logger.error(f"No option data for {symbol}")
            return {
                "side": "ERROR - No Data",
                "entry": "",
                "exit": "",
                "time": datetime.now().strftime("%H:%M"),
                "price": "N/A"
            }
        
        # Extract current price and data
        records = option_data.get('records', {})
        underlying_value = records.get('underlyingValue', 0)
        
        if not underlying_value:
            logger.error(f"No underlying value for {symbol}")
            return {
                "side": "ERROR - No Price",
                "entry": "",
                "exit": "",
                "time": datetime.now().strftime("%H:%M"),
                "price": "N/A"
            }
        
        current_price = float(underlying_value)
        logger.info(f"Current Price: {current_price}")
        
        # Get option chain data for analysis
        data_points = records.get('data', [])
        
        # Calculate Put/Call ratio (PCR)
        total_call_oi = 0
        total_put_oi = 0
        
        for item in data_points[:10]:  # Check near ATM strikes
            ce = item.get('CE', {})
            pe = item.get('PE', {})
            total_call_oi += ce.get('openInterest', 0)
            total_put_oi += pe.get('openInterest', 0)
        
        pcr = round(total_put_oi / total_call_oi, 2) if total_call_oi > 0 else 1.0
        logger.info(f"Put/Call Ratio: {pcr}")
        
        # Simple decision logic based on PCR
        side = "AVOID"
        entry = ""
        exit = ""
        
        # PCR > 1.2 = More puts than calls = Bullish sentiment
        # PCR < 0.8 = More calls than puts = Bearish sentiment
        
        if pcr > 1.2:
            side = "BUY CALL (CE)"
            entry = f"Above {current_price:.2f}"
            exit = f"Target {current_price + 100:.2f}"
            logger.info("✅ Signal: BUY CALL (Bullish - High PCR)")
        elif pcr < 0.8:
            side = "BUY PUT (PE)"
            entry = f"Below {current_price:.2f}"
            exit = f"Target {current_price - 100:.2f}"
            logger.info("✅ Signal: BUY PUT (Bearish - Low PCR)")
        else:
            logger.info("⚪ Signal: AVOID (Neutral PCR)")
        
        # Get VIX for volatility check
        vix = get_india_vix()
        if vix and vix > 20:
            side += f" | High Volatility (VIX: {vix:.2f})"
            logger.warning(f"⚠️ High volatility detected")
        
        return {
            "side": side,
            "entry": entry,
            "exit": exit,
            "time": datetime.now().strftime("%H:%M"),
            "price": f"₹{current_price:.2f}",
            "pcr": pcr,
            "vix": vix if vix else "N/A"
        }
        
    except Exception as e:
        logger.error(f"❌ Error analyzing {symbol}: {e}", exc_info=True)
        return {
            "side": "ERROR",
            "entry": "",
            "exit": "",
            "time": datetime.now().strftime("%H:%M"),
            "error": str(e)
        }

def main():
    """Main execution"""
    logger.info("="*60)
    logger.info("🚀 NSE Options Engine (No API Keys Required)")
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
    logger.info("="*60)
    
    # Initialize NSE session
    if not init_nse_session():
        logger.error("Failed to initialize NSE session")
        # Create error JSON
        result = {
            "nifty": {"side": "ERROR - NSE Connection Failed", "time": datetime.now().strftime("%H:%M")},
            "banknifty": {"side": "ERROR - NSE Connection Failed", "time": datetime.now().strftime("%H:%M")}
        }
    else:
        # Small delay to avoid rate limiting
        time.sleep(1)
        
        # Analyze symbols
        result = {
            "nifty": analyze_symbol("NIFTY"),
        }
        
        time.sleep(2)  # Delay between requests
        
        result["banknifty"] = analyze_symbol("BANKNIFTY")
    
    # Save results
    try:
        with open("data.json", "w") as f:
            json.dump(result, f, indent=2)
        
        logger.info("\n" + "="*60)
        logger.info("📊 Results saved to data.json")
        logger.info("="*60)
        logger.info(json.dumps(result, indent=2))
        logger.info("✅ Engine completed successfully")
        
    except Exception as e:
        logger.critical(f"💥 Could not save data.json: {e}", exc_info=True)
        with open("data.json", "w") as f:
            f.write('{"error": "Failed to save results"}')
    
    sys.exit(0)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.critical(f"💥 Fatal error: {e}", exc_info=True)
        # Still create data.json with error
        with open("data.json", "w") as f:
            json.dump({
                "error": str(e),
                "time": datetime.now().strftime("%H:%M")
            }, f, indent=2)
        sys.exit(0)  # Exit 0 to not fail workflow
