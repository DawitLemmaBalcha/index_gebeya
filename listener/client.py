import httpx
from config import API_URL, ALERTS_API_URL, API_BASE, logger

# NEW: Internal Secret Header
INTERNAL_HEADERS = {"X-Internal-Service": "index-listener"}

async def send_to_api(payload: dict) -> bool:
    """Sends payload to Backend API (Ingestion)."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            logger.info(f"🚀 Sending payload for msg #{payload.get('message_id')}...")
            response = await client.post(API_URL, json=payload)
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ SUCCESS: Item #{data.get('item_id')} created.")
                return True
            elif response.status_code == 429:
                logger.warning(f"⏳ API Rate Limit Hit (429).")
                return False
            else:
                logger.error(f"❌ API Error ({response.status_code}): {response.text}")
                return False
        except Exception as e:
            logger.error(f"💥 Client Exception: {e}")
            return False

async def create_alert_api(user_id: int, query_text: str, max_price: float = None, preferences: dict = None) -> bool:
    """Sends Alert Data to Backend API."""
    if preferences is None:
        preferences = {}

    payload = {
        "query_text": query_text,
        "max_price": max_price,
        "init_data": str(user_id),
        "preferences": preferences
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # INJECT HEADER HERE 👇
            response = await client.post(ALERTS_API_URL, json=payload, headers=INTERNAL_HEADERS)
            if response.status_code == 200:
                logger.info(f"✅ Alert Created for User {user_id}")
                return True
            else:
                logger.error(f"❌ Failed to create alert: {response.text}")
                return False
        except Exception as e:
            logger.error(f"💥 Alert Client Exception: {e}")
            return False

async def get_active_alerts(user_id: int) -> list:
    """Fetches active alerts for a user."""
    url = f"{ALERTS_API_URL}?init_data={user_id}"
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # INJECT HEADER HERE 👇
            response = await client.get(url, headers=INTERNAL_HEADERS)
            if response.status_code == 200:
                return response.json()
            return []
        except Exception as e:
            logger.error(f"⚠️ Failed to fetch alerts: {e}")
            return []

async def delete_alert_api(user_id: int, alert_id: int) -> bool:
    """Disables an alert."""
    url = f"{ALERTS_API_URL}{alert_id}?init_data={user_id}"
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # INJECT HEADER HERE 👇
            response = await client.delete(url, headers=INTERNAL_HEADERS)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"⚠️ Failed to delete alert: {e}")
            return False

async def get_pending_notifications():
    """Fetches pending notifications from the Backend."""
    url = f"{API_BASE}/notifications/pending"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(url)
            if response.status_code == 200:
                return response.json()
            return []
        except Exception as e:
            logger.error(f"⚠️ Failed to fetch notifications: {e}")
            return []

async def ack_notification(notification_id: int) -> bool:
    """Marks a notification as SENT in the Backend."""
    url = f"{API_BASE}/notifications/{notification_id}/ack"
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.post(url)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"⚠️ Failed to ACK notification {notification_id}: {e}")
            return False