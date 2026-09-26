"""Master-audit follow-ups: token expiry, donor-side approval, stable recommendation IDs,
low-confidence reports, overdue dispatch, IVR plausibility, CORS, all-language phrases."""
import base64
import json
import os
import tempfile
import time
from datetime import datetime, timedelta

os.environ.setdefault("PHC_DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import auth, engine, gemini, seed, service  # noqa: E402
from app.db import get_conn  # noqa: E402
from app.main import app  # noqa: E402
from app.phrases import P  # noqa: E402
from app.reference import LANGUAGES  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        seed.seed_database(force=True)
        engine.invalidate()
        yield c
    seed.seed_database(force=True)
    engine.invalidate()


def login(client, persona):
    tok = client.post("/api/auth/login", json={"persona_id": persona}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _signed(claims):
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode()
    return {"Authorization": f"Bearer {body}.{auth._sign(body.encode())}"}


def test_tokens_expire(client):
    p = next(p for p in auth.personas() if p["id"] == "national")
    assert client.post("/api/admin/reset", headers=_signed({**p, "exp": int(time.time()) - 5})).status_code == 401
    assert client.post("/api/admin/reset", headers=_signed(p)).status_code == 401      # no expiry at all
    assert client.get("/api/meta", headers=login(client, "national")).json()["user"]["exp"] > time.time()


def _fresh():
    seed.seed_database(force=True)
    engine.invalidate()


def _deck_lane(client):
    plan = client.get("/api/redistribution").json()
    return next(s for s in plan["shipments"] if s["from"]["code"] == "PHC-14" and s["to"]["code"] == "PHC-22")


def test_only_the_donor_side_releases_stock(client):
    _fresh()
    rec = _deck_lane(client)                      # PHC-14 is in Villupuram, PHC-22 in Tiruvannamalai
    r = client.post(f"/api/redistribution/{rec['id']}/approve", headers=login(client, "dho-TVM"))
    assert r.status_code == 403 and "donor" in r.json()["detail"]
    r = client.post(f"/api/redistribution/{rec['id']}/approve", headers=login(client, "dho-VPM"))
    assert r.status_code == 200 and r.json()["status"] == "approved"
    tid = r.json()["id"]
    client.post(f"/api/transfers/{tid}/status", json={"status": "cancelled"}, headers=login(client, "dho-VPM"))


def test_recommendation_id_survives_unrelated_changes(client):
    _fresh()
    before = _deck_lane(client)
    h = login(client, "national")
    # A report at PHC-22 changes how much it needs -> quantities move, identity must not.
    r = client.post("/api/reports/submit", headers=h, json={
        "phc_id": 22, "confirmed": True,
        "report": {"stock": [{"drug_code": "PCM", "quantity": 40, "kind": "remaining"}]}})
    assert r.status_code == 200
    after = _deck_lane(client)
    assert after["id"] == before["id"]
    assert after["lines"][0]["qty"] != before["lines"][0]["qty"]
    # double approval is idempotent; a later approval after closure gets a fresh transfer code
    t1 = client.post(f"/api/redistribution/{after['id']}/approve", headers=h).json()
    t2 = client.post(f"/api/redistribution/{after['id']}/approve", headers=h).json()
    assert t1["id"] == t2["id"] and t1["code"] == f"{after['id']}-1"
    client.post(f"/api/transfers/{t1['id']}/status", json={"status": "cancelled"}, headers=h)
    t3 = client.post(f"/api/redistribution/{_deck_lane(client)['id']}/approve", headers=h).json()
    assert t3["id"] != t1["id"] and t3["code"].endswith("-2")
    client.post(f"/api/transfers/{t3['id']}/status", json={"status": "cancelled"}, headers=h)


def test_low_confidence_report_needs_confirmation(client):
    ws = service.check_report(41, {"stock": [], "confidence": 0.3})
    assert [w["code"] for w in ws] == ["low_confidence"]
    assert service.check_report(41, {"stock": [], "confidence": 0.9}) == []


def test_undispatched_transfer_becomes_overdue(client):
    _fresh()
    h = login(client, "national")
    rec = _deck_lane(client)
    t = client.post(f"/api/redistribution/{rec['id']}/approve", headers=h).json()
    assert t["overdue"] is False
    old = (datetime.now() - timedelta(days=5)).isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute("UPDATE transfers SET created_at=? WHERE id=?", (old, t["id"]))
    t = service.get_transfer(t["id"])
    assert t["overdue"] and t["age_days"] == 5
    snap = client.get("/api/briefing", headers=h).json()
    assert any(o["from"] == "PHC-14" for o in snap["snapshot"]["overdue_transfers"])
    assert any("not dispatched" in a for a in snap["actions"])
    client.post(f"/api/transfers/{t['id']}/status", json={"status": "cancelled"}, headers=h)


def _ivr(client, params, lang="ta"):
    return client.post("/api/dialogflow/webhook", json={
        "languageCode": f"{lang}-IN", "fulfillmentInfo": {"tag": "submit-report"},
        "sessionInfo": {"parameters": {"caller_phone": "+919000000022", **params}}}).json()


def _ivr_reports():
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM reports WHERE channel='ivr' AND phc_id=22").fetchone()[0]


def test_ivr_asks_before_saving_implausible_numbers(client):
    n0 = _ivr_reports()
    r = _ivr(client, {"pcm": 99999, "beds": 3})
    text = r["fulfillment_response"]["messages"][0]["text"]["text"][0]
    assert r["session_info"]["parameters"]["needs_confirmation"] is True
    assert "99999" in text and "சரிபாருங்கள்" in text          # Tamil "please check"
    assert _ivr_reports() == n0                                   # nothing saved yet
    r = _ivr(client, {"pcm": 99999, "beds": 3, "confirmed": True})
    assert r["session_info"]["parameters"]["needs_confirmation"] is False
    assert _ivr_reports() == n0 + 1
    with get_conn() as conn:
        saved = conn.execute("SELECT parsed_json FROM reports WHERE channel='ivr' ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert "count_high" in saved                                  # override kept for audit


def test_no_cross_site_access_by_default(client):
    r = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


@pytest.mark.parametrize("lang", sorted(LANGUAGES))
def test_every_language_has_every_phrase(lang):
    assert set(P[lang]) == set(P["en"])
    for k, v in P[lang].items():
        assert set(__import__("re").findall(r"\{(\w+)\}", v)) == set(__import__("re").findall(r"\{(\w+)\}", P["en"][k])), (lang, k)
    text = gemini.confirmation_text({"stock": [{"drug_code": "PCM", "quantity": 5, "kind": "received"}],
                                     "beds_occupied": 2}, lang, "PHC X")
    assert "PHC X" in text and "5" in text
