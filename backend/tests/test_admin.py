"""
UAT round-2 (FIX 4): sqladmin full CRUD for the monetization tables
(boosts, subscriptions) + the Alert lapse/soft-delete columns.

The admin page itself needs browser auth and is not automatable here —
this module covers the compile check (importing `admin`) and asserts the
new ModelViews are registered by setup_admin with their CRUD flags, plus
the AlertAdmin column additions (read-only display).

FIX 5 (sqladmin create-form gap): sqladmin's ModelConverter._prepare_column
drops PK AND FK columns from forms unless the ModelView sets
`form_include_pk = True`. BoostAdmin/SubscriptionAdmin set it so admins can
enter item/channel/user IDs directly (test-data creation without a real
Stars payment). The deeper tests scaffold the actual create form through
setup_admin (the same path the admin UI uses) and assert the PK + FK
columns render as form fields.
"""

import asyncio

from fastapi import FastAPI

from admin import setup_admin, AlertAdmin, BoostAdmin, SubscriptionAdmin
from models import Alert, Boost, Subscription


def _registered_views(admin):
    """Map model class -> ModelView instance from sqladmin's registered views."""
    return {v.model: v for v in admin.views}


def test_setup_admin_registers_boost_and_subscription_views():
    admin = setup_admin(FastAPI())
    by_model = _registered_views(admin)
    assert Boost in by_model
    assert Subscription in by_model


def test_boost_admin_has_full_crud_flags():
    assert BoostAdmin.can_create is True
    assert BoostAdmin.can_edit is True
    assert BoostAdmin.can_delete is True
    assert BoostAdmin.can_export is True


def test_boost_admin_columns():
    cols = {c.key for c in BoostAdmin.column_list}
    assert cols == {
        "id", "item_id", "channel_id", "user_id", "source",
        "price_paid_stars", "telegram_payment_charge_id",
        "starts_at", "ends_at", "created_at",
    }
    assert {c.key for c in BoostAdmin.column_searchable_list} == {
        "telegram_payment_charge_id"
    }
    assert {c.key for c in BoostAdmin.column_sortable_list} == {
        "id", "ends_at", "created_at"
    }


def test_subscription_admin_has_full_crud_flags():
    assert SubscriptionAdmin.can_create is True
    assert SubscriptionAdmin.can_edit is True
    assert SubscriptionAdmin.can_delete is True
    assert SubscriptionAdmin.can_export is True


def test_subscription_admin_columns():
    cols = {c.key for c in SubscriptionAdmin.column_list}
    assert cols == {
        "id", "user_id", "product", "status",
        "telegram_payment_charge_id", "invoice_payload",
        "current_period_start", "current_period_end", "is_recurring",
        "created_at",
    }
    assert {c.key for c in SubscriptionAdmin.column_searchable_list} == {
        "invoice_payload", "telegram_payment_charge_id"
    }
    assert {c.key for c in SubscriptionAdmin.column_sortable_list} == {
        "id", "created_at", "current_period_end"
    }


def test_alert_admin_exposes_lapse_and_deleted_columns():
    cols = {c.key for c in AlertAdmin.column_list}
    assert "lapsed" in cols
    assert "deleted_at" in cols


def test_alert_admin_flags_not_touched_by_fix4():
    # FIX 4 only ADDS display columns to AlertAdmin — its explicit CRUD
    # configuration (can_export) is untouched; create/edit/delete stay on
    # the sqladmin defaults (the file never overrides them).
    assert AlertAdmin.can_export is True
    assert "can_create" not in AlertAdmin.__dict__
    assert "can_delete" not in AlertAdmin.__dict__


def test_boost_admin_form_include_pk_flag():
    # FIX 5: sqladmin hides PK and FK columns from forms unless
    # form_include_pk is set (forms.ModelConverter._prepare_column gate);
    # admins need to enter item/channel/user IDs directly (test-data
    # creation without a real Stars payment).
    assert BoostAdmin.form_include_pk is True


def test_subscription_admin_form_include_pk_flag():
    # FIX 5: same gate — user_id must be enterable directly on create.
    assert SubscriptionAdmin.form_include_pk is True


def test_boost_admin_create_form_exposes_pk_and_fk_columns():
    # FIX 5 (deeper): scaffold the real create form via setup_admin (the
    # exact path the admin UI uses) and assert the PK + all FK columns
    # render as form fields.
    admin = setup_admin(FastAPI())
    view = _registered_views(admin)[Boost]
    form_cls = asyncio.run(view.scaffold_form())
    fields = set(form_cls()._fields.keys())
    assert {"id", "item_id", "channel_id", "user_id"} <= fields


def test_subscription_admin_create_form_exposes_pk_and_user_id():
    # FIX 5 (deeper): the subscription create form must expose id + user_id.
    admin = setup_admin(FastAPI())
    view = _registered_views(admin)[Subscription]
    form_cls = asyncio.run(view.scaffold_form())
    fields = set(form_cls()._fields.keys())
    assert {"id", "user_id"} <= fields
