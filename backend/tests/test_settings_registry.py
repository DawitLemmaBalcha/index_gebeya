"""
NB-49: the settings registry — effective-config resolution
(DB row → env var → constant default), cast validation, fail-open reads.
"""
import pytest
from sqlalchemy import select

from database import engine
from models import AdminSetting
from services.settings_registry import REGISTRY, get_setting, list_settings, set_setting


class TestGetSetting:
    def test_db_row_overrides_env_value(self, db_session, monkeypatch):
        monkeypatch.setenv("ALERT_MAX_PER_USER", "50")
        set_setting(db_session, "max_alerts_per_user", "7")
        assert get_setting(db_session, "max_alerts_per_user") == 7

    def test_no_db_row_reads_env_value(self, db_session, monkeypatch):
        monkeypatch.setenv("ALERT_MAX_PER_USER", "42")
        assert get_setting(db_session, "max_alerts_per_user") == 42

    def test_no_db_row_no_env_uses_constant_default(self, db_session, monkeypatch):
        monkeypatch.delenv("ALERT_MAX_PER_USER", raising=False)
        assert get_setting(db_session, "max_alerts_per_user") == 20

    def test_monetization_enabled_defaults_true(self, db_session, monkeypatch):
        monkeypatch.delenv("MONETIZATION_ENABLED", raising=False)
        assert get_setting(db_session, "monetization_enabled") is True

    def test_bool_casting_from_db_row(self, db_session):
        set_setting(db_session, "monetization_enabled", "false")
        assert get_setting(db_session, "monetization_enabled") is False
        set_setting(db_session, "monetization_enabled", "1")
        assert get_setting(db_session, "monetization_enabled") is True

    def test_int_casting_from_db_row(self, db_session):
        set_setting(db_session, "all_in_one_price_stars", "120")
        assert get_setting(db_session, "all_in_one_price_stars") == 120

    def test_missing_table_fails_open_to_env_default(self, db_session, monkeypatch):
        # Console-table migration failure must never crash the marketplace:
        # reads fall back to the env default (blueprint §6).
        monkeypatch.setenv("ALERT_MAX_PER_USER", "33")
        AdminSetting.__table__.drop(bind=engine)
        try:
            assert get_setting(db_session, "max_alerts_per_user") == 33
        finally:
            AdminSetting.__table__.create(bind=engine)

    def test_ad_hoc_key_uses_provided_defaults(self, db_session, monkeypatch):
        monkeypatch.setenv("SOME_FUTURE_KNOB", "9")
        assert get_setting(db_session, "some_future_knob", env_default=5, cast=int) == 9


class TestSetSetting:
    def test_upsert_same_key_twice_yields_one_row(self, db_session):
        set_setting(db_session, "stale_item_days", "10")
        set_setting(db_session, "stale_item_days", "12")
        rows = db_session.execute(
            select(AdminSetting).where(AdminSetting.key == "stale_item_days")
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].value == "12"
        assert rows[0].source == "db"
        assert rows[0].type == "int"

    def test_unknown_key_rejected(self, db_session):
        with pytest.raises(ValueError):
            set_setting(db_session, "not_a_real_key", "x")

    def test_invalid_int_value_raises_before_write(self, db_session):
        with pytest.raises(ValueError):
            set_setting(db_session, "stale_item_days", "not-a-number")
        assert db_session.scalar(
            select(AdminSetting).where(AdminSetting.key == "stale_item_days")
        ) is None


class TestListSettings:
    def test_lists_all_registered_keys_with_live_value_and_source(self, db_session, monkeypatch):
        monkeypatch.delenv("ALERT_MAX_PER_USER", raising=False)
        monkeypatch.delenv("ALL_IN_ONE_PRICE_STARS", raising=False)
        set_setting(db_session, "max_alerts_per_user", "7")
        rows = list_settings(db_session)
        by_key = {r["key"]: r for r in rows}
        assert len(rows) == len(REGISTRY)
        # every row carries the four contract fields
        for r in rows:
            assert {"key", "type", "value", "source", "description"} <= set(r.keys())
        assert by_key["max_alerts_per_user"]["value"] == 7
        assert by_key["max_alerts_per_user"]["source"] == "db"
        assert by_key["max_alerts_per_user"]["type"] == "int"
        # no DB row -> env source (live value = constant default)
        assert by_key["all_in_one_price_stars"]["source"] == "env"
        assert by_key["all_in_one_price_stars"]["value"] == 100

    def test_works_without_explicit_session(self, db_session, monkeypatch):
        # Route contract: GET /ops/settings calls list_settings() with no args.
        monkeypatch.delenv("ALERT_MAX_PER_USER", raising=False)
        rows = list_settings()
        assert len(rows) == len(REGISTRY)
