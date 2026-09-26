"""Federated forecasting, emergency simulator, Ask Pulse agent tools, register photos, impact,
scale benchmark and DHIS2 export."""
import os
import tempfile
from types import SimpleNamespace

os.environ.setdefault("PHC_DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import agent, dhis2, engine, federated, gemini, scenarios, seed, service  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        seed.seed_database(force=True)
        engine.invalidate()
        yield c


def login(client, persona):
    tok = client.post("/api/auth/login", json={"persona_id": persona}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


# ---------------------------------------------------------------- A. federated forecasting
def test_federated_prior_beats_local_cold_start(client):
    v = client.get("/api/federated", headers=login(client, "national")).json()
    assert len(v["states"]) == 4 and v["summary"]["raw_rows_shared"] == 0
    for s in v["states"]:
        assert s["numbers_shared"] < 100 < s["raw_rows_kept_local"]
        assert s["federated_accuracy"] > s["local_accuracy"]      # the shared prior helps a new state
    assert set(v["prior"]["params"]) == {"alpha", "beta", "gamma", "phi"}
    assert all(len(d["weekday"]) == 7 for d in v["prior"]["drugs"].values())


def test_fedavg_is_sample_weighted():
    u = {"A": {"params": {"alpha": 0.1, "beta": 0.04, "gamma": 0.1, "phi": 0.9}, "n_obs": 300,
               "drugs": {"PCM": {"weekday": [1] * 7, "per_100_opd": 30}}},
         "B": {"params": {"alpha": 0.4, "beta": 0.04, "gamma": 0.1, "phi": 0.9}, "n_obs": 100,
               "drugs": {"PCM": {"weekday": [1] * 7, "per_100_opd": 10}}}}
    p = federated.aggregate(u)
    assert p["params"]["alpha"] == pytest.approx(0.175) and p["drugs"]["PCM"]["per_100_opd"] == 25


# ---------------------------------------------------------------- B. emergency simulator
def test_flood_raises_risk_and_plans_ahead(client):
    body = {"kind": "flood", "districts": ["KRP"], "severity": "severe"}
    r = client.post("/api/scenarios/run", json=body, headers=login(client, "national")).json()
    assert r["affected_phcs"] == 15
    assert r["scenario"]["at_risk_lines"] > r["baseline"]["at_risk_lines"]
    assert r["new_risks"] and r["plan"]["shipment_count"] + r["plan"]["escalation_count"] > 0
    assert r["multipliers"]["ORS"] == 3.0
    plan = client.post("/api/scenarios/plan", json={**body, "language": "or"}, headers=login(client, "national")).json()
    assert plan["actions"] and plan["headline"]


def test_scenario_respects_jurisdiction(client):
    h = login(client, "dho-TVM")
    assert client.post("/api/scenarios/run", json={"kind": "flood", "districts": ["KRP"]}, headers=h).status_code == 403
    ok = client.post("/api/scenarios/run", json={"kind": "heatwave", "districts": ["TVM"]}, headers=h)
    assert ok.status_code == 200
    tvm = {p["id"] for p in engine.get()["phcs"] if p["district_code"] == "TVM"}
    assert all(x["phc"]["id"] in tvm for x in ok.json()["new_risks"])
    assert client.post("/api/scenarios/run", json={"kind": "flood", "districts": ["VPM"]},
                       headers=login(client, "phc-22")).status_code == 403
    assert client.post("/api/scenarios/run", json={"kind": "tsunami", "districts": ["TVM"]}, headers=h).status_code == 400


def test_scenario_never_changes_stored_data(client):
    before = [i["status"] for i in engine.get()["items"]]
    scenarios.run("cholera", ["GKP", "KSN"], "extreme")
    assert [i["status"] for i in engine.get()["items"]] == before


# ---------------------------------------------------------------- C. agent tools
def _tools(pid, scope=None):
    user = {"role": pid.split("-")[0].replace("dho", "district"), "scope": scope or {}, "name": pid}
    tb = agent.Toolbox(user, scope or {})
    return tb, {f.__name__: f for f in tb.tools()}


def test_agent_tools_are_scoped():
    tb, t = _tools("dho-TVM", {"state": "TN", "district": "TVM"})
    lines = t["get_stock_status"](only_at_risk=False)["lines"]
    tvm = {f"{p['code']} {p['name']}" for p in engine.get()["phcs"] if p["district_code"] == "TVM"}
    assert lines and all(ln["phc"] in tvm for ln in lines)
    assert "error" in t["get_phc_overview"]("PHC-93")                      # Koraput: not theirs
    assert "error" in t["simulate_emergency"]("flood", ["KRP"])
    assert t["simulate_emergency"]("flood", ["Tiruvannamalai"])["affected_phcs"] > 0
    assert [s["tool"] for s in tb.steps][-1] == "simulate_emergency"


def test_agent_proposes_but_never_approves():
    tb, t = _tools("dho-VPM", {"state": "TN", "district": "VPM"})
    lane = next(s for s in t["get_recommended_transfers"](phc="PHC-22")["transfers"] if s["from"].startswith("PHC-14 "))
    assert lane["you_can_approve"]
    assert "proposed" in t["propose_transfer_approval"](lane["id"])["status"]
    assert tb.actions[0]["rec_id"] == lane["id"] and tb.actions[0]["type"] == "approve_transfer"
    assert service.open_transfer_for(lane["id"]) is None                  # nothing was approved
    tb2, t2 = _tools("dho-TVM", {"state": "TN", "district": "TVM"})
    assert "error" in t2["propose_transfer_approval"](lane["id"])       # not the donor side
    assert not tb2.actions


def test_agent_runs_tools_through_gemini(client, monkeypatch):
    calls = []

    def generate_content(model, contents, config):
        tools = {f.__name__: f for f in config.tools}
        calls.append(tools["get_stock_status"](drug="ORS"))              # what AFC would do
        return SimpleNamespace(text="ORS is short at 3 PHCs.")

    monkeypatch.setattr(gemini, "client", lambda: SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    r = client.post("/api/ask", json={"question": "Where is ORS short?"}, headers=login(client, "dho-TVM")).json()
    assert r["answer"].startswith("ORS") and r["steps"][0]["tool"] == "get_stock_status" and calls


# ---------------------------------------------------------------- D. register photo
def test_photo_report(client, monkeypatch):
    h = login(client, "phc-22")
    assert client.post("/api/reports/photo", data={"phc_id": 22}, files={"image": ("r.txt", b"x", "text/plain")},
                       headers=h).status_code == 415
    seen = {}

    def fake_parse(**kw):
        seen.update(kw)
        return {"report": {"stock": [{"drug_code": "PCM", "quantity": 120, "kind": "remaining"}], "beds_occupied": 3,
                           "confidence": 0.9, "transcript": "PCM 120", "confirmation": "ok"}, "engine": "test"}

    monkeypatch.setattr(gemini, "parse_report", fake_parse)
    r = client.post("/api/reports/photo", data={"phc_id": 22, "language": "ta"},
                    files={"image": ("register.jpg", b"\xff\xd8fake", "image/jpeg")}, headers=h)
    assert r.status_code == 200 and seen["image"] == b"\xff\xd8fake" and seen["image_mime"] == "image/jpeg"
    assert client.post("/api/reports/photo", data={"phc_id": 93}, files={"image": ("r.jpg", b"x", "image/jpeg")},
                       headers=h).status_code == 403


# ---------------------------------------------------------------- E. impact
def test_impact_scoped_and_consistent(client):
    nat = client.get("/api/impact", headers=login(client, "national")).json()
    assert nat["stockout_days_prevented"] > 0 and nat["patients_covered"] > 0
    assert nat["national_projection"]["phcs"] == 24935
    tvm = client.get("/api/impact", headers=login(client, "dho-TVM")).json()
    assert 0 < tvm["units_moved"] <= nat["units_moved"]
    assert "impact" in client.get("/api/overview", headers=login(client, "national")).json()


# ---------------------------------------------------------------- F. scale
def test_scale_benchmark_published(client):
    r = client.get("/api/scale")
    if r.status_code == 404:
        pytest.skip("benchmark not generated")
    b = r.json()
    assert b["states"] == 36 and b["series"] == b["phcs"] * 10 and b["per_state"]


# ---------------------------------------------------------------- G. DHIS2
def test_dhis2_export(client):
    meta = client.get("/api/dhis2/metadata").json()
    codes = {e["code"] for e in meta["dataElements"]}
    assert len(codes) == 5 + 10 * 4
    v = client.get("/api/dhis2/dataValueSets?month=2026-09", headers=login(client, "dho-TVM")).json()
    assert v["period"] == "202609" and v["dataValues"]
    assert {d["dataElement"] for d in v["dataValues"]} <= codes
    nins = {p["nin"] for p in engine.get()["phcs"] if p["district_code"] == "TVM"}
    assert {d["orgUnit"] for d in v["dataValues"]} <= nins
    assert dhis2.metadata()["dataSets"][0]["periodType"] == "Monthly"
