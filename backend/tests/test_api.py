"""End-to-end API tests: seed -> dashboards -> report -> forecast update -> transfer lifecycle."""
import os
import tempfile

os.environ["PHC_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("GOOGLE_API_KEY", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import nlu  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def login(client, persona):
    tok = client.post("/api/auth/login", json={"persona_id": persona}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_overview_national(client):
    r = client.get("/api/overview").json()
    assert r["kpis"]["phcs"] == 120
    assert r["kpis"]["outbreak_clusters"] >= 2
    assert {c["syndrome"] for c in r["clusters"]} >= {"diarrhoea", "fever"}
    assert r["backtest"]["recall_14d_ahead"] > 0.6


def test_row_level_scope(client):
    h = login(client, "dho-TVM")
    r = client.get("/api/overview", headers=h).json()
    assert r["kpis"]["phcs"] == 15
    assert all(p["district_code"] == "TVM" for p in r["phcs"])
    # a DHO cannot widen scope with a query parameter
    r2 = client.get("/api/overview?state=UP", headers=h).json()
    assert all(p["district_code"] == "TVM" for p in r2["phcs"])


def test_deck_scenario_phc14_to_phc22(client):
    plan = client.get("/api/redistribution").json()
    lanes = [(s["from"]["code"], s["to"]["code"], [l["drug_code"] for l in s["lines"]])
             for s in plan["shipments"]]
    assert any(f == "PHC-14" and t == "PHC-22" and "PCM" in d for f, t, d in lanes), lanes


def test_text_report_fallback_and_submit(client):
    parsed = client.post("/api/reports/parse", json={
        "phc_id": 22, "language": "en",
        "text": "Paracetamol 150 strips, ORS 60 sachets, beds occupied 3, staff present 9, OPD 72"}).json()
    rep = parsed["report"]
    codes = {s["drug_code"]: s["quantity"] for s in rep["stock"]}
    assert codes["PCM"] == 150 and codes["ORS"] == 60
    assert rep["beds_occupied"] == 3 and rep["staff_present"] == 9 and rep["opd_count"] == 72
    out = client.post("/api/reports/submit", json={"phc_id": 22, "language": "en", "channel": "voice",
                                                    "engine": parsed["engine"], "report": rep}).json()
    pcm = next(i for i in out["items"] if i["drug_code"] == "PCM")
    assert pcm["stock"] == 150


def test_transfer_lifecycle_moves_stock(client):
    h = login(client, "national")
    plan = client.get("/api/redistribution").json()
    rec = plan["shipments"][0]
    line = rec["lines"][0]
    before_to = next(d for d in client.get(f"/api/phcs/{rec['to']['id']}").json()["drugs"]
                     if d["code"] == line["drug_code"])["stock"]
    t = client.post(f"/api/redistribution/{rec['id']}/approve", headers=h).json()
    assert t["status"] == "approved"
    assert client.post(f"/api/transfers/{t['id']}/status", json={"status": "delivered"},
                       headers=h).status_code == 400          # must go via in_transit
    client.post(f"/api/transfers/{t['id']}/status", json={"status": "in_transit"}, headers=h)
    t = client.post(f"/api/transfers/{t['id']}/status", json={"status": "delivered"}, headers=h).json()
    assert t["status"] == "delivered"
    after_to = next(d for d in client.get(f"/api/phcs/{rec['to']['id']}").json()["drugs"]
                    if d["code"] == line["drug_code"])["stock"]
    assert after_to == pytest.approx(before_to + line["qty"])


def test_phc_staff_cannot_approve(client):
    h = login(client, "phc-22")
    plan = client.get("/api/redistribution", headers=h).json()
    if plan["shipments"]:
        r = client.post(f"/api/redistribution/{plan['shipments'][0]['id']}/approve", headers=h)
        assert r.status_code == 403


def test_ussd_flow(client):
    phone = "+919000000022"
    def step(text):
        return client.post("/api/ussd", data={"sessionId": "s1", "phoneNumber": phone,
                                              "text": text}).text
    assert step("").startswith("CON") and "PHC-22" in step("")
    assert "Enter strips remaining" in step("1*1")
    assert "Saved PCM" in step("1*1*140")
    assert step("1*1*140*0*2*4*5").startswith("CON Today's report")
    end = step("1*1*140*0*2*4*5*1")
    assert end.startswith("END Submitted")


def test_sms_and_dialogflow(client):
    r = client.post("/api/sms", json={"phone": "+919000000093", "text": "ORS 20 ZNC 5 BED 6 STF 8 OPD 140"}).json()
    assert r["saved"]
    df = client.post("/api/dialogflow/webhook", json={
        "languageCode": "hi", "fulfillmentInfo": {"tag": "submit-report"},
        "sessionInfo": {"parameters": {"caller_phone": "+919000000061", "pcm": 80, "beds": 5,
                                       "staff": 10}}}).json()
    msg = df["fulfillment_response"]["messages"][0]["text"]["text"][0]
    assert "धन्यवाद" in msg


def test_briefing_and_alert_fallback(client):
    b = client.get("/api/briefing").json()
    assert b["headline"] and b["actions"]
    cid = client.get("/api/alerts").json()["clusters"][0]["id"]
    a = client.post(f"/api/clusters/{cid}/alert", json={}).json()
    assert a["recommended_response"]


def test_hmis_export(client):
    r = client.get("/api/hmis/export.csv")
    assert r.status_code == 200 and "facility_nin" in r.text.splitlines()[0]


def test_nlu_hinglish():
    p = nlu.parse("paracetamol ke 120 strip bache hain, bistar 4, staff 8, OPD 90")
    assert p["stock"][0] == {"drug_code": "PCM", "quantity": 120.0}
    assert p["beds_occupied"] == 4 and p["staff_present"] == 8 and p["opd_count"] == 90
