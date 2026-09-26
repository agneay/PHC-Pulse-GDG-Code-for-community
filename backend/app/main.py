"""PHC Pulse API (FastAPI). Serves the JSON API under /api and the React dashboard at /."""
import csv
import io
import json
import logging
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Optional

import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import anomaly, auth, channels, config, engine, gemini, seed, service
from .db import get_conn, rows
from .reference import DISTRICTS, DRUG_BY_CODE, DRUGS, LANGUAGES, STATES

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_app):
    seed.seed_database()
    engine.get()   # warm the cache
    yield


app = FastAPI(title="PHC Pulse API", version="1.0.0", lifespan=lifespan,
              description="A heartbeat for every health centre in India.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def result(cross_state: bool = False):
    return engine.get(cross_state)


def scope_dep(state: Optional[str] = None, district: Optional[str] = None,
              user: dict = Depends(auth.current_user)):
    return auth.effective_scope(user, state, district)


# ---------------------------------------------------------------- meta / auth
@app.get("/api/health")
def health():
    return {"ok": True, "today": config.TODAY.isoformat(), "gemini": gemini.status()}


@app.get("/api/meta")
def meta(user: dict = Depends(auth.current_user)):
    return {
        "today": config.TODAY.isoformat(), "user": user, "personas": auth.personas(),
        "states": STATES, "districts": [{k: d[k] for k in ("code", "state", "name", "lat", "lon")}
                                        for d in DISTRICTS],
        "drugs": service.drug_list(), "languages": LANGUAGES, "gemini": gemini.status(),
        "params": {"warning_window": config.WARNING_WINDOW, "horizon": config.FORECAST_HORIZON,
                   "supply_cycle": config.SUPPLY_CYCLE_DAYS, "safety_days": config.SAFETY_DAYS,
                   "cost_per_km": config.COST_PER_KM, "fixed_trip_cost": config.FIXED_TRIP_COST},
    }


class LoginIn(BaseModel):
    persona_id: str


@app.post("/api/auth/login")
def login(body: LoginIn):
    return auth.issue(body.persona_id)


# ---------------------------------------------------------------- dashboards
@app.get("/api/overview")
def overview(scope: dict = Depends(scope_dep)):
    r = result()
    sc = service.scoped(r, scope)
    dmap = {d["code"]: d for d in DISTRICTS}
    rollup = {}
    for p in sc["phcs"]:
        g = rollup.setdefault(p["district_code"], {
            "code": p["district_code"], "name": dmap[p["district_code"]]["name"],
            "state_code": p["state_code"], "phcs": 0, "reported": 0, "score": 0, "red": 0,
            "critical_items": 0, "anomalies": 0})
        g["phcs"] += 1; g["reported"] += p["reported_today"]; g["score"] += p["score"]
        g["red"] += p["health"] == "red"; g["critical_items"] += p["critical_items"]
        g["anomalies"] += p["anomalies"]
    for g in rollup.values():
        g["score"] = round(g["score"] / g["phcs"])
    return {"scope": scope, "scope_label": service.scope_label(scope), "today": r["today"],
            "computed_at": r["computed_at"], "compute_ms": r["compute_ms"],
            "kpis": service.kpis(sc), "phcs": sc["phcs"], "districts": list(rollup.values()),
            "clusters": sc["clusters"], "anomalies": sc["anomalies"][:20],
            "shipments": sc["shipments"][:5], "backtest": r["backtest"]}


@app.get("/api/stock")
def stock(scope: dict = Depends(scope_dep), status: Optional[str] = None):
    r = result()
    sc = service.scoped(r, scope)
    pmap = {p["id"]: p for p in sc["phcs"]}
    items = sc["items"]
    if status:
        wanted = set(status.split(","))
        items = [i for i in items if i["status"] in wanted]
    out = [{**i, "phc_code": pmap[i["phc_id"]]["code"], "phc_name": pmap[i["phc_id"]]["name"],
            "district_code": pmap[i["phc_id"]]["district_code"],
            "drug_name": DRUG_BY_CODE[i["drug_code"]]["name"],
            "unit": DRUG_BY_CODE[i["drug_code"]]["unit"]} for i in items]
    return {"items": out, "phcs": sc["phcs"], "drugs": service.drug_list()}


@app.get("/api/alerts")
def alerts(scope: dict = Depends(scope_dep)):
    r = result()
    sc = service.scoped(r, scope)
    pmap = {p["id"]: p for p in sc["phcs"]}
    order = {"stocked_out": 0, "critical": 1, "high": 2, "watch": 3}
    warn = sorted([i for i in sc["items"] if i["status"] in order],
                  key=lambda i: (order[i["status"]], i["days_to_stockout"] or 0))
    return {
        "stock_warnings": [{**i, "phc_code": pmap[i["phc_id"]]["code"],
                            "phc_name": pmap[i["phc_id"]]["name"],
                            "district_code": pmap[i["phc_id"]]["district_code"],
                            "drug_name": DRUG_BY_CODE[i["drug_code"]]["name"],
                            "unit": DRUG_BY_CODE[i["drug_code"]]["unit"]} for i in warn],
        "anomalies": sc["anomalies"], "clusters": sc["clusters"],
    }


@app.get("/api/phcs/{phc_id}")
def phc_detail(phc_id: int, user: dict = Depends(auth.current_user)):
    r = result()
    p = next((p for p in r["phcs"] if p["id"] == phc_id), None)
    if not p or not auth.in_scope(user.get("scope", {}), p):
        raise HTTPException(404, "PHC not found in your scope")
    A = r["_arrays"]
    i = A["pidx"][phc_id]
    days = r["days"]
    T = len(days)
    window = 60
    t0 = max(0, T - window)

    def clean(v):
        return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), 1)

    items = {it["drug_code"]: it for it in r["items"] if it["phc_id"] == phc_id}
    drugs_out = []
    for j, d in enumerate(DRUGS):
        it = items[d["code"]]
        hist = [{"day": days[t], "demand": clean(A["demand"][i, j, t]),
                 "stock": clean(A["closing"][i, j, t])} for t in range(t0, T)]
        last_t = int(A["last_demand_t"][i, j])
        fc = A["fc"][i, j]
        sig = float(A["sigma"][i, j])
        base_day = config.TODAY - timedelta(days=(T - 1 - last_t))
        stock_level = max(it["stock"] + it["incoming"] - it["committed"], 0)
        s_t0 = int(A["last_stock_t"][i, j])
        proj, cum = [], 0.0
        for h in range(1, len(fc) + 1):
            day = base_day + timedelta(days=h)
            if day <= config.TODAY - timedelta(days=(T - 1 - s_t0)):
                continue
            cum += fc[h - 1]
            proj.append({"day": day.isoformat(), "forecast": round(float(fc[h - 1]), 1),
                         "lo": round(max(0.0, fc[h - 1] - 1.28 * sig), 1),
                         "hi": round(fc[h - 1] + 1.28 * sig, 1),
                         "projected_stock": round(max(stock_level - cum, 0.0), 1)})
        drugs_out.append({**it, "code": d["code"], "name": d["name"], "unit": d["unit"],
                          "history": hist, "forecast": proj})

    foot = A["foot"]
    lt = int(A["last_foot_t"][i])
    bands = {}
    for syn in ("opd", "fever", "diarrhoea", "respiratory"):
        band = anomaly.expected_band(foot[syn][i], A["wf"][i], A["wday"], lt, window)
        bands[syn] = {t: (e, u) for t, e, u in band}
    footfall = []
    for t in range(t0, T):
        row = {"day": days[t]}
        for syn in ("opd", "fever", "diarrhoea", "respiratory", "beds_occupied", "staff_present"):
            row[syn] = clean(foot[syn][i, t])
        for syn in ("opd", "fever", "diarrhoea", "respiratory"):
            if t in bands[syn]:
                row[f"{syn}_expected"] = round(bands[syn][t][0], 1)
                row[f"{syn}_threshold"] = round(bands[syn][t][1], 1)
        footfall.append(row)

    with get_conn() as conn:
        reports = rows(conn, "SELECT id, created_at, channel, language, transcript, confirmation,"
                             " engine FROM reports WHERE phc_id=? ORDER BY id DESC LIMIT 10", (phc_id,))
    transfers = service.list_transfers("t.from_phc=? OR t.to_phc=?", (phc_id, phc_id))
    ships = [s for s in r["plan"]["shipments"] if s["from"]["id"] == phc_id or s["to"]["id"] == phc_id]
    return {"phc": p, "drugs": drugs_out, "footfall": footfall,
            "anomalies": [a for a in r["anomalies"] if a["phc_id"] == phc_id],
            "reports": reports, "transfers": transfers, "recommendations": ships,
            "district_name": service.DISTRICT_NAME[p["district_code"]],
            "state_name": service.STATE_NAME[p["state_code"]]}


# ---------------------------------------------------------------- redistribution
@app.get("/api/redistribution")
def redistribution(cross_state: bool = False, scope: dict = Depends(scope_dep)):
    r = result(cross_state)
    sc = service.scoped(r, scope)
    stats = dict(r["plan"]["stats"])
    if scope:   # re-aggregate the national plan's stats for this jurisdiction
        moved = sum(l["qty"] for s in sc["shipments"] for l in s["lines"])
        short = sum(e["qty"] for e in sc["escalations"])
        stats.update(shipments=len(sc["shipments"]), units_moved=round(moved),
                     units_needed=round(moved + short),
                     coverage=round(moved / (moved + short), 3) if moved + short else None,
                     cost=float(sum(s["cost_inr"] for s in sc["shipments"])),
                     lanes=len({(s["from"]["id"], s["to"]["id"]) for s in sc["shipments"]}))
    return {"shipments": sc["shipments"], "escalations": sc["escalations"],
            "stats": stats, "cross_state": cross_state,
            "transfers": [t for t in service.list_transfers()
                          if t["from_phc"] in sc["ids"] or t["to_phc"] in sc["ids"]]}


@app.post("/api/redistribution/{rec_id}/approve")
def approve(rec_id: str, cross_state: bool = False, user: dict = Depends(auth.require_user)):
    if user["role"] == "phc":
        raise HTTPException(403, "PHC staff cannot approve transfers")
    r = result(cross_state)
    rec = next((s for s in r["plan"]["shipments"] if s["id"] == rec_id), None)
    if not rec:
        raise HTTPException(409, "Recommendation is stale - the plan was recomputed. Refresh.")
    sc = user.get("scope", {})
    if not (auth.in_scope(sc, rec["from"]) or auth.in_scope(sc, rec["to"])):
        raise HTTPException(403, "Outside your jurisdiction")
    return service.approve_recommendation(rec, user)


class StatusIn(BaseModel):
    status: str


@app.post("/api/transfers/{tid}/status")
def transfer_status(tid: int, body: StatusIn, user: dict = Depends(auth.require_user)):
    t = next((t for t in service.list_transfers("t.id=?", (tid,))), None)
    if not t:
        raise HTTPException(404, "unknown transfer")
    donor = {"id": t["from_phc"], "district_code": t["from_district"], "state_code": t["from_state"]}
    recipient = {"id": t["to_phc"], "district_code": t["to_district"], "state_code": t["to_state"]}
    sc = user.get("scope", {})
    # The donor side dispatches, the recipient side confirms receipt; cancelling is an officer decision.
    allowed = {"in_transit": auth.in_scope(sc, donor),
               "delivered": auth.in_scope(sc, recipient),
               "cancelled": user["role"] != "phc" and (auth.in_scope(sc, donor)
                                                       or auth.in_scope(sc, recipient))}
    if body.status not in allowed:
        raise HTTPException(400, f"unknown status {body.status}")
    if not allowed[body.status]:
        raise HTTPException(403, f"You cannot mark {t['from_code']} -> {t['to_code']} as {body.status}")
    try:
        return service.set_transfer_status(tid, body.status, user)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/transfers")
def transfers(scope: dict = Depends(scope_dep)):
    r = result()
    ids = {p["id"] for p in r["phcs"] if auth.in_scope(scope, p)}
    return [t for t in service.list_transfers() if t["from_phc"] in ids or t["to_phc"] in ids]


# ---------------------------------------------------------------- reporting (voice / text)
@app.post("/api/reports/voice")
async def report_voice(audio: UploadFile = File(...), phc_id: int = Form(...),
                       language: str = Form("en"), previous: Optional[str] = Form(None),
                       text: Optional[str] = Form(None), user: dict = Depends(auth.require_user)):
    phc = service.get_phc(phc_id)
    if not phc:
        raise HTTPException(404, "unknown PHC")
    auth.require_phc_access(user, phc)
    data = await audio.read()
    if len(data) > 8_000_000:
        raise HTTPException(413, "audio too long - keep it under 60 seconds")
    try:
        out = gemini.parse_report(
            phc=phc, district=service.DISTRICT_NAME[phc["district_code"]],
            state=service.STATE_NAME[phc["state_code"]], language=language, audio=data,
            mime_type=(audio.content_type or "audio/wav").split(";")[0], text=text,
            previous=json.loads(previous) if previous else None)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return {**out, "warnings": service.check_report(phc_id, out["report"])}


class TextReportIn(BaseModel):
    phc_id: int
    language: str = "en"
    text: str
    previous: Optional[dict] = None


@app.post("/api/reports/parse")
def report_parse(body: TextReportIn, user: dict = Depends(auth.require_user)):
    phc = service.get_phc(body.phc_id)
    if not phc:
        raise HTTPException(404, "unknown PHC")
    auth.require_phc_access(user, phc)
    try:
        out = gemini.parse_report(
            phc=phc, district=service.DISTRICT_NAME[phc["district_code"]],
            state=service.STATE_NAME[phc["state_code"]], language=body.language, text=body.text,
            previous=body.previous)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return {**out, "warnings": service.check_report(body.phc_id, out["report"])}


class SubmitIn(BaseModel):
    phc_id: int
    language: str = "en"
    channel: str = "voice"
    engine: str = "unknown"
    report: dict
    confirmed: bool = False     # the worker re-checked numbers flagged as implausible


@app.post("/api/reports/submit")
def report_submit(body: SubmitIn, user: dict = Depends(auth.require_user)):
    phc = service.get_phc(body.phc_id)
    if not phc:
        raise HTTPException(404, "unknown PHC")
    auth.require_phc_access(user, phc)
    warnings = service.check_report(body.phc_id, body.report)
    if warnings and not body.confirmed:
        raise HTTPException(409, {"message": "Some numbers look unusual. Re-check them, then confirm.",
                                  "warnings": warnings})
    try:
        out = service.apply_report(body.phc_id, {**body.report, "warnings": warnings}, body.channel,
                                   body.language, body.engine, reporter=user["name"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    r = result()
    items = [i for i in r["items"] if i["phc_id"] == body.phc_id]
    return {**out, "items": items}


@app.get("/api/reports")
def reports(limit: int = 30, scope: dict = Depends(scope_dep)):
    with get_conn() as conn:
        rs = rows(conn, "SELECT r.*, p.code AS phc_code, p.name AS phc_name, p.district_code,"
                        " p.state_code FROM reports r JOIN phcs p ON p.id=r.phc_id"
                        " ORDER BY r.id DESC LIMIT ?", (limit * 4,))
    rs = [r for r in rs if auth.in_scope(scope, {"id": r["phc_id"], "district_code": r["district_code"],
                                                  "state_code": r["state_code"]})][:limit]
    for r in rs:
        r["parsed"] = json.loads(r.pop("parsed_json") or "{}")
    return rs


# ---------------------------------------------------------------- feature-phone channels
@app.post("/api/ussd", response_class=PlainTextResponse)
async def ussd(request: Request):
    form = await request.form()
    return channels.ussd(form.get("sessionId", ""), form.get("phoneNumber", ""), form.get("text", ""))


class SmsIn(BaseModel):
    phone: str
    text: str


@app.post("/api/sms")
def sms(body: SmsIn):
    return channels.sms(body.phone, body.text)


@app.post("/api/dialogflow/webhook")
async def dialogflow(request: Request):
    return channels.dialogflow_webhook(await request.json())


@app.get("/api/workers")
def workers(scope: dict = Depends(scope_dep)):
    with get_conn() as conn:
        ws = rows(conn, "SELECT w.*, p.code AS phc_code, p.name AS phc_name, p.district_code,"
                        " p.state_code FROM workers w JOIN phcs p ON p.id=w.phc_id ORDER BY p.id")
    return [w for w in ws if auth.in_scope(scope, {"id": w["phc_id"], "district_code": w["district_code"],
                                                   "state_code": w["state_code"]})]


# ---------------------------------------------------------------- Gemini insights
@app.get("/api/briefing")
def briefing(language: str = "en", scope: dict = Depends(scope_dep),
             user: dict = Depends(auth.current_user)):
    snap = service.snapshot(result(), scope)
    audience = {"national": "national health ministry command centre", "state": "state health officer",
                "district": "district health officer", "phc": "PHC medical officer"}[user["role"]]
    return {"snapshot": snap, **gemini.briefing(snap, audience, language)}


class AskIn(BaseModel):
    question: str
    language: Optional[str] = None      # the site language; the answer follows the question's


@app.post("/api/ask")
def ask(body: AskIn, scope: dict = Depends(scope_dep)):
    return gemini.ask(body.question[:2000], service.snapshot(result(), scope), body.language)


class TtsIn(BaseModel):
    text: str
    language: str = "en"


@app.post("/api/tts")
def tts(body: TtsIn, user: dict = Depends(auth.require_user)):
    """Read-back audio for devices without a voice in the worker's language."""
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "nothing to read")
    if len(text) > 1500:
        raise HTTPException(413, "text too long to read aloud")
    try:
        wav = gemini.tts(text, body.language if body.language in LANGUAGES else "en")
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        logging.getLogger("phc.tts").exception("Gemini TTS failed")
        raise HTTPException(502, f"Read-aloud failed: {e}")
    return Response(wav, media_type="audio/wav")


class AlertIn(BaseModel):
    language: Optional[str] = None


@app.post("/api/clusters/{cluster_id}/alert")
def cluster_alert(cluster_id: str, body: AlertIn, user: dict = Depends(auth.require_user)):
    r = result()
    sc = user.get("scope", {})
    c = next((c for c in r["clusters"] if c["id"] == cluster_id), None)
    if not c or not any(auth.in_scope(sc, p) for p in r["phcs"] if p["id"] in c["phc_ids"]):
        raise HTTPException(404, "cluster not found in your scope")
    lang = body.language or next(s["language"] for s in STATES if s["code"] == c["state_code"])
    pmap = {p["id"]: p for p in r["phcs"]}
    payload = {**c, "district_name": " / ".join(service.DISTRICT_NAME[d] for d in c["district_codes"]),
               "state_name": service.STATE_NAME[c["state_code"]],
               "phcs": [{"code": pmap[i]["code"], "name": pmap[i]["name"]} for i in c["phc_ids"]],
               "anomalies": [a for a in r["anomalies"] if a["phc_id"] in c["phc_ids"]]}
    return {"cluster": c, "language": lang, **gemini.outbreak_alert(payload, lang)}


# ---------------------------------------------------------------- model card / HMIS
@app.get("/api/model")
def model():
    r = result()
    return {"backtest": r["backtest"], "plan_stats": r["plan"]["stats"], "compute_ms": r["compute_ms"],
            "forecaster": {"name": "Damped Holt-Winters, multiplicative weekly seasonality",
                           "alpha": 0.25, "beta": 0.04, "gamma": 0.15, "phi": 0.9,
                           "series": len(r["items"]), "horizon_days": config.FORECAST_HORIZON,
                           "outbreak_adjustment": "anomaly-linked drugs scaled by observed surge, "
                                                  "held 14 days then decayed"},
            "optimizer": {"name": "Mixed-integer program (HiGHS)", "objective":
                          "trip cost + handling + urgency-weighted shortage penalty",
                          "consolidation": "one trip variable per lane shared by all drugs"},
            "anomaly": {"method": "weekday-adjusted robust z-score (median/MAD), 28-day baseline",
                        "threshold_z": anomaly.Z_THRESHOLD, "cluster_km": anomaly.CLUSTER_KM},
            "gemini": gemini.status()}


@app.get("/api/hmis/export.csv")
def hmis_export(month: Optional[str] = None, scope: dict = Depends(scope_dep)):
    """Monthly facility report in an HMIS-style flat layout (one row per facility x item)."""
    month = month or config.TODAY.strftime("%Y-%m")
    with get_conn() as conn:
        stock = rows(conn, """SELECT p.id, p.nin, p.code, p.name, p.district_code, p.state_code, s.drug_code,
              SUM(COALESCE(s.received,0)) AS received, SUM(COALESCE(s.dispensed,0)) AS dispensed,
              SUM(CASE WHEN s.closing<=0 THEN 1 ELSE 0 END) AS stockout_days,
              (SELECT closing FROM stock_daily s2 WHERE s2.phc_id=s.phc_id AND s2.drug_code=s.drug_code
                 AND substr(s2.day,1,7)=? ORDER BY s2.day DESC LIMIT 1) AS closing
            FROM stock_daily s JOIN phcs p ON p.id=s.phc_id WHERE substr(s.day,1,7)=?
            GROUP BY s.phc_id, s.drug_code ORDER BY p.id""", (month, month))
        foot = {r["code"]: r for r in rows(conn, """SELECT p.code, SUM(opd) AS opd, SUM(fever) AS fever,
              SUM(diarrhoea) AS diarrhoea, SUM(respiratory) AS respiratory, COUNT(*) AS days_reported
            FROM footfall_daily f JOIN phcs p ON p.id=f.phc_id WHERE substr(f.day,1,7)=?
            GROUP BY p.code""", (month,))}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["month", "state", "district", "facility_nin", "facility_code", "facility_name",
                "opd_total", "fever", "diarrhoea", "ari", "days_reported", "item_code", "item_name",
                "received", "consumed", "closing_balance", "stockout_days"])
    for s in stock:
        if not auth.in_scope(scope, s):
            continue
        f = foot.get(s["code"], {})
        w.writerow([month, s["state_code"], s["district_code"], s["nin"], s["code"], s["name"],
                    f.get("opd"), f.get("fever"), f.get("diarrhoea"), f.get("respiratory"),
                    f.get("days_reported"), s["drug_code"], DRUG_BY_CODE[s["drug_code"]]["name"],
                    round(s["received"]), round(s["dispensed"]), round(s["closing"] or 0),
                    s["stockout_days"]])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=phc_pulse_hmis_{month}.csv"})


@app.post("/api/admin/reset")
def reset(user: dict = Depends(auth.require_national)):
    """Re-seed the demo data (used between demo runs)."""
    seed.seed_database(force=True)
    channels._submitted.clear()
    engine.invalidate()
    engine.get()
    return {"ok": True}


# ---------------------------------------------------------------- SPA
def static_file(root, path: str):
    """The file under `root` that `path` names, or None. Resolved and confined to `root`, so
    "..", percent-encoded slashes and absolute paths (e.g. "//proc/self/environ") never escape."""
    root = root.resolve()
    f = (root / path.lstrip("/\\")).resolve()
    return f if path and f.is_relative_to(root) and f.is_file() else None


if config.STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=config.STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = static_file(config.STATIC_DIR, path)
        if f:
            return FileResponse(f)
        return FileResponse(config.STATIC_DIR / "index.html")
else:
    @app.get("/")
    def root():
        return JSONResponse({"service": "PHC Pulse API", "docs": "/docs",
                             "note": "frontend not built - run `npm run build` in /frontend"})
