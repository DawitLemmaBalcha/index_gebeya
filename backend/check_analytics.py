from database import SessionLocal
from models import UserInteraction
import json

def verify_log():
    db = SessionLocal()
    try:
        # Get the most recent interaction
        last_interaction = db.query(UserInteraction).order_by(UserInteraction.created_at.desc()).first()
        
        if last_interaction:
            print("\n✅ VERIFICATION SUCCESS")
            print(f"ID: {last_interaction.id}")
            print(f"Type: {last_interaction.interaction_type}")
            print(f"User ID: {last_interaction.user_id}")
            print(f"Session: {last_interaction.session_id}")
            print(f"Metadata: {last_interaction.meta_data}")
            print(f"Timestamp: {last_interaction.created_at}")
            
            # Verify generic metadata structure
            if last_interaction.meta_data:
                data = json.loads(last_interaction.meta_data)
                if "query" in data and data["query"] == "iphone":
                    print("✅ Metadata integrity verified.")
                else:
                    print("⚠️ Metadata content mismatch (Check input).")
        else:
            print("\n❌ VERIFICATION FAILED: No interactions found in database.")
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    verify_log()