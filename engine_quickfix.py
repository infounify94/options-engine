import requests
import statistics
from datetime import datetime
import json
import logging
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

TWELVE_KEY = "1e88d174b30146ceb4b18045710afcfc"
NEWS_KEY = "dfbfbb2c1046406997fc9284575e5487"

def safe_request(url, description):
    """Make a safe API request with error handling"""
    try:
        logger.info(f"Fetching {description}...")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Check for API errors
        if isinstance(data, dict) and data.get("status") == "error":
            logger.error(f"API error: {data.get('message', 'Unknown error')}")
            return None
            
        logger.info(f"✅ {description} fetched successfully")
        return data
    except requests.exceptions.Timeout:
        logger.error(f"⏱️ Timeout fetching {description}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Request failed for {description}: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"❌ Invalid JSON for {description}: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected error fetching {description}: {e}")
        return None

def get_price(symbol):
    """Get price data with error handling"""
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=5min&outputsize=50&apikey={TWELVE_KEY}"
    r = safe_request(url, f"price data for {symbol}")
    
    if not r:
        logger.error(f"No response for {symbol} price")
        return None
    
    # Check if 'values' key exists
    if "values" not in r:
        logger.error(f"No 'values' key in response for {symbol}. Keys: {list(r.keys())}")
        return None
    
    values = r["values"]
    if not values or len(values) == 0:
        logger.error(f"Empty values array for {symbol}")
        return None
    
    # Extract closes safely
    try:
        closes = [float(x["close"]) for x in values if "close" in x]
        if not closes:
            logger.error(f"No valid close prices for {symbol}")
            return None
        logger.info(f"Got {len(closes)} prices for {symbol}, latest: {closes[-1]}")
        return closes
    except (KeyError, ValueError, TypeError) as e:
        logger.error(f"Error parsing closes for {symbol}: {e}")
        return None

def get_indicator(symbol, indicator):
    """Get technical indicator with error handling"""
    url = f"https://api.twelvedata.com/{indicator}?symbol={symbol}&interval=5min&apikey={TWELVE_KEY}"
    r = safe_request(url, f"{indicator} for {symbol}")
    
    if not r:
        return None
    
    # Check if 'values' key exists
    if "values" not in r:
        logger.error(f"No 'values' key in {indicator} response for {symbol}. Keys: {list(r.keys())}")
        return None
    
    values = r["values"]
    if not values or len(values) == 0:
        logger.error(f"Empty values for {indicator} on {symbol}")
        return None
    
    key = indicator.lower()
    if key not in values[0]:
        logger.error(f"Key '{key}' not found in {indicator} response for {symbol}")
        return None
    
    try:
        value = float(values[0][key])
        logger.info(f"{indicator} for {symbol}: {value}")
        return value
    except (ValueError, TypeError) as e:
        logger.error(f"Invalid {indicator} value for {symbol}: {e}")
        return None

def get_vix():
    """Get VIX with error handling"""
    url = f"https://api.twelvedata.com/quote?symbol=INDIAVIX&apikey={TWELVE_KEY}"
    r = safe_request(url, "India VIX")
    
    if not r:
        return None
    
    if "close" not in r:
        logger.error(f"No 'close' key in VIX response. Keys: {list(r.keys())}")
        return None
    
    try:
        value = float(r["close"])
        logger.info(f"India VIX: {value}")
        return value
    except (ValueError, TypeError) as e:
        logger.error(f"Invalid VIX value: {e}")
        return None

def get_news_sentiment():
    """Get news sentiment with error handling"""
    url = f"https://newsapi.org/v2/everything?q=nifty OR banknifty OR rbi OR stock market india&apiKey={NEWS_KEY}"
    r = safe_request(url, "news sentiment")
    
    if not r or "articles" not in r:
        logger.warning("No news data, using neutral sentiment")
        return 0
    
    articles = r["articles"]
    if not articles:
        logger.warning("No articles found, using neutral sentiment")
        return 0
    
    titles = [a.get("title", "").lower() for a in articles[:10] if a.get("title")]
    
    score = 0
    for t in titles:
        if any(w in t for w in ["crash","fall","fear","drop","war","inflation"]):
            score -= 1
        if any(w in t for w in ["rise","growth","profit","gain","bullish","record"]):
            score += 1
    
    logger.info(f"News sentiment: {score} (from {len(titles)} articles)")
    return score

def decision(symbol):
    """Make trading decision with error handling"""
    logger.info(f"\n{'='*60}")
    logger.info(f"Analyzing {symbol}")
    logger.info(f"{'='*60}")
    
    # Fetch all data
    closes = get_price(symbol)
    ema = get_indicator(symbol, "ema")
    rsi = get_indicator(symbol, "rsi")
    macd = get_indicator(symbol, "macd")
    vix = get_vix()
    news = get_news_sentiment()
    
    # Check for missing data
    missing = []
    if not closes: missing.append("price")
    if ema is None: missing.append("EMA")
    if rsi is None: missing.append("RSI")
    if macd is None: missing.append("MACD")
    
    if missing:
        logger.error(f"Missing data for {symbol}: {', '.join(missing)}")
        return {
            "side": f"ERROR - Missing: {', '.join(missing)}",
            "entry": "",
            "exit": "",
            "time": datetime.now().strftime("%H:%M"),
            "error": "API data unavailable"
        }
    
    last = closes[-1]
    side = "AVOID"
    entry = ""
    exit = ""
    
    # Trading logic
    logger.info(f"Price: {last}, EMA: {ema}, RSI: {rsi}, MACD: {macd}, News: {news}")
    
    if last > ema and rsi > 55 and macd > 0 and news >= 0:
        side = "BUY CALL (CE)"
        entry = f"Above {last}"
        exit = f"Near {last + 80}"
        logger.info("✅ Signal: BUY CALL")
    elif last < ema and rsi < 45 and macd < 0 and news <= 0:
        side = "BUY PUT (PE)"
        entry = f"Below {last}"
        exit = f"Near {last - 80}"
        logger.info("✅ Signal: BUY PUT")
    else:
        logger.info("⚪ Signal: AVOID")
    
    if vix and vix > 20:
        side += " | High Volatility"
        logger.warning(f"⚠️ High volatility: VIX = {vix}")
    
    return {
        "side": side,
        "entry": entry,
        "exit": exit,
        "time": datetime.now().strftime("%H:%M")
    }

# Main execution
try:
    logger.info("="*60)
    logger.info("🚀 Starting Options Engine")
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*60)
    
    result = {
        "nifty": decision("NIFTY"),
        "banknifty": decision("BANKNIFTY")
    }
    
    # Save results
    with open("data.json", "w") as f:
        json.dump(result, f, indent=2)
    
    logger.info("\n" + "="*60)
    logger.info("📊 Results saved to data.json")
    logger.info("="*60)
    logger.info(json.dumps(result, indent=2))
    
    # Check if we have any valid results
    has_valid_result = False
    for symbol_result in result.values():
        if "ERROR" not in symbol_result["side"]:
            has_valid_result = True
            break
    
    if not has_valid_result:
        logger.error("❌ All analyses failed!")
        sys.exit(1)
    else:
        logger.info("✅ Engine completed successfully")
        sys.exit(0)
        
except Exception as e:
    logger.critical(f"💥 Fatal error: {e}", exc_info=True)
    sys.exit(1)
