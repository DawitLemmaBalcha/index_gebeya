from sqlalchemy import text
from database import engine

def migrate_schema():
    print("🔧 Starting Manual Schema Migration...")
    with engine.connect() as conn:
        # 1. Add 'meta_data' column
        try:
            conn.execute(text("ALTER TABLE user_interactions ADD COLUMN meta_data TEXT;"))
            print("✅ Added column 'meta_data'")
        except Exception as e:
            print(f"⚠️ Note: 'meta_data' add failed (check if exists): {e}")
        
        # 2. Make 'item_id' nullable (so we can log searches)
        try:
            conn.execute(text("ALTER TABLE user_interactions ALTER COLUMN item_id DROP NOT NULL;"))
            print("✅ Altered 'item_id' to be nullable")
        except Exception as e:
            print(f"⚠️ Note: 'item_id' alter failed: {e}")
            
        conn.commit()
        print("🚀 Schema aligned successfully.")

if __name__ == "__main__":
    migrate_schema()