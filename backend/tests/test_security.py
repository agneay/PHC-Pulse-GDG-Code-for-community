"""Access control, static-file confinement and stale-demo re-seeding."""
import os
import tempfile
from datetime import timedelta

os.environ.setdefault("PHC_DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config, engine, seed  # noqa: E402
from app.db import get_conn  # noqa: E402
from app.main import app, static_file  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def login(client, persona):
    tok = client.post("/api/auth/login", json={"persona_id": persona}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_static_file_is_confined(tmp_path):
    root = tmp_path / "static"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("spa")
    (root / "assets" / "app.js").write_text("js")
    secret = tmp_path / "secret.txt"
    secret.write_text("key")
    assert static_file(root, "assets/app.js") == (root / "assets" / "app.js").resolve()
    assert static_file(root, "../secret.txt") is None
    assert static_file(root, "assets/../../secret.txt") is None
    assert static_file(root, str(secret)) is None                  # absolute path
    assert static_file(root, "/" + str(secret).lstrip("/")) is None  # "//abs/path" form
    assert static_file(root, "") is None


def _approved_transfer(client):
    plan = client.get("/api/redistribution").json()
    rec = next(s for s in plan["shipments"] if s["from"]["state_code"] == "UP")
    return client.post(f"/api/redistribution/{rec['id']}/approve",
                       headers=login(client, "national")).json()


def test_writes_require_a_token(client):
    t = _approved_transfer(client)
    assert client.post(f"/api/transfers/{t['id']}/status", json={"status": "in_transit"}).status_code == 401
    assert client.post("/api/reports/submit", json={"phc_id": 5, "report": {"stock": []}}).status_code == 401
    assert client.post("/api/reports/parse", json={"phc_id": 5, "text": "ORS 4"}).status_code == 401
    assert client.post("/api/admin/reset").status_code == 401
    cid = client.get("/api/alerts").json()["clusters"][0]["id"]
    assert client.post(f"/api/clusters/{cid}/alert", json={}).status_code == 401


def test_transfer_status_is_scoped(client):
    t = _approved_transfer(client)                                  # an Uttar Pradesh lane
    assert client.post(f"/api/transfers/{t['id']}/status", json={"status": "in_transit"},
                       headers=login(client, "phc-22")).status_code == 403
    assert client.post(f"/api/transfers/{t['id']}/status", json={"status": "in_transit"},
                       headers=login(client, "dho-TVM")).status_code == 403
    assert client.post(f"/api/transfers/{t['id']}/status", json={"status": "bogus"},
                       headers=login(client, "national")).status_code == 400
    ok = client.post(f"/api/transfers/{t['id']}/status", json={"status": "in_transit"},
                     headers=login(client, "state-UP"))
    assert ok.status_code == 200 and ok.json()["status"] == "in_transit"


def test_phc_staff_can_only_report_for_their_own_phc(client):
    h = login(client, "phc-22")
    body = {"report": {"stock": [{"drug_code": "PCM", "quantity": 100}]}}
    assert client.post("/api/reports/submit", json={"phc_id": 5, **body}, headers=h).status_code == 403
    r = client.post("/api/reports/submit", json={"phc_id": 22, **body}, headers=h)
    assert r.status_code == 200


def test_reset_is_national_only(client):
    assert client.post("/api/admin/reset", headers=login(client, "dho-TVM")).status_code == 403


def test_hmis_export_follows_scope(client):
    rows = client.get("/api/hmis/export.csv", headers=login(client, "phc-22")).text.splitlines()[1:]
    assert rows and all(",PHC-22," in r for r in rows)
    rows = client.get("/api/hmis/export.csv", headers=login(client, "dho-TVM")).text.splitlines()[1:]
    assert len(rows) == 15 * 10 and all(",TVM," in r for r in rows)


def test_stale_database_is_reseeded(client, monkeypatch):
    today = config.TODAY
    with get_conn() as conn:
        conn.execute("INSERT INTO reports (phc_id, created_at, channel) VALUES (1, 'x', 'test')")
    monkeypatch.setattr(config, "TODAY", today + timedelta(days=3))
    seed.seed_database()
    with get_conn() as conn:
        end = conn.execute("SELECT MAX(day) FROM footfall_daily WHERE source='hmis'").fetchone()[0]
        n_reports = conn.execute("SELECT COUNT(*) FROM reports WHERE channel='test'").fetchone()[0]
    assert end == config.TODAY.isoformat() and n_reports == 0
    engine.invalidate()
    ships = engine.get()["plan"]["shipments"]
    assert any(s["from"]["code"] == "PHC-14" and s["to"]["code"] == "PHC-22" for s in ships)

    # Same day again: the data (including new reports) is kept.
    with get_conn() as conn:
        conn.execute("INSERT INTO reports (phc_id, created_at, channel) VALUES (1, 'x', 'test')")
    seed.seed_database()
    with get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM reports WHERE channel='test'").fetchone()[0] == 1

    monkeypatch.setattr(config, "TODAY", today)
    seed.seed_database()
    engine.invalidate()
