"""Regression and audit remediation tests:
1. SQLite PRAGMA foreign_keys = ON
2. Engine bounds check with future-dated database rows (0 <= t < T)
3. Gemini 429 quota exhaustion & 503 transient failure resilience
4. API key and credential sanitization in error messages
5. Ask Pulse fallback to deterministic rules on Gemini error
"""
from datetime import timedelta
import pytest
from app import config, engine, gemini
from app.db import get_conn


def test_sqlite_foreign_keys_enabled():
    """Verify that foreign keys are enabled on every connection."""
    with get_conn() as conn:
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1, "PRAGMA foreign_keys must be ON"


def test_engine_future_date_bounds_regression():
    """Verify engine handles dates beyond config.TODAY safely without IndexError."""
    future_day = (config.TODAY + timedelta(days=10)).isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO stock_daily (phc_id, drug_code, day, closing, dispensed, unmet) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (1, "PCM", future_day, 120.0, 10.0, 0.0),
        )
        conn.execute(
            "INSERT OR REPLACE INTO footfall_daily (phc_id, day, opd, fever) "
            "VALUES (?, ?, ?, ?)",
            (1, future_day, 85, 12),
        )
    try:
        # compute() must not raise IndexError: index X is out of bounds for axis with size T
        res = engine.compute()
        assert res is not None
        assert res["today"] == config.TODAY.isoformat()
        # Verify valid historical days are preserved
        assert len(res["days"]) > 0
    finally:
        with get_conn() as conn:
            conn.execute("DELETE FROM stock_daily WHERE day = ?", (future_day,))
            conn.execute("DELETE FROM footfall_daily WHERE day = ?", (future_day,))
        engine.invalidate()


def test_gemini_parse_report_429_clean_error(monkeypatch):
    """Voice report should return clean user-facing error on 429 quota exhaustion without raw RPC."""
    def fake_gen(*args, **kwargs):
        raise Exception("429 RESOURCE_EXHAUSTED: Quota exceeded for quota metric 'Generate Content Requests per day'")

    monkeypatch.setattr(gemini, "client", lambda: object())
    monkeypatch.setattr(gemini, "_gen_json", fake_gen)

    phc = {"id": 1, "code": "PHC-1", "name": "Test PHC", "district_code": "TVM", "state_code": "KL"}
    with pytest.raises(RuntimeError) as exc_info:
        gemini.parse_report(
            phc=phc, district="Thiruvananthapuram", state="Kerala",
            language="en", audio=b"RIFF" + b"\x00" * 40
        )

    err_msg = str(exc_info.value)
    assert "quota" in err_msg.lower() or "temporarily unavailable" in err_msg.lower()
    assert "RESOURCE_EXHAUSTED" not in err_msg
    assert "Generate Content Requests" not in err_msg


def test_ask_pulse_fallback_on_gemini_429(monkeypatch):
    """Ask Pulse falls back to deterministic rules on Gemini 429 quota exhaustion."""
    class FailingModels:
        def generate_content(self, *args, **kwargs):
            raise Exception("Resource has been exhausted (e.g. check quota). 429 RESOURCE_EXHAUSTED")

    fake_client = type("FakeClient", (), {"models": FailingModels()})()
    monkeypatch.setattr(gemini, "client", lambda: fake_client)

    snapshot = {
        "scope": "Test District",
        "date": "2026-03-31",
        "kpis": {
            "predicted_stockouts": 3,
            "stocked_out_items": 1,
            "outbreak_clusters": 1,
            "recommended_transfers": 2,
            "phcs": 10,
            "phcs_reporting_today": 8,
        },
        "stock_risks": [
            {"phc": "PHC-1 Test", "drug": "Paracetamol", "stock": 10, "days_to_stockout": 2, "status": "critical"}
        ],
        "clusters": [
            {"syndrome": "fever", "district": "Test District", "phcs": ["PHC-1"], "excess_cases": 15}
        ],
    }

    res = gemini.ask("What is the paracetamol stock status?", snapshot)
    assert res["engine"] == "rules-fallback"
    assert "quota" in res["answer"].lower() or "rules" in res["answer"].lower()
    assert "Paracetamol" in res["answer"] or "stock" in res["answer"].lower()


def test_daily_quota_no_repeated_retries(monkeypatch):
    """Daily quota exhaustion must NOT be repeatedly retried."""
    call_count = {"count": 0}

    class FailingModels:
        def generate_content(self, *args, **kwargs):
            call_count["count"] += 1
            raise Exception("429 Quota exceeded for quota metric 'Generate Content Requests per day'")

    fake_client = type("FakeClient", (), {"models": FailingModels()})()
    monkeypatch.setattr(gemini, "client", lambda: fake_client)

    gemini.ask("Any fever outbreak?", {"scope": "Test", "kpis": {}})
    assert call_count["count"] == 1, "Daily quota must NOT be retried"


def test_api_key_redaction_in_errors(monkeypatch):
    """API keys must never be exposed in error messages."""
    monkeypatch.setattr(gemini.config, "GEMINI_API_KEY", "AIzaSySecretFakeApiKey123456")
    err = Exception("Failed with key AIzaSySecretFakeApiKey123456 at endpoint https://generativelanguage.googleapis.com")
    cleaned = gemini._clean_error_message(err)
    assert "AIzaSySecretFakeApiKey123456" not in cleaned
    assert "[REDACTED]" in cleaned or "temporarily unavailable" in cleaned or "service error" in cleaned
