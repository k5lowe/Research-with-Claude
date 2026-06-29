import os
from dotenv import load_dotenv

load_dotenv()

# Alpaca credentials
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
# Use paper trading base URL to test: https://paper-api.alpaca.markets
# Switch to live: https://api.alpaca.markets
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://api.alpaca.markets")

# Symbols to trade (US stocks)
SYMBOLS = os.getenv("SYMBOLS", "AAPL,MSFT,NVDA").split(",")

# Strategy parameters
EMA_SHORT = int(os.getenv("EMA_SHORT", "9"))
EMA_LONG = int(os.getenv("EMA_LONG", "21"))
RSI_PERIOD = int(os.getenv("RSI_PERIOD", "14"))
RSI_OVERBOUGHT = float(os.getenv("RSI_OVERBOUGHT", "70"))
RSI_OVERSOLD = float(os.getenv("RSI_OVERSOLD", "30"))

# Risk management
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.01"))   # 1% of account per trade
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "0.02"))      # 2% stop loss
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "0.04"))  # 4% take profit (2:1 R/R)
MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", "0.05"))  # 5% max daily loss, then halt

# Bar timeframe for intraday signals
BAR_TIMEFRAME = os.getenv("BAR_TIMEFRAME", "5Min")  # 5-minute bars
LOOKBACK_BARS = int(os.getenv("LOOKBACK_BARS", "50"))

# Trading hours (Eastern time, market hours)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 35   # start 5 min after open to avoid chaotic open
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 45  # stop 15 min before close to avoid end-of-day whipsaws

# Poll interval in seconds
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))
