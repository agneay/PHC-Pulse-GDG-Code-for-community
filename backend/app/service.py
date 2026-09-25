"""Write paths (reports, transfers) and read-model helpers shared by the API and channels."""
import json
from datetime import datetime, timedelta
from typing import Optional

from . import config, engine
from .auth import in_scope
from .db import get_conn, rows
from .reference import DISTRICTS, DRUG_BY_CODE, DRUGS, STATES

DISTRICT_NAME = {d["code"]: d["name"] for d in DISTRICTS}
STATE_NAME = {s["code"]: s["name"] for s in STATES}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def get_phc(phc_id: int) -> Optional[dict]:
    with get_conn() as conn:
        r = rows(conn, "SELECT * FROM phcs WHERE id=?", (phc_id,))
    return r[0] if r else None


def find_phc(code_or_id) -> Optional[dict]:
    with get_conn() as conn:
        r = rows(conn, "SELECT * FROM phcs WHERE code=? OR id=? OR UPPER(code)=UPPER(?)",
                 (str(code_or_id), code_or_id if str(code_or_id).isdigit() else -1, str(code_or_id)))
    return r[0] if r else None


# ------------------------------------------------------------------ stock ledger helpers
def _today_row(conn, phc_id: int, drug: str) -> dict:
    """Get (or open) today's ledger row, carrying forward the last closing balance."""
    today = config.TODAY.isoformat()
    r = rows(conn, "SELECT * FROM stock_daily WHERE phc_id=? AND drug_code=? AND day=?",
             (phc_id, drug, today))
    if r:
        return r[0]
    last = rows(conn, "SELECT closing FROM stock_daily WHERE phc_id=? AND drug_code=? AND day<? "
                      "ORDER BY day DESC LIMIT 1", (phc_id, drug, today))
    opening = last[0]["closing"] if last else 0.0
    row = {"phc_id": phc_id, "drug_code": drug, "day": today, "opening": opening, "received": 0.0,
           "dispensed": None, "unmet": 0.0, "adjustment": 0.0, "closing": opening,
           "source": "transfer"}
    conn.execute("INSERT INTO stock_daily VALUES (:phc_id,:drug_code,:day,:opening,:received,"
                 ":dispensed,:unmet,:adjustment,:closing,:source)", row)
    return row


def _save_row(conn, r: dict):
    conn.execute("UPDATE stock_daily SET opening=:opening, received=:received, dispensed=:dispensed,"
                 " unmet=:unmet, adjustment=:adjustment, closing=:closing, source=:source "
                 "WHERE phc_id=:phc_id AND drug_code=:drug_code AND day=:day", r)


def apply_report(phc_id: int, report: dict, channel: str, language: str, engine_name: str,
                 reporter: str = "worker") -> dict:
    """Persist a structured daily report (from voice, USSD, SMS or IVR) into the warehouse."""
    today = config.TODAY.isoformat()
    phc = get_phc(phc_id)
    if not phc:
        raise ValueError("unknown PHC")
    with get_conn() as conn:
        for line in report.get("stock", []):
            code = line.get("drug_code")
            if code not in DRUG_BY_CODE or line.get("quantity") is None:
                continue
            r = _today_row(conn, phc_id, code)
            q = max(0.0, float(line["quantity"]))
            if line.get("kind") == "received":
                r["received"] = (r["received"] or 0) + q
                r["closing"] = (r["closing"] or 0) + q
            else:
                r["closing"] = q
                r["dispensed"] = max(0.0, (r["opening"] or 0) + (r["received"] or 0)
                                     + (r["adjustment"] or 0) - q)
                r["source"] = channel
            _save_row(conn, r)

        f = rows(conn, "SELECT * FROM footfall_daily WHERE phc_id=? AND day=?", (phc_id, today))
        cur = f[0] if f else {"phc_id": phc_id, "day": today, "opd": None, "fever": None,
                              "diarrhoea": None, "respiratory": None, "beds_occupied": None,
                              "staff_present": None, "source": channel}
        mapping = {"opd": "opd_count", "fever": "fever_cases", "diarrhoea": "diarrhoea_cases",
                   "respiratory": "respiratory_cases", "beds_occupied": "beds_occupied",
                   "staff_present": "staff_present"}
        for col, key in mapping.items():
            if report.get(key) is not None:
                cur[col] = int(report[key])
        if cur["beds_occupied"] is not None:
            cur["beds_occupied"] = min(cur["beds_occupied"], phc["beds_total"])
        cur["source"] = channel
        conn.execute("INSERT OR REPLACE INTO footfall_daily VALUES (:phc_id,:day,:opd,:fever,"
                     ":diarrhoea,:respiratory,:beds_occupied,:staff_present,:source)", cur)
        cursor = conn.execute(
            "INSERT INTO reports (phc_id, created_at, channel, language, transcript, parsed_json,"
            " confirmation, reporter, engine) VALUES (?,?,?,?,?,?,?,?,?)",
            (phc_id, now_iso(), channel, language, report.get("transcript"),
             json.dumps(report, ensure_ascii=False), report.get("confirmation"), reporter,
             engine_name))
        rid = cursor.lastrowid
    engine.invalidate()
    return {"report_id": rid, "phc": phc["code"]}


# ------------------------------------------------------------------ transfers
TRANSITIONS = {"approved": {"in_transit", "cancelled"}, "in_transit": {"delivered"},
               "delivered": set(), "cancelled": set()}


def approve_recommendation(rec: dict, user: dict) -> dict:
    ts = now_iso()
    lines = [{"drug_code": l["drug_code"], "qty": l["qty"], "needed_in_days": l["needed_in_days"]}
             for l in rec["lines"]]
    reason = "; ".join(
        f"{rec['from']['code']} has surplus {DRUG_BY_CODE[l['drug_code']]['name']}; "
        f"{rec['to']['code']} needs it in {l['needed_in_days']} days" for l in rec["lines"])
    with get_conn() as conn:
        dup = rows(conn, "SELECT id FROM transfers WHERE code=?", (rec["id"],))
        if dup:
            return get_transfer(dup[0]["id"])
        cur = conn.execute(
            "INSERT INTO transfers (code, from_phc, to_phc, lines_json, distance_km, cost_inr,"
            " eta_hours, status, reason, created_at, updated_at, approved_by, history_json)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rec["id"], rec["from"]["id"], rec["to"]["id"], json.dumps(lines), rec["distance_km"],
             rec["cost_inr"], rec["eta_hours"], "approved", reason, ts, ts, user["name"],
             json.dumps([{"status": "approved", "at": ts, "by": user["name"]}])))
        tid = cur.lastrowid
    engine.invalidate()
    return get_transfer(tid)


def set_transfer_status(tid: int, status: str, user: dict) -> dict:
    with get_conn() as conn:
        t = rows(conn, "SELECT * FROM transfers WHERE id=?", (tid,))
        if not t:
            raise ValueError("unknown transfer")
        t = t[0]
        if status not in TRANSITIONS[t["status"]]:
            raise ValueError(f"cannot move from {t['status']} to {status}")
        lines = json.loads(t["lines_json"])
        for l in lines:
            if status == "in_transit":        # stock leaves the donor's shelf
                r = _today_row(conn, t["from_phc"], l["drug_code"])
                r["adjustment"] = (r["adjustment"] or 0) - l["qty"]
                r["closing"] = max(0.0, (r["closing"] or 0) - l["qty"])
                _save_row(conn, r)
            elif status == "delivered":       # and arrives at the recipient
                r = _today_row(conn, t["to_phc"], l["drug_code"])
                r["received"] = (r["received"] or 0) + l["qty"]
                r["closing"] = (r["closing"] or 0) + l["qty"]
                _save_row(conn, r)
        hist = json.loads(t["history_json"] or "[]")
        ts = now_iso()
        hist.append({"status": status, "at": ts, "by": user["name"]})
        conn.execute("UPDATE transfers SET status=?, updated_at=?, history_json=? WHERE id=?",
                     (status, ts, json.dumps(hist), tid))
    engine.invalidate()
    return get_transfer(tid)


def get_transfer(tid: int) -> dict:
    return list_transfers(where="t.id=?", params=(tid,))[0]


def list_transfers(where: str = "1=1", params=()) -> list:
    with get_conn() as conn:
        ts = rows(conn, f"""SELECT t.*, a.code AS from_code, a.name AS from_name,
            a.district_code AS from_district, a.state_code AS from_state, a.lat AS from_lat,
            a.lon AS from_lon, b.code AS to_code, b.name AS to_name, b.district_code AS to_district,
            b.state_code AS to_state, b.lat AS to_lat, b.lon AS to_lon
            FROM transfers t JOIN phcs a ON a.id=t.from_phc JOIN phcs b ON b.id=t.to_phc
            WHERE {where} ORDER BY t.id DESC""", params)
    for t in ts:
        t["lines"] = json.loads(t.pop("lines_json"))
        for l in t["lines"]:
            l["drug_name"] = DRUG_BY_CODE[l["drug_code"]]["name"]
            l["unit"] = DRUG_BY_CODE[l["drug_code"]]["unit"]
        t["history"] = json.loads(t.pop("history_json") or "[]")
        if t["status"] == "in_transit":
            started = next((h["at"] for h in t["history"] if h["status"] == "in_transit"), None)
            if started:
                t["eta_at"] = (datetime.fromisoformat(started)
                               + timedelta(hours=t["eta_hours"] or 0)).isoformat(timespec="minutes")
    return ts


# ------------------------------------------------------------------ read models
def scoped(result: dict, scope: dict) -> dict:
    """Filter the engine output down to the caller's scope."""
    phcs = [p for p in result["phcs"] if in_scope(scope, p)]
    ids = {p["id"] for p in phcs}
    items = [i for i in result["items"] if i["phc_id"] in ids]
    anomalies = [a for a in result["anomalies"] if a["phc_id"] in ids]
    clusters = [c for c in result["clusters"] if set(c["phc_ids"]) & ids]
    ships = [s for s in result["plan"]["shipments"] if s["from"]["id"] in ids or s["to"]["id"] in ids]
    esc = [e for e in result["plan"]["escalations"] if e["phc"]["id"] in ids]
    return {"phcs": phcs, "items": items, "anomalies": anomalies, "clusters": clusters,
            "shipments": ships, "escalations": esc, "ids": ids}


def kpis(sc: dict) -> dict:
    phcs, items = sc["phcs"], sc["items"]
    occ = [p["beds_occupied"] / p["beds_total"] for p in phcs if p["beds_occupied"] is not None]
    att = [p["staff_present"] / p["staff_sanctioned"] for p in phcs if p["staff_present"] is not None]
    return {
        "phcs": len(phcs),
        "phcs_reporting_today": sum(p["reported_today"] for p in phcs),
        "stocked_out_items": sum(i["status"] == "stocked_out" for i in items),
        "predicted_stockouts": sum(i["status"] in ("critical", "high", "watch") for i in items),
        "critical_items": sum(i["status"] == "critical" for i in items),
        "surplus_items": sum(i["status"] == "surplus" for i in items),
        "anomalies": len(sc["anomalies"]),
        "outbreak_clusters": len(sc["clusters"]),
        "recommended_transfers": len(sc["shipments"]),
        "escalations": len(sc["escalations"]),
        "bed_occupancy": round(sum(occ) / len(occ), 3) if occ else None,
        "staff_attendance": round(sum(att) / len(att), 3) if att else None,
        "avg_score": round(sum(p["score"] for p in phcs) / len(phcs)) if phcs else None,
        "health": {h: sum(p["health"] == h for p in phcs) for h in ("green", "amber", "red")},
    }


def scope_label(scope: dict) -> str:
    if scope.get("phc_id"):
        p = get_phc(scope["phc_id"])
        return p["name"] if p else "PHC"
    if scope.get("district"):
        return f"{DISTRICT_NAME[scope['district']]} district, {STATE_NAME[scope['state']]}"
    if scope.get("state"):
        return STATE_NAME[scope["state"]]
    return "India (all pilot states)"


def snapshot(result: dict, scope: dict) -> dict:
    """Compact, LLM-friendly view of the scoped situation (grounding for Gemini)."""
    sc = scoped(result, scope)
    pmap = {p["id"]: p for p in sc["phcs"]}
    risks = sorted([i for i in sc["items"] if i["status"] in ("stocked_out", "critical", "high")],
                   key=lambda i: (i["days_to_stockout"] if i["days_to_stockout"] is not None else 99))
    return {
        "scope": scope_label(scope), "date": result["today"], "kpis": kpis(sc),
        "stock_risks": [{"phc": pmap[i["phc_id"]]["code"] + " " + pmap[i["phc_id"]]["name"],
                         "district": DISTRICT_NAME[pmap[i["phc_id"]]["district_code"]],
                         "drug": DRUG_BY_CODE[i["drug_code"]]["name"], "stock": i["stock"],
                         "days_to_stockout": i["days_to_stockout"], "status": i["status"],
                         "next_supply_in_days": i["next_supply_in"],
                         "outbreak_adjusted": i["surge_reason"]} for i in risks[:25]],
        "clusters": [{"district": DISTRICT_NAME[c["district_code"]], "syndrome": c["syndrome"],
                      "phcs": c["phc_codes"], "excess_cases": c["excess_cases"],
                      "max_ratio": c["max_ratio"], "days": c["max_consecutive_days"]}
                     for c in sc["clusters"]],
        "anomalies": [{"phc": a["phc_code"], "syndrome": a["syndrome"], "observed": a["observed"],
                       "expected": a["expected"], "in_cluster": a["in_cluster"]}
                      for a in sc["anomalies"][:12]],
        "top_transfers": [{"id": s["id"], "from": s["from"]["code"] + " " + s["from"]["name"],
                           "to": s["to"]["code"] + " " + s["to"]["name"],
                           "lines": [{"drug": DRUG_BY_CODE[l["drug_code"]]["name"], "qty": l["qty"]}
                                     for l in s["lines"]],
                           "urgency_days": s["urgency_days"], "distance_km": s["distance_km"],
                           "cost_inr": s["cost_inr"]} for s in sc["shipments"][:10]],
        "escalations": [{"phc": e["phc"]["code"], "drug": DRUG_BY_CODE[e["drug_code"]]["name"],
                         "qty": e["qty"], "needed_in_days": e["needed_in_days"]}
                        for e in sc["escalations"][:10]],
        "weakest_phcs": [{"phc": p["code"] + " " + p["name"], "score": p["score"],
                          "critical_items": p["critical_items"], "anomalies": p["anomalies"],
                          "reported_today": p["reported_today"]}
                         for p in sorted(sc["phcs"], key=lambda p: p["score"])[:8]],
    }


def drug_list():
    return [{k: d[k] for k in ("code", "name", "unit", "names", "aliases")} for d in DRUGS]
