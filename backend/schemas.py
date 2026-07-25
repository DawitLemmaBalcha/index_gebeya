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

# ----------------------------------------------------------------------
# SEARCH SCHEMAS
# ----------------------------------------------------------------------
class SearchQuery(BaseModel):
    query: str
    limit: int = 20
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    category: Optional[str] = None

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
    is_active: bool
    created_at: datetime
    expires_at: Optional[datetime]
    last_triggered_at: Optional[datetime]
    best_opportunity_score: float

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
    is_active: bool = True

    class Config:
        from_attributes = True


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
    item_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ----------------------------------------------------------------------
# NOTIFICATION SCHEMAS
# ----------------------------------------------------------------------
class NotificationResponse(BaseModel):
    id: int
    user_telegram_id: int
    item: ItemResponse
    alert_id: Optional[int] = None
    match_tier: str
    created_at: datetime

    class Config:
        from_attributes = True