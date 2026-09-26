"""Data quality: discards are not demand, implausible numbers are challenged, silent PHCs are
not trusted, clusters cross district lines and optimiser failures are visible."""
import os
import tempfile
from datetime import date, timedelta
from types import SimpleNamespace

os.environ.setdefault("PHC_DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import anomaly, config, engine, nlu, redistribution, seed  # noqa: E402
from app.db import get_conn, rows  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
    seed.seed_database(force=True)      # leave a clean demo database for other modules
    engine.invalidate()


def login(client, persona):
    tok = client.post("/api/auth/login", json={"persona_id": persona}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


# ---------------------------------------------------------------- discards
@pytest.mark.parametrize("text, discarded, counted", [
    ("PCM 120 ORS 40 DMG ORS 5 BED 4", [("ORS", 5)], [("PCM", 120), ("ORS", 40)]),
    ("ORS 55, 5 ORS expired", [("ORS", 5)], [("ORS", 55)]),
    ("ORS 5 expired, PCM 120", [("ORS", 5)], [("PCM", 120)]),
    ("expired zinc 10, zinc 30", [("ZNC", 10)], [("ZNC", 30)]),
    ("ओआरएस 50, खराब ओआरएस 4", [("ORS", 4)], [("ORS", 50)]),
])
def test_nlu_discards(text, discarded, counted):
    p = nlu.parse(text)
    assert [(s["drug_code"], s["quantity"]) for s in p["discarded"]] == discarded
    assert [(s["drug_code"], s["quantity"]) for s in p["stock"]] == counted


def test_nlu_whole_words():
    p = nlu.parse("metformin 30, diabetes patients 12, OPD 80")
    assert "diarrhoea_cases" not in p and p["opd_count"] == 80


def test_discard_is_an_adjustment_not_demand(client):
    phc, day = 30, config.TODAY.isoformat()
    with get_conn() as conn:
        before = rows(conn, "SELECT * FROM stock_daily WHERE phc_id=? AND drug_code='ORS' AND day=?",
                      (phc, day))[0]
    count = max(before["closing"] - 8, 0)
    report = {"stock": [{"drug_code": "ORS", "quantity": count, "kind": "remaining"},   # order on purpose
                        {"drug_code": "ORS", "quantity": 5, "kind": "discarded"}]}
    r = client.post("/api/reports/submit", headers=login(client, "national"),
                    json={"phc_id": phc, "report": report, "confirmed": True})
    assert r.status_code == 200, r.text
    with get_conn() as conn:
        after = rows(conn, "SELECT * FROM stock_daily WHERE phc_id=? AND drug_code='ORS' AND day=?",
                     (phc, day))[0]
    assert after["adjustment"] == before["adjustment"] - 5
    assert after["closing"] == count
    # the 5 thrown away are not in dispensed (= patient demand the forecaster learns from)
    assert after["dispensed"] == pytest.approx(
        after["opening"] + after["received"] + after["adjustment"] - after["closing"])


# ---------------------------------------------------------------- plausibility
def test_implausible_count_needs_confirmation(client):
    h = login(client, "national")
    pcm = next(i for i in engine.get()["items"] if i["phc_id"] == 22 and i["drug_code"] == "PCM")
    big = round(pcm["stock"] * 10 + 500)
    parsed = client.post("/api/reports/parse", headers=h, json={
        "phc_id": 22, "text": f"paracetamol {big}, beds 30"}).json()
    fields = {w["field"] for w in parsed["warnings"]}
    assert {"PCM", "beds_occupied"} <= fields
    body = {"phc_id": 22, "report": parsed["report"]}
    r = client.post("/api/reports/submit", headers=h, json=body)
    assert r.status_code == 409 and r.json()["detail"]["warnings"]
    r = client.post("/api/reports/submit", headers=h, json={**body, "confirmed": True})
    assert r.status_code == 200
    with get_conn() as conn:
        saved = rows(conn, "SELECT parsed_json FROM reports WHERE id=?", (r.json()["report_id"],))[0]
    assert "warnings" in saved["parsed_json"]           # audit trail of the override


def test_normal_report_has_no_warnings(client):
    it = {i["drug_code"]: i for i in engine.get()["items"] if i["phc_id"] == 41}
    text = f"paracetamol {round(it['PCM']['stock'])}, ORS {round(it['ORS']['stock'])}, beds 2, staff 8"
    parsed = client.post("/api/reports/parse", headers=login(client, "national"),
                         json={"phc_id": 41, "text": text}).json()
    assert parsed["warnings"] == []


def test_sms_asks_to_resend_with_yes(client):
    phone = "+919000000061"
    msg = "PCM 99999 BED 3"
    r = client.post("/api/sms", json={"phone": phone, "text": msg}).json()
    assert not r["saved"] and "YES" in r["reply"] and "PCM 99999" in r["reply"]
    r = client.post("/api/sms", json={"phone": phone, "text": msg + " YES"}).json()
    assert r["saved"]


# ---------------------------------------------------------------- silent PHCs
def test_silent_phc_is_flagged_and_excluded(client):
    r = engine.get()
    cluster = next(c for c in r["clusters"] if c["syndrome"] == "diarrhoea")
    silent = cluster["phc_ids"][0]
    cutoff = config.TODAY - timedelta(days=config.STALE_DAYS)
    with get_conn() as conn:
        for tbl in ("footfall_daily", "stock_daily"):
            conn.execute(f"DELETE FROM {tbl} WHERE phc_id=? AND day>?",
                         (silent, cutoff.isoformat()))
    engine.invalidate()
    r = engine.get()
    p = next(p for p in r["phcs"] if p["id"] == silent)
    assert p["stale"] and p["days_since_report"] >= config.STALE_DAYS
    assert all(a["phc_id"] != silent for a in r["anomalies"])
    assert all(silent not in c["phc_ids"] for c in r["clusters"])
    assert all(silent not in (s["from"]["id"], s["to"]["id"]) for s in r["plan"]["shipments"])
    assert all(e["phc"]["id"] != silent for e in r["plan"]["escalations"])
    ov = client.get("/api/overview", headers=login(client, "national")).json()
    assert ov["kpis"]["stale_phcs"] >= 1
    seed.seed_database(force=True)
    engine.invalidate()


# ---------------------------------------------------------------- clusters
def test_cluster_crosses_district_border():
    T = 60
    wday = np.arange(T) % 7
    phcs = [{"id": 1, "code": "PHC-1", "name": "A", "district_code": "VPM", "state_code": "TN",
             "lat": 12.30, "lon": 79.40},
            {"id": 2, "code": "PHC-2", "name": "B", "district_code": "TVM", "state_code": "TN",
             "lat": 12.35, "lon": 79.45}]           # ~8 km apart, different districts
    foot = {k: np.full((2, T), 10.0) for k in ("fever", "respiratory")}
    foot["opd"] = np.full((2, T), 100.0)
    foot["diarrhoea"] = np.full((2, T), 10.0)
    foot["diarrhoea"][:, -1] = 40
    days = [date(2026, 1, 1) + timedelta(days=t) for t in range(T)]
    out = anomaly.detect(foot, wday, np.array([T - 1, T - 1]), phcs, days)
    assert len(out["clusters"]) == 1
    c = out["clusters"][0]
    assert c["district_codes"] == ["TVM", "VPM"] and sorted(c["phc_ids"]) == [1, 2]


# ---------------------------------------------------------------- optimiser failure
def test_solver_failure_is_flagged(monkeypatch):
    monkeypatch.setattr(redistribution, "milp",
                        lambda *a, **k: SimpleNamespace(x=None, status=4, message="solver error"))
    phcs = [{"state_code": "TN"}, {"state_code": "TN"}]
    plan = redistribution.optimise(
        [{"phc_idx": 0, "drug": "PCM", "need": 50, "days_to_stockout": 3}],
        [{"phc_idx": 1, "drug": "PCM", "surplus": 80}], phcs, np.array([[0, 20.0], [20.0, 0]]))
    assert plan["stats"]["failed"] and plan["stats"]["units_needed"] == 50
