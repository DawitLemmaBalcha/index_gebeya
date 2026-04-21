import os
import logging

# LOGGING SETUP
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("SuqListener")

# ENVIRONMENT VARIABLES
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# API CONFIG
# We split the base URL from the specific endpoint to allow flexible calls
# Default internal docker networking: http://api:8000
API_BASE = os.getenv("API_BASE", "http://api:8000")
API_URL = f"{API_BASE}/parse-telegram-post" # Legacy Variable for Worker
ALERTS_API_URL = f"{API_BASE}/alerts/"      # New Variable for Alerts

# EXTERNAL LINKS
WEB_APP_URL = "https://teleshop-et.ddns.net"

MEDIA_DIR = "/app/media"

# TUNING KNOBS (From .env)
# Default to 30s heartbeat and 10 retries if not set
HEARTBEAT_INTERVAL = float(os.getenv("LISTENER_INTERVAL", "30.0"))
MAX_RETRIES_LIMIT = int(os.getenv("LISTENER_MAX_RETRIES", "10"))

# ALBUM BUFFERING
ALBUM_BUFFER_DELAY = 2.0 

# Ensure media directory exists
os.makedirs(MEDIA_DIR, exist_ok=True)