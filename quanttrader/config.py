import os
from dotenv import load_dotenv

load_dotenv()

ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')
ALPACA_BASE_URL = os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')

# Position sizing: dollars per order
ORDER_DOLLARS = float(os.getenv('ORDER_DOLLARS', '1000'))

# Risk limits
MAX_DAILY_LOSS = float(os.getenv('MAX_DAILY_LOSS', '0'))  # 0 = disabled
