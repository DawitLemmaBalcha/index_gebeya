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
    # passive_deletes=True (user-deletion policy): the DB-level ON DELETE
    # action does the work — without it the ORM pre-nullifies these child FKs
    # on user delete, which violates their NOT NULL columns before the DB acts.
    reviews = relationship("Review", back_populates="user", passive_deletes=True)
    interactions = relationship("UserInteraction", back_populates="user", passive_deletes=True)
    notifications = relationship("Notification", back_populates="user", passive_deletes=True)


class UserInteraction(Base):
    """Tracks what users look at for the Recommendation Engine"""
    __tablename__ = "user_interactions"

    id = Column(Integer, primary_key=True, index=True)
    # user-deletion policy (ADR-0001 pattern): user delete → SET NULL (analytics history survives)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
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
    # user-deletion policy (ADR-0001 pattern): user delete cascades alerts
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
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
    deleted_at = Column(DateTime(timezone=True), nullable=True) # 👈 TECH-25: Soft-delete marker (user-deleted); NULL = never user-deleted
    # NB-46: True = deactivated by subscription lapse (distinct from user pause)
    lapsed = Column(Boolean, default=False, nullable=False)
    
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
    # user-deletion policy (ADR-0001 pattern): user delete cascades notifications
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=True)
    alert_id = Column(Integer, ForeignKey("alerts.id", ondelete="CASCADE"), nullable=True) # TECH-25: alert purge cascades its notifications at the DB level
    
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
    # channel-deletion policy (ADR-0001 pattern): hard admin delete cascades
    # listings/ratings/boosts — the FINAL FK-action sweep. With this change
    # EVERY FK in models.py carries an explicit ondelete action: users (8,
    # a97d1e2), items.item_id CASCADEs, alerts (TECH-25), channels (this).
    # passive_deletes=True: the DB-level ON DELETE CASCADE does the work —
    # without it the ORM pre-nullifies these child FKs on channel delete,
    # which violates their NOT NULL columns before the DB acts (the a97d1e2
    # trap). boosts intentionally have NO Channel-side relationship (services
    # query explicitly) — the mapper is blind, so the DB cascade handles them.
    items = relationship("Item", back_populates="channel", passive_deletes=True)
    reviews = relationship("Review", back_populates="channel", passive_deletes=True)


class Review(Base):
    __tablename__ = "reviews"
    
    # 1. Prevent Duplicate Reviews
    __table_args__ = (
        UniqueConstraint('user_id', 'channel_id', name='_user_channel_uc'),
    )

    id = Column(Integer, primary_key=True, index=True)
    # channel-deletion policy (ADR-0001 pattern): hard admin delete cascades ratings
    channel_id = Column(Integer, ForeignKey("channels.id", ondelete="CASCADE"), nullable=False)
    # user-deletion policy (ADR-0001 pattern): user delete cascades reviews
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
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
    # channel-deletion policy (ADR-0001 pattern): hard admin delete cascades listings
    channel_id = Column(Integer, ForeignKey("channels.id", ondelete="CASCADE"), nullable=False)
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
    
    # Dedup flag — set when item replaces a previous listing (soft-deleted)
    is_dedup = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Soft-delete (TECH-21: dedup now soft-deletes + creates replacement)
    is_active = Column(Boolean, default=True, nullable=False)

    # TECH-22: Item lifecycle status (active, sold, reported_sold, soft_deleted, removed, stale)
    status = Column(String, default="active", nullable=False)

    # TECH-22: Stale flag for items with zero interactions after STALE_ITEM_DAYS
    is_stale = Column(Boolean, default=False, nullable=False)

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


class SoldReport(Base):
    """TECH-22: Crowdsourced sold-reporting — one report per user per item."""
    __tablename__ = "sold_reports"
    __table_args__ = (
        UniqueConstraint('user_id', 'item_id', name='_user_item_sold_report_uc'),
    )

    id = Column(Integer, primary_key=True, index=True)
    # user-deletion policy (ADR-0001 pattern): user delete cascades sold_reports
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User")
    item = relationship("Item")


class ItemEdit(Base):
    """TECH-23: Edit history audit log for inventory management."""
    __tablename__ = "item_edits"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    field = Column(String, nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    # user-deletion policy (ADR-0001 pattern): user delete cascades item_edits (edited_by)
    edited_by = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    item = relationship("Item")
    editor = relationship("User")


# ----------------------------------------------------------------------
# 4. MONETIZATION LAYER (NB-43..NB-47)
# ----------------------------------------------------------------------
class Boost(Base):
    """NB-43/44: One-time 7-day top placement purchase, paid in Stars or
    consumed from an all-in-one subscription's monthly credit.

    One table for both sources — `source='paid'|'credit'`; placement queries
    never filter on source (credit boosts are placement-indistinguishable).
    `telegram_payment_charge_id` is the idempotency key: unique, NULL for
    credit boosts (Postgres treats NULLs as distinct, so multiple credit
    boosts coexist). No relationships — services query explicitly.
    """
    __tablename__ = "boosts"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True)
    # channel-deletion policy (ADR-0001 pattern): hard admin delete cascades boosts
    channel_id = Column(Integer, ForeignKey("channels.id", ondelete="CASCADE"), nullable=False)
    # user-deletion policy (ADR-0001 pattern): user delete cascades boosts
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source = Column(String, nullable=False, default="paid")
    price_paid_stars = Column(Integer, nullable=True)  # NULL for credit boosts
    telegram_payment_charge_id = Column(String, nullable=True, unique=True)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Subscription(Base):
    """NB-46: Native 30-day auto-renewing Star subscription (alerts_only or
    all_in_one). One row per user in v1; renewals update the same row's
    period_end. `telegram_payment_charge_id` is the idempotency key (unique).
    """
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    # user-deletion policy (ADR-0001 pattern): user delete cascades subscriptions
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active")
    telegram_payment_charge_id = Column(String, nullable=True, unique=True)
    invoice_payload = Column(String, nullable=False)
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    is_recurring = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())