from pydantic import BaseModel, field_validator
from typing import Optional, Union, Dict, Any, List
from datetime import datetime

# ----------------------------------------------------------------------
# CHANNEL SCHEMAS
# ----------------------------------------------------------------------
class ChannelBase(BaseModel):
    username: str
    title: Optional[str] = None
    trust_score: float = 0.0
    is_verified: bool = False

class ChannelResponse(ChannelBase):
    id: int
    review_count: int
    photo_file_id: Optional[str] = None

    class Config:
        from_attributes = True


class ChannelUpsert(BaseModel):
    username: str
    title: Optional[str] = None
    registered_by: Optional[int] = None
    telegram_id: Optional[int] = None


# ----------------------------------------------------------------------
# REVIEW SCHEMAS
# ----------------------------------------------------------------------
class ReviewCreate(BaseModel):
    channel_id: int
    rating: int          # 1 to 5
    comment: Optional[str] = None
    init_data: str       

class ReviewResponse(BaseModel):
    id: int
    channel_id: int
    user_id: int
    rating: int
    comment: Optional[str]
    user_photo_url: Optional[str] = None
    user_name: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

# ----------------------------------------------------------------------
# ITEM SCHEMAS
# ----------------------------------------------------------------------
class ItemBase(BaseModel):
    title: Optional[str] = None
    original_caption: Optional[str] = None
    description: Optional[str] = None # 👈 The Critical Fix
    price: Optional[float] = None
    currency: str = "ETB"
    phone_number: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    specs: Optional[Dict[str, Any]] = None
    # TECH-22: Item lifecycle status
    status: Optional[str] = "active"

class ItemCreate(ItemBase):
    telegram_message_id: int
    channel_username: str  
    image_path: Optional[str] = None

class ItemResponse(ItemBase):
    id: int
    image_path: Optional[str] = None 
    created_at: datetime
    channel: ChannelResponse 
    images: List[str] = [] 
    
    total_score: Optional[float] = 0.0
    relevance_score: Optional[float] = 0.0 

    specs: Union[Dict[str, Any], str, None] = None 

    # TECH-21: Expose soft-delete status
    is_active: bool = True 

    # TECH-22: Item lifecycle status
    status: str = "active"

    # TECH-22: Stale flag (zero interactions after STALE_ITEM_DAYS)
    is_stale: bool = False

    # TECH-22: Crowdsourced report count (injected by route, not in DB model)
    report_count: Optional[int] = None

    @field_validator('images', mode='before')
    @classmethod
    def extract_image_paths(cls, v: Any) -> List[str]:
        if isinstance(v, list):
            paths = []
            for item in v:
                if hasattr(item, 'image_path'):
                    paths.append(item.image_path)
                elif isinstance(item, str):
                    paths.append(item)
            return paths
        return v or []

    class Config:
        from_attributes = True

# ----------------------------------------------------------------------
# INGESTION SCHEMAS
# ----------------------------------------------------------------------
class TelegramPost(BaseModel):
    channel_name: str 
    message_id: int
    text: str
    image_path: Optional[str] = None
    album_paths: List[str] = []

class IngestionResponse(BaseModel):
    status: str
    item_id: Optional[int] = None
    extracted_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    replaced: bool = False

# ----------------------------------------------------------------------
# SEARCH SCHEMAS
# ----------------------------------------------------------------------
class SearchQuery(BaseModel):
    query: str
    limit: int = 20
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    category: Optional[str] = None
    exclude_unpriced: bool = False

class SearchResponse(BaseModel):
    items: List[ItemResponse]
    total: int
    execution_time_ms: float

# ----------------------------------------------------------------------
# ALERT SCHEMAS
# ----------------------------------------------------------------------
class AlertCreate(BaseModel):
    query_text: str
    max_price: Optional[float] = None
    init_data: str 
    preferences: Optional[Dict[str, Any]] = {} 

class AlertResponse(BaseModel):
    id: int
    query_text: str
    max_price: Optional[float] = None
    preferences: Optional[Union[Dict[str, Any], str]] = None
    is_active: bool
    created_at: datetime
    expires_at: Optional[datetime]
    last_triggered_at: Optional[datetime]
    best_opportunity_score: float
    total_matches: int = 0
    bullseye_matches: int = 0

    class Config:
        from_attributes = True

class AlertNotification(BaseModel):
    user_telegram_id: int
    item: ItemResponse
    match_tier: str 
    match_reason: str

# ----------------------------------------------------------------------
# OWNER CHANNEL SCHEMA (TECH-17)
# ----------------------------------------------------------------------
class OwnerChannelResponse(BaseModel):
    id: int
    username: str
    title: Optional[str]
    trust_score: float
    review_count: int
    is_verified: bool
    product_count: int
    indexing_paused: bool = False
    is_active: bool = True

    class Config:
        from_attributes = True


# ----------------------------------------------------------------------
# TECH-19: Channel Management Schemas
# ----------------------------------------------------------------------
class ChannelPauseRequest(BaseModel):
    indexing_paused: bool


class ChannelInfoResponse(BaseModel):
    id: int
    username: str
    registered_by: Optional[int] = None
    indexing_paused: bool
    is_active: bool

    class Config:
        from_attributes = True


class ChannelActionResponse(BaseModel):
    status: str
    message: Optional[str] = None


# ----------------------------------------------------------------------
# MATCH HISTORY SCHEMA (TECH-17)
# ----------------------------------------------------------------------
class MatchHistoryResponse(BaseModel):
    id: int
    alert_id: Optional[int] = None
    alert_query_text: Optional[str] = None
    match_tier: str
    match_score: float
    item_title: Optional[str] = None
    item_price: Optional[float] = None
    item_image_path: Optional[str] = None
    item_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ----------------------------------------------------------------------
# NOTIFICATION SCHEMAS
# ----------------------------------------------------------------------
class NotificationResponse(BaseModel):
    id: int
    user_telegram_id: int
    item: Optional[ItemResponse] = None
    alert_id: Optional[int] = None
    match_tier: str
    message_text: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ----------------------------------------------------------------------
# TECH-22: Sold Report Schemas
# ----------------------------------------------------------------------
class SoldReportCreate(BaseModel):
    init_data: str


class SoldReportResponse(BaseModel):
    id: int
    user_id: int
    item_id: int
    created_at: datetime
    report_count: Optional[int] = None

    class Config:
        from_attributes = True


# ----------------------------------------------------------------------
# TECH-23: Inventory Management Schemas
# ----------------------------------------------------------------------
class ItemUpdateRequest(BaseModel):
    """
    Partial update request for inventory management. All fields optional —
    only provided fields are updated. Use exclude_unset to detect which
    fields were sent vs unset.
    """
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    specs: Optional[Dict[str, Any]] = None


class ItemEditResponse(BaseModel):
    id: int
    item_id: int
    field: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    edited_by: int
    timestamp: datetime

    class Config:
        from_attributes = True


class ItemStatusResponse(BaseModel):
    status: str
    message: str