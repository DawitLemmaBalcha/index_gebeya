import os
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import Response
import base64

from database import engine
from models import User, UserInteraction, Alert, Notification, Channel, Review, Item, ItemImage


# ---------------------------------------------------------------------------
# Authentication — simple username/password via env vars
# ---------------------------------------------------------------------------
class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        expected_user = os.getenv("ADMIN_USERNAME", "admin")
        expected_pass = os.getenv("ADMIN_PASSWORD", "indexgebeya")
        if username == expected_user and password == expected_pass:
            request.session.update({"token": "authenticated"})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        token = request.session.get("token")
        return token == "authenticated"


# ---------------------------------------------------------------------------
# Model Views — one per table, full CRUD
# ---------------------------------------------------------------------------
class UserAdmin(ModelView, model=User):
    column_list = [User.id, User.telegram_id, User.username, User.first_name, User.created_at]
    column_searchable_list = [User.username, User.first_name]
    column_sortable_list = [User.id, User.created_at]
    can_create = True
    can_edit = True
    can_delete = True
    can_export = True
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-user"


class UserInteractionAdmin(ModelView, model=UserInteraction):
    column_list = [UserInteraction.id, UserInteraction.user_id, UserInteraction.session_id,
                   UserInteraction.item_id, UserInteraction.interaction_type, UserInteraction.created_at]
    column_searchable_list = [UserInteraction.interaction_type]
    column_sortable_list = [UserInteraction.id, UserInteraction.created_at]
    can_export = True
    name = "Interaction"
    name_plural = "Interactions"
    icon = "fa-solid fa-chart-line"


class AlertAdmin(ModelView, model=Alert):
    column_list = [Alert.id, Alert.user_id, Alert.query_text, Alert.max_price,
                   Alert.is_active, Alert.created_at, Alert.expires_at, Alert.last_triggered_at]
    column_searchable_list = [Alert.query_text]
    column_sortable_list = [Alert.id, Alert.created_at, Alert.best_opportunity_score]
    can_export = True
    name = "Alert"
    name_plural = "Alerts"
    icon = "fa-solid fa-bell"


class NotificationAdmin(ModelView, model=Notification):
    column_list = [Notification.id, Notification.user_id, Notification.item_id,
                   Notification.alert_id, Notification.match_tier, Notification.match_score,
                   Notification.status, Notification.created_at, Notification.sent_at]
    column_searchable_list = [Notification.status]
    column_sortable_list = [Notification.id, Notification.created_at]
    can_export = True
    name = "Notification"
    name_plural = "Notifications"
    icon = "fa-solid fa-envelope"


class ChannelAdmin(ModelView, model=Channel):
    column_list = [Channel.id, Channel.username, Channel.title, Channel.trust_score,
                   Channel.review_count, Channel.is_verified, Channel.created_at,
                   Channel.photo_file_id]
    column_searchable_list = [Channel.username, Channel.title]
    column_sortable_list = [Channel.id, Channel.trust_score, Channel.review_count, Channel.created_at]
    can_create = True
    can_edit = True
    can_delete = True
    can_export = True
    name = "Channel"
    name_plural = "Channels"
    icon = "fa-solid fa-store"


class ReviewAdmin(ModelView, model=Review):
    column_list = [Review.id, Review.channel_id, Review.user_id, Review.rating,
                   Review.comment, Review.user_photo_url, Review.created_at]
    column_searchable_list = [Review.comment]
    column_sortable_list = [Review.id, Review.rating, Review.created_at]
    can_export = True
    name = "Review"
    name_plural = "Reviews"
    icon = "fa-solid fa-star"


class ItemAdmin(ModelView, model=Item):
    column_list = [Item.id, Item.title, Item.price, Item.currency, Item.category,
                   Item.subcategory, Item.channel_id, Item.created_at]
    column_searchable_list = [Item.title, Item.description, Item.category, Item.subcategory]
    column_sortable_list = [Item.id, Item.price, Item.created_at]
    can_create = True
    can_edit = True
    can_delete = True
    can_export = True
    name = "Item"
    name_plural = "Items"
    icon = "fa-solid fa-box"


class ItemImageAdmin(ModelView, model=ItemImage):
    column_list = [ItemImage.id, ItemImage.item_id, ItemImage.image_path]
    column_sortable_list = [ItemImage.id]
    can_create = True
    can_edit = True
    can_delete = True
    can_export = True
    name = "Item Image"
    name_plural = "Item Images"
    icon = "fa-solid fa-image"


# ---------------------------------------------------------------------------
# Setup helper
# ---------------------------------------------------------------------------
def setup_admin(app):
    """Attach SQLAdmin to the FastAPI app."""
    auth_backend = AdminAuth(secret_key=os.getenv("ADMIN_SECRET_KEY", "change-me-in-production"))
    admin = Admin(
        app,
        engine,
        authentication_backend=auth_backend,
        title="Index Gebeya Admin",
        base_url="/admin",
        templates_dir="/app/templates",
    )
    # Register all model views
    admin.add_view(UserAdmin)
    admin.add_view(UserInteractionAdmin)
    admin.add_view(AlertAdmin)
    admin.add_view(NotificationAdmin)
    admin.add_view(ChannelAdmin)
    admin.add_view(ReviewAdmin)
    admin.add_view(ItemAdmin)
    admin.add_view(ItemImageAdmin)

    return admin
