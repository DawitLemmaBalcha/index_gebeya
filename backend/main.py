import os
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from database import engine, Base
from ai_engine.vector_client import initialize_taxonomy_index

# 👇 IMPORT ROUTERS 👇
from api.routes import ingestion, search, items, reviews, alerts, notifications, analytics, feed

# Initialize Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("suq_api")

# --- CUSTOM LOG FILTER ---
class EndpointFilter(logging.Filter):
    """
    Filter out health checks and internal polling from access logs
    to keep the console clean.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("/notifications/pending") == -1

# Apply filter to Uvicorn's access logger
logging.getLogger("uvicorn.access").addFilter(EndpointFilter())
# -------------------------

# Initialize DB
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Teleshop API", version="0.6.0")

# Mount Media
os.makedirs("/app/media/temp", exist_ok=True)
app.mount("/media", StaticFiles(directory="/app/media"), name="media")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    try:
        initialize_taxonomy_index()
        logger.info("✅ Visual Taxonomy Index Initialized")
    except Exception as e:
        logger.error(f"❌ Failed to init Taxonomy Index: {e}")

@app.get("/")
def read_root():
    return {"status": "online", "service": "Teleshop Engine Alpha 0.6.0"}

# INCLUDE ROUTERS
app.include_router(ingestion.router)
app.include_router(search.router, prefix="/search", tags=["Search"])
app.include_router(items.router, prefix="/items", tags=["Items"])
app.include_router(reviews.router, prefix="/reviews", tags=["Reviews"])
app.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
app.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])

# RENAMED FROM /analytics TO /activity
app.include_router(analytics.router, prefix="/activity", tags=["Analytics"]) 

app.include_router(feed.router, prefix="/feed", tags=["Feed"])