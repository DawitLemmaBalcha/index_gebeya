from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, BigInteger, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from database import Base  # ABSOLUTE IMPORT

# ----------------------------------------------------------------------
# 1. USER & AUTH LAYER
# ----------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    alerts = relationship("Alert", back_populates="user", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="user")
    interactions = relationship("UserInteraction", back_populates="user")
    notifications = relationship("Notification", back_populates="user")


class UserInteraction(Base):
    """Tracks what users look at for the Recommendation Engine"""
    __tablename__ = "user_interactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    session_id = Column(String, nullable=True)
    
    # MODIFIED: Changed to nullable=True to support generic events (e.g., Search)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="SET NULL"), nullable=True)
    
    interaction_type = Column(String, default="view")
    
    # NEW: Contextual payload (JSON string) for the event (e.g., search queries, filter state)
    meta_data = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="interactions")
    item = relationship("Item")


class Alert(Base):
    """Buyer Alert System - Updated for Unified Alert Engine"""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Core Criteria
    query_text = Column(String, nullable=True) # Textual representation of what they wanted
    query_vector = mapped_column(Vector(512))  # The "Idea" they are looking for
    
    # Hard Filters
    min_price = Column(Float, nullable=True)
    max_price = Column(Float, nullable=True)
    
    # Smart Toggles (JSONB)
    # Stores: { "strict_brand": true, "strict_model": true }
    preferences = Column(String, default="{}") 
    
    # State Management
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True) # 👈 NEW: Expiry Date
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)
    
    # The High Water Mark
    best_opportunity_score = Column(Float, default=0.0)

    # Match counters (TECH-20: Alert Guardrails)
    total_matches = Column(Integer, default=0, nullable=False)
    bullseye_matches = Column(Integer, default=0, nullable=False)

    # Relationships
    user = relationship("User", back_populates="alerts")


class Notification(Base):
    """The Mailbox: Stores pending alerts for the Listener to pick up"""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=True)
    
    # Payload Data
    match_tier = Column(String, nullable=False) # "bullseye" or "ring"
    match_score = Column(Float, nullable=False)
    
    # Status
    status = Column(String, default="PENDING") # PENDING, SENT, FAILED
    message_text = Column(Text, nullable=True)  # For system DMs (auto-pause, expiry)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="notifications")
    item = relationship("Item")
    alert = relationship("Alert")


# ----------------------------------------------------------------------
# 2. MARKETPLACE LAYER (Channels & Trust)
# ----------------------------------------------------------------------
class Channel(Base):
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=True)
    username = Column(String, unique=True, index=True, nullable=False)
    title = Column(String, nullable=True)
    
    # Trust System
    trust_score = Column(Float, default=0.0)
    review_count = Column(Integer, default=0)
    is_verified = Column(Boolean, default=False)
    photo_file_id = Column(String, nullable=True)  # Telegram big_file_id for channel profile photo
    registered_by = Column(BigInteger, nullable=True)
    
    # TECH-19: Processing DM lifecycle — pause/resume/remove gates
    indexing_paused = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    items = relationship("Item", back_populates="channel")
    reviews = relationship("Review", back_populates="channel")


class Review(Base):
    __tablename__ = "reviews"
    
    # 1. Prevent Duplicate Reviews
    __table_args__ = (
        UniqueConstraint('user_id', 'channel_id', name='_user_channel_uc'),
    )

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)
    user_photo_url = Column(Text, nullable=True)  # URL to reviewer's Telegram profile photo
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    channel = relationship("Channel", back_populates="reviews")
    user = relationship("User", back_populates="reviews")


# ----------------------------------------------------------------------
# 3. INVENTORY LAYER
# ----------------------------------------------------------------------
class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    
    # Source Info
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    telegram_message_id = Column(Integer, unique=True, index=True)
    
    # Content Data (Source of Truth)
    title = Column(String, nullable=True)         # Extracted/Generated Title
    original_caption = Column(Text, nullable=True) # Raw Telegram Text
    
    # Metadata
    description = Column(String) # AI Summary/Cleaned Description
    price = Column(Float, nullable=True)
    currency = Column(String, default="ETB")
    phone_number = Column(String, nullable=True)
    
    # AI Classification
    category = Column(String, index=True)
    subcategory = Column(String, index=True)
    
    # Structured Specs (JSON)
    specs = Column(String, nullable=True)
    
    # Media (Representative/Thumbnail)
    image_path = Column(String)
    
    # Vector Embeddings
    image_vector = mapped_column(Vector(512))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    channel = relationship("Channel", back_populates="items")
    images = relationship("ItemImage", back_populates="item", cascade="all, delete-orphan")


class ItemImage(Base):
    """Gallery Support: Stores multiple images for a single item"""
    __tablename__ = "item_images"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    image_path = Column(String, nullable=False)
    
    # Relationship
    item = relationship("Item", back_populates="images")