"""
NB-49: the audit service — the single mutation path of the ops console.

Rows are never deleted (Rule 1.4); there is no delete path anywhere.
"""
import services.audit as audit_module
from database import SessionLocal
from models import AuditLog
from services.audit import record_audit


class TestRecordAudit:
    def test_writes_row_with_all_fields(self, db_session):
        row = record_audit(
            db_session,
            admin_user="admin",
            action="update_boost_price",
            section="monetization",
            entity_type="boost_price",
            entity_id="Mobile Phones/Android Phones",
            before={"price_stars": 150},
            after={"price_stars": 180},
        )
        assert row.id is not None
        saved = db_session.get(AuditLog, row.id)
        assert saved.admin_user == "admin"
        assert saved.action == "update_boost_price"
        assert saved.section == "monetization"
        assert saved.entity_type == "boost_price"
        assert saved.entity_id == "Mobile Phones/Android Phones"
        assert saved.before == {"price_stars": 150}
        assert saved.after == {"price_stars": 180}
        assert saved.created_at is not None

    def test_before_after_json_round_trips(self, db_session):
        row = record_audit(
            db_session,
            admin_user="a",
            action="x",
            section="s",
            entity_type="t",
            before={"a": [1, 2], "nested": {"k": "v"}, "b": None},
            after=None,
        )
        saved = db_session.get(AuditLog, row.id)
        assert saved.before == {"a": [1, 2], "nested": {"k": "v"}, "b": None}
        assert saved.after is None

    def test_entity_id_is_nullable(self, db_session):
        row = record_audit(
            db_session, admin_user="a", action="x", section="s", entity_type="t"
        )
        saved = db_session.get(AuditLog, row.id)
        assert saved.entity_id is None

    def test_commits_independently_of_the_callers_transaction(self, db_session):
        # A fresh session must see the row — the helper commits on its own,
        # so a failed mutation never produces an audit row and an applied
        # one always does.
        row = record_audit(
            db_session, admin_user="a", action="x", section="s", entity_type="t"
        )
        fresh = SessionLocal()
        try:
            assert fresh.get(AuditLog, row.id) is not None
        finally:
            fresh.close()

    def test_no_delete_path_exists(self):
        # Invariant (Rule 1.4): audit rows are never deleted.
        assert not hasattr(audit_module, "delete_audit")
        assert not hasattr(audit_module, "purge_audit")
        assert not hasattr(audit_module, "clear_audit")
