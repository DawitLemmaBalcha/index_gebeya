import logging
from sqlalchemy.orm import Session
from sqlalchemy import or_
from models import Alert, Item, User  # ABSOLUTE IMPORT

logger = logging.getLogger(__name__)

def check_alerts(item: Item, db: Session):
    """
    Sync Alert Matcher (Alpha Version).
    """
    try:
        # 1. Fetch potential matching alerts
        potential_alerts = db.query(Alert).filter(
            Alert.is_active == True,
            or_(Alert.max_price == None, Alert.max_price >= item.price)
        ).all()

        match_count = 0
        
        for alert in potential_alerts:
            # 2. Lexical Matching
            query_terms = alert.search_query.lower().split()
            item_text = (item.description or "").lower() + " " + (item.category or "").lower()
            
            # Check if ALL query terms exist in the item text
            if all(term in item_text for term in query_terms):
                match_count += 1
                notify_user(alert.user, item, alert.search_query)

        if match_count > 0:
            logger.info(f"✨ Item {item.id} triggered {match_count} alerts.")

    except Exception as e:
        logger.error(f"Error in check_alerts: {e}")

def notify_user(user: User, item: Item, query: str):
    """
    Stub for Telegram Notification.
    """
    message = (
        f"🔔 ALERT MATCH for User {user.telegram_id}!\n"
        f"Query: '{query}' matched Item #{item.id}\n"
        f"Price: {item.price} {item.currency}\n"
        f"Channel: @{item.channel.username}\n"
    )
    print("\n" + "="*40)
    print(message)
    print("="*40 + "\n")