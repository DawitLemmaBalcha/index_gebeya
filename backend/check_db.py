from database import SessionLocal
from models import Item
import json

# Connect to DB
db = SessionLocal()

# Fetch the last 5 items
items = db.query(Item).order_by(Item.id.desc()).limit(5).all()

print(f"\n--- 🔍 DATABASE INSPECTION (Latest Entries) ---")

if not items:
    print("❌ No items found in the database.")
else:
    for item in items:
        print(f"\n🆔 [ID: {item.id}] {item.item_name}")
        print(f"   💰 Price:      {item.price} {item.currency}")
        print(f"   📂 Category:   {item.category}") 
        print(f"   ⭐️ Subcat:     {item.subcategory}")
        print(f"   📍 Location:   {item.location}")
        print(f"   📞 Phone:      {item.contact_phone}")
        print(f"   🧩 Metadata:   {json.dumps(item.item_metadata)}")
        print(f"   📸 Image Path: {item.image_path}")

print("\n----------------------------------------------------")