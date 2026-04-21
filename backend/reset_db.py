from database import engine, Base
from models import Item

print("🗑️  Dropping all tables...")
Base.metadata.drop_all(bind=engine)
print("✨ Creating new schema...")
Base.metadata.create_all(bind=engine)
print("✅ Database reset complete!")