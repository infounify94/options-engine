import requests
import statistics
from datetime import datetime
import json
import logging
import sys
import time
from typing import Optional, Dict, Any, List

# ============================================================================
# CONFIGURATION
# ============================================================================

TWELVE_KEY = "1e88d174b30146ceb4b18045710afcfc"
NEWS_KEY = "dfbfbb2c1046406997fc9284575e5487"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# CUSTOM EXCEPTIONS
# ============================================================================

class APIError(Exception):
    """Raised when API call fails"""
    pass

class DataValidationError(Exception):
    """Raised when data validation fails"""
    pass

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def safe_get(data: Dict, *keys, default=None) -> Any:
    """Safely navigate nested dictionary"""
    result = data
    for key in keys:
        if isinstance(result, dict):
            result = result.get(key)
            if result is None:
                return default
        else:
            return default
    return result if result is not None else default

def retry_request(url: str, max_retries: int = 3, delay: int = 2) -> Optional[Dict]:
    """Make HTTP request with retry logic"""
    for attempt in range(1, max_retries + 1):
        try:
            logger.debug(f"Attempt {attempt}/{max_retries} - Requesting: {url}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Check for API-specific errors
            if "status" in data and data["status"] == "error":
                error_msg = safe_get(data, "message", default="Unknown API error")
                raise APIError(f"API returned error: {error_msg}")
            
            return data
            
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout on attempt {attempt}/{max_retries}")
            if attempt == max_retries:
                raise APIError("Request timed out after all retries")
            time.sleep(delay)
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request failed on attempt {attempt}/{max_retries}: {e}")
            if attempt == max_retries:
                raise APIError(f"Request failed after all retries: {e}")
            time.sleep(delay)
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response: {e}")
            raise APIError(f"Invalid JSON response from API: {e}")
    
    return None

# ============================================================================
# API FUNCTIONS WITH ERROR HANDLING
# ============================================================================

def get_price(symbol: str) -> Optional[List[float]]:
    """Fetch price data with error handling"""
    try:
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=5min&outputsize=50&apikey={TWELVE_KEY}"
        logger.info(f"Fetching price data for {symbol}")
        
        data = retry_request(url)
        if not data:
            logger.error(f"No data returned for {symbol}")
            return None
        
        # Validate response structure
        values = safe_get(data, "values", default=[])
        if not values:
            logger.error(f"No values in response for {symbol}. Response keys: {list(data.keys())}")
            return None
        
        # Extract closes with validation
        closes = []
        for item in values:
            close = safe_get(item, "close")
            if close:
                try:
                    closes.append(float(close))
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid close value: {close}")
                    continue
        
        if not closes:
            logger.error(f"No valid close prices for {symbol}")
            return None
        
        logger.info(f"Successfully fetched {len(closes)} prices for {symbol}")
        return closes
        
    except APIError as e:
        logger.error(f"API error fetching price for {symbol}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching price for {symbol}: {e}", exc_info=True)
        return None

def get_indicator(symbol: str, indicator: str) -> Optional[float]:
    """Fetch technical indicator with error handling"""
    try:
        url = f"https://api.twelvedata.com/{indicator}?symbol={symbol}&interval=5min&apikey={TWELVE_KEY}"
        logger.info(f"Fetching {indicator} for {symbol}")
        
        data = retry_request(url)
        if not data:
            logger.error(f"No data returned for {indicator} on {symbol}")
            return None
        
        # Validate response structure
        values = safe_get(data, "values", default=[])
        if not values or len(values) == 0:
            logger.error(f"No values in {indicator} response for {symbol}")
            return None
        
        key = indicator.lower()
        value = safe_get(values[0], key)
        
        if value is None:
            logger.error(f"Key '{key}' not found in {indicator} response for {symbol}")
            return None
        
        try:
            result = float(value)
            logger.info(f"{indicator} for {symbol}: {result}")
            return result
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid {indicator} value for {symbol}: {value}")
            return None
            
    except APIError as e:
        logger.error(f"API error fetching {indicator} for {symbol}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching {indicator} for {symbol}: {e}", exc_info=True)
        return None

def get_vix() -> Optional[float]:
    """Fetch VIX with error handling"""
    try:
        url = f"https://api.twelvedata.com/quote?symbol=INDIAVIX&apikey={TWELVE_KEY}"
        logger.info("Fetching India VIX")
        
        data = retry_request(url)
        if not data:
            logger.error("No data returned for VIX")
            return None
        
        close = safe_get(data, "close")
        if close is None:
            logger.error(f"No close value in VIX response. Keys: {list(data.keys())}")
            return None
        
        try:
            result = float(close)
            logger.info(f"India VIX: {result}")
            return result
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid VIX value: {close}")
            return None
            
    except APIError as e:
        logger.error(f"API error fetching VIX: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching VIX: {e}", exc_info=True)
        return None

def get_news_sentiment() -> int:
    """Fetch news sentiment with error handling"""
    try:
        url = f"https://newsapi.org/v2/everything?q=nifty OR banknifty OR rbi OR stock market india&apiKey={NEWS_KEY}"
        logger.info("Fetching news sentiment")
        
        data = retry_request(url)
        if not data:
            logger.warning("No news data returned, defaulting to neutral sentiment")
            return 0
        
        articles = safe_get(data, "articles", default=[])
        if not articles:
            logger.warning("No articles in news response, defaulting to neutral sentiment")
            return 0
        
        titles = []
        for article in articles[:10]:
            title = safe_get(article, "title")
            if title:
                titles.append(title.lower())
        
        score = 0
        negative_words = ["crash", "fall", "fear", "drop", "war", "inflation", "concern", "decline"]
        positive_words = ["rise", "growth", "profit", "gain", "bullish", "record", "rally", "surge"]
        
        for title in titles:
            if any(word in title for word in negative_words):
                score -= 1
            if any(word in title for word in positive_words):
                score += 1
        
        logger.info(f"News sentiment score: {score} (from {len(titles)} articles)")
        return score
        
    except APIError as e:
        logger.error(f"API error fetching news: {e}")
        return 0  # Neutral on error
    except Exception as e:
        logger.error(f"Unexpected error fetching news: {e}", exc_info=True)
        return 0  # Neutral on error

# ============================================================================
# DECISION LOGIC WITH ERROR HANDLING
# ============================================================================

def decision(symbol: str) -> Dict[str, str]:
    """Make trading decision with error handling"""
    logger.info(f"{'='*60}")
    logger.info(f"Analyzing {symbol}")
    logger.info(f"{'='*60}")
    
    try:
        # Fetch all data
        closes = get_price(symbol)
        ema = get_indicator(symbol, "ema")
        rsi = get_indicator(symbol, "rsi")
        macd = get_indicator(symbol, "macd")
        vix = get_vix()
        news = get_news_sentiment()
        
        # Validate required data
        missing_data = []
        if closes is None or len(closes) == 0:
            missing_data.append("price data")
        if ema is None:
            missing_data.append("EMA")
        if rsi is None:
            missing_data.append("RSI")
        if macd is None:
            missing_data.append("MACD")
        
        if missing_data:
            logger.error(f"Missing data for {symbol}: {', '.join(missing_data)}")
            return {
                "side": "ERROR - Missing Data",
                "entry": "",
                "exit": "",
                "time": datetime.now().strftime("%H:%M"),
                "error": f"Unable to fetch: {', '.join(missing_data)}"
            }
        
        last = closes[-1]
        side = "AVOID"
        entry = ""
        exit = ""
        
        # Trading logic
        logger.info(f"Last Price: {last}, EMA: {ema}, RSI: {rsi}, MACD: {macd}, News: {news}")
        
        if last > ema and rsi > 55 and macd > 0 and news >= 0:
            side = "BUY CALL (CE)"
            entry = f"Above {last:.2f}"
            exit = f"Near {last + 80:.2f}"
            logger.info(f"Signal: BUY CALL")
        elif last < ema and rsi < 45 and macd < 0 and news <= 0:
            side = "BUY PUT (PE)"
            entry = f"Below {last:.2f}"
            exit = f"Near {last - 80:.2f}"
            logger.info(f"Signal: BUY PUT")
        else:
            logger.info(f"Signal: AVOID (conditions not met)")
        
        if vix and vix > 20:
            side += f" | High Volatility (VIX: {vix:.2f})"
            logger.warning(f"High volatility detected: VIX = {vix:.2f}")
        
        return {
            "side": side,
            "entry": entry,
            "exit": exit,
            "time": datetime.now().strftime("%H:%M")
        }
        
    except Exception as e:
        logger.error(f"Critical error in decision for {symbol}: {e}", exc_info=True)
        return {
            "side": "ERROR",
            "entry": "",
            "exit": "",
            "time": datetime.now().strftime("%H:%M"),
            "error": str(e)
        }

# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main execution with error handling"""
    logger.info("="*60)
    logger.info("Starting Options Engine")
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*60)
    
    symbols = ["NIFTY", "BANKNIFTY"]
    result = {}
    
    success_count = 0
    for symbol in symbols:
        try:
            result[symbol.lower()] = decision(symbol)
            if "ERROR" not in result[symbol.lower()]["side"]:
                success_count += 1
        except Exception as e:
            logger.error(f"Failed to process {symbol}: {e}", exc_info=True)
            result[symbol.lower()] = {
                "side": "CRITICAL ERROR",
                "entry": "",
                "exit": "",
                "time": datetime.now().strftime("%H:%M"),
                "error": str(e)
            }
    
    # Save results
    try:
        with open("data.json", "w") as f:
            json.dump(result, f, indent=2)
        logger.info("Results saved to data.json")
        logger.info(json.dumps(result, indent=2))
    except Exception as e:
        logger.error(f"Failed to save results: {e}", exc_info=True)
        sys.exit(1)
    
    # Summary
    logger.info("="*60)
    logger.info(f"Analysis Complete: {success_count}/{len(symbols)} successful")
    logger.info("="*60)
    
    # Exit with appropriate code
    if success_count == 0:
        logger.error("All analyses failed!")
        sys.exit(1)
    elif success_count < len(symbols):
        logger.warning("Some analyses failed, but continuing...")
        sys.exit(0)  # Or sys.exit(1) if you want to fail on partial success
    else:
        logger.info("All analyses completed successfully!")
        sys.exit(0)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
