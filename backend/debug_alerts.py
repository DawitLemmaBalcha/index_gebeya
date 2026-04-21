import sys
import os
from sqlalchemy import select
import numpy as np

sys.path.append('/app')
from database import SessionLocal
from models import Alert, Item
from ai_engine.matcher import evaluate_match, MatchTier

def debug_matches():
    db = SessionLocal()
    try:
        items = db.scalars(select(Item).order_by(Item.id.desc()).limit(5)).all()
        alerts = db.scalars(select(Alert).where(Alert.is_active == True)).all()

        print(f"\n🔍 DEBUGGING MATCHING LOGIC (HYBRID)")
        
        for item in items:
            if item.image_vector is None: continue

            item_vec = item.image_vector
            if hasattr(item_vec, "tolist") or isinstance(item_vec, np.ndarray): 
                item_vec = list(item_vec)

            print(f"📦 ITEM: '{item.title}'")

            for alert in alerts:
                alert_vec = alert.query_vector
                if hasattr(alert_vec, "tolist") or isinstance(alert_vec, np.ndarray): 
                    alert_vec = list(alert_vec)

                # RUN MATCHER WITH TEXT
                res = evaluate_match(
                    item_vector=item_vec,
                    alert_vector=alert_vec,
                    item_price=item.price,
                    alert_max_price=alert.max_price,
                    item_title=item.title,
                    alert_query_text=alert.query_text # <--- KEY CHANGE
                )

                if res.tier != MatchTier.MISS:
                    print(f"   ✅ MATCH! {res.tier.name} (Score: {res.score:.4f})")
                else:
                    print(f"   ❌ MISS.  (Score: {res.score:.4f})")
            print("-" * 20)
    finally:
        db.close()

if __name__ == "__main__":
    debug_matches()