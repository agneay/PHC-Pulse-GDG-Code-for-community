"""Ask Pulse as an agent: Gemini answers by calling tools over the live engine output.

Every tool is built per request and closed over the caller's scope, so the model can only see
what the officer is allowed to see. Tools never change data: `propose_transfer_approval` only
records a *proposed* action, which the UI shows as a button the officer must press (and which
the normal approval endpoint re-checks, including the donor-side rule).
"""
import logging

import numpy as np

from . import auth, config, engine, scenarios, service
from .geo import distance_matrix_km
from .reference import DRUG_BY_CODE, DRUGS, LANGUAGES, LIFE_SAVING

log = logging.getLogger("phc.agent")

AGENT_PROMPT = """You are PHC Pulse Copilot, an assistant for Indian public-health officers.
Answer with facts from your tools, not from memory: call tools to look up stock, surplus, transfers,
outbreak signals, emergency scenarios and impact. Be concise (<= 150 words), name PHCs and drugs,
give numbers and days. Answer in the language of the question{site_language}.
If the officer asks you to approve or arrange a transfer, find it with get_recommended_transfers and
call propose_transfer_approval; never say it is done, the officer confirms it with a button.
Today is {today}. The officer's area: {scope}."""


def _drug(q: str):
    q = (q or "").strip().lower()
    if not q:
        return None
    for d in DRUGS:
        keys = [d["code"].lower(), d["name"].lower()] + [a.lower() for a in d["aliases"]] + \
               [n.lower() for n in d["names"].values()]
        if any(q == k or (len(q) > 2 and q in k) for k in keys):
            return d["code"]
    return None


class Toolbox:
    def __init__(self, user: dict, scope: dict):
        self.user, self.scope = user, scope
        self.r = engine.get()
        self.sc = service.scoped(self.r, scope)
        self.phcs = {p["id"]: p for p in self.sc["phcs"]}
        self.steps, self.actions = [], []

    def _phc(self, q: str):
        q = (q or "").strip().lower()
        if not q:
            return None
        for p in self.phcs.values():
            if q in (p["code"].lower(), str(p["id"]), p["name"].lower()) or q.replace(" ", "") == p["code"].lower().replace("-", ""):
                return p
        for p in self.phcs.values():
            if len(q) > 3 and q in p["name"].lower():
                return p
        return None

    def _log(self, tool, args, summary):
        self.steps.append({"tool": tool, "args": {k: v for k, v in args.items() if v not in ("", None, [])},
                           "summary": summary})

    # ---- tools (docstrings and type hints are what Gemini sees) -------------------------------
    def tools(self):
        tb = self

        def get_stock_status(drug: str = "", phc: str = "", only_at_risk: bool = True) -> dict:
            """Medicine stock and forecast at PHCs in the officer's area. drug: code or name
            (e.g. "ORS", "paracetamol"); phc: code or name (e.g. "PHC-22"); only_at_risk: only lines
            that will run out before the next supply. Returns up to 25 lines, most urgent first."""
            code, p = _drug(drug), tb._phc(phc)
            items = [i for i in tb.sc["items"] if (not code or i["drug_code"] == code)
                     and (not p or i["phc_id"] == p["id"])
                     and (not only_at_risk or i["status"] in ("stocked_out", "critical", "high", "watch"))]
            items.sort(key=lambda i: i["days_to_stockout"] if i["days_to_stockout"] is not None else 999)
            out = [{"phc": f"{tb.phcs[i['phc_id']]['code']} {tb.phcs[i['phc_id']]['name']}",
                    "drug": DRUG_BY_CODE[i["drug_code"]]["name"], "stock": round(i["stock"]),
                    "uses_per_day": i["daily_forecast"], "runs_out_in_days": i["days_to_stockout"],
                    "next_supply_in_days": i["next_supply_in"], "status": i["status"],
                    "life_saving": i["drug_code"] in LIFE_SAVING} for i in items[:25]]
            tb._log("get_stock_status", {"drug": drug, "phc": phc}, f"{len(items)} lines")
            return {"lines": out, "total_matching": len(items)}

        def get_phc_overview(phc: str) -> dict:
            """Beds, staff, today's report and the riskiest medicines for one PHC (code or name)."""
            p = tb._phc(phc)
            tb._log("get_phc_overview", {"phc": phc}, p["code"] if p else "not found")
            if not p:
                return {"error": f"No PHC matching '{phc}' in your area."}
            risky = [i for i in tb.sc["items"] if i["phc_id"] == p["id"] and i["status"] in ("stocked_out", "critical", "high")]
            return {"phc": f"{p['code']} {p['name']}", "district": service.DISTRICT_NAME[p["district_code"]],
                    "beds": f"{p['beds_occupied']}/{p['beds_total']}", "staff": f"{p['staff_present']}/{p['staff_sanctioned']}",
                    "reported_today": p["reported_today"], "days_since_report": p["days_since_report"],
                    "resilience_score": p["score"], "outbreak_anomalies": p["anomalies"],
                    "medicines_at_risk": [{"drug": DRUG_BY_CODE[i["drug_code"]]["name"], "runs_out_in_days": i["days_to_stockout"]} for i in risky]}

        def find_surplus(drug: str, near_phc: str = "") -> dict:
            """PHCs in the officer's area holding surplus of a drug, nearest first if near_phc is given."""
            code, p = _drug(drug), tb._phc(near_phc)
            tb._log("find_surplus", {"drug": drug, "near_phc": near_phc}, code or "unknown drug")
            if not code:
                return {"error": f"Unknown drug '{drug}'."}
            donors = [i for i in tb.sc["items"] if i["drug_code"] == code and i["surplus_units"] >= 1]
            rows = []
            for i in donors:
                q = tb.phcs[i["phc_id"]]
                km = None
                if p:
                    km = float(distance_matrix_km(np.array([p["lat"], q["lat"]]), np.array([p["lon"], q["lon"]]))[0, 1] * config.ROAD_FACTOR)
                rows.append({"phc": f"{q['code']} {q['name']}", "surplus_units": i["surplus_units"],
                             "road_km": round(km, 1) if km is not None else None})
            rows.sort(key=lambda r: (r["road_km"] if r["road_km"] is not None else 0, -r["surplus_units"]))
            return {"drug": DRUG_BY_CODE[code]["name"], "donors": rows[:10]}

        def get_recommended_transfers(phc: str = "", drug: str = "") -> dict:
            """Transfers the optimiser recommends in the officer's area (optionally for one PHC or
            drug), with their ids and whether this officer may approve them."""
            code, p = _drug(drug), tb._phc(phc)
            ships = [s for s in tb.sc["shipments"] if (not p or p["id"] in (s["from"]["id"], s["to"]["id"]))
                     and (not code or any(ln["drug_code"] == code for ln in s["lines"]))]
            tb._log("get_recommended_transfers", {"phc": phc, "drug": drug}, f"{len(ships)} transfers")
            return {"transfers": [{"id": s["id"], "from": f"{s['from']['code']} {s['from']['name']}",
                                   "to": f"{s['to']['code']} {s['to']['name']}", "road_km": s["distance_km"],
                                   "needed_in_days": s["urgency_days"], "cost_inr": s["cost_inr"],
                                   "items": [f"{ln['qty']:g} {DRUG_BY_CODE[ln['drug_code']]['unit']} {DRUG_BY_CODE[ln['drug_code']]['name']}" for ln in s["lines"]],
                                   "you_can_approve": auth.can_release(tb.user, s["from"])} for s in ships[:12]]}

        def propose_transfer_approval(transfer_id: str, reason: str = "") -> dict:
            """Propose approving a recommended transfer (id like "REC-1A2B3C4D"). This does NOT
            approve it: the officer sees a button and confirms."""
            s = next((s for s in tb.sc["shipments"] if s["id"] == transfer_id.strip().upper()), None)
            tb._log("propose_transfer_approval", {"transfer_id": transfer_id}, "proposed" if s else "not found")
            if not s:
                return {"error": f"No recommended transfer {transfer_id} in your area."}
            if not auth.can_release(tb.user, s["from"]):
                return {"error": "Only an officer responsible for the donor PHC can approve this transfer."}
            if not any(a["rec_id"] == s["id"] for a in tb.actions):
                tb.actions.append({"type": "approve_transfer", "rec_id": s["id"], "reason": reason,
                                   "from": s["from"]["code"], "to": s["to"]["code"],
                                   "items": [{"drug_code": ln["drug_code"], "qty": ln["qty"]} for ln in s["lines"]]})
            return {"status": "proposed; the officer must press Approve to confirm"}

        def get_outbreak_signals() -> dict:
            """Outbreak clusters and unusual patient surges in the officer's area."""
            tb._log("get_outbreak_signals", {}, f"{len(tb.sc['clusters'])} clusters")
            return {"clusters": [{"id": c["id"], "syndrome": c["syndrome"], "phcs": c["phc_codes"],
                                  "excess_cases": c["excess_cases"], "max_ratio_vs_expected": c["max_ratio"]}
                                 for c in tb.sc["clusters"]],
                    "phc_anomalies": [{"phc": a["phc_code"], "syndrome": a["syndrome"], "observed": a["observed"],
                                       "expected": a["expected"]} for a in tb.sc["anomalies"][:15]]}

        def simulate_emergency(kind: str, districts: list[str], severity: str = "severe") -> dict:
            """What-if simulation of a health emergency. kind: flood, cyclone, vector (dengue /
            malaria), cholera or heatwave; districts: district codes or names in the officer's area;
            severity: moderate, severe or extreme."""
            allowed = {p["district_code"] for p in tb.phcs.values()}
            names = {service.DISTRICT_NAME[c].lower(): c for c in allowed}
            codes = [names.get(str(d).lower(), str(d).upper()) for d in districts]
            codes = [c for c in codes if c in allowed]
            kind = kind if kind in scenarios.PRESETS else "flood"
            severity = severity if severity in scenarios.SEVERITY else "severe"
            tb._log("simulate_emergency", {"kind": kind, "districts": codes, "severity": severity},
                    f"{len(codes)} districts")
            if not codes:
                return {"error": "No districts in your area matched. Available: " + ", ".join(
                    f"{c} ({service.DISTRICT_NAME[c]})" for c in sorted(allowed))}
            sim = scenarios.run(kind, codes, severity, scope_phc_ids=set(tb.phcs))
            return {k: sim[k] for k in ("kind", "severity", "duration", "affected_phcs", "baseline", "scenario")} | {
                "new_risks": [f"{r['drug']} at {r['phc']['name']}: {r['days_to_stockout']} days" for r in sim["new_risks"][:10]],
                "advance_transfers": sim["plan"]["shipment_count"], "units_movable": sim["plan"]["units"],
                "emergency_indents": sim["plan"]["escalation_count"], "indent_units": sim["plan"]["escalation_units"]}

        def get_impact_summary() -> dict:
            """What the current transfer plan achieves: stock-out days prevented, patients covered, money saved."""
            tb._log("get_impact_summary", {}, "plan impact")
            return tb.r["impact"]

        return [get_stock_status, get_phc_overview, find_surplus, get_recommended_transfers,
                propose_transfer_approval, get_outbreak_signals, simulate_emergency, get_impact_summary]


def ask(question: str, user: dict, scope: dict, language: str = None) -> dict:
    from . import gemini
    if gemini.client() is None:
        # No model: still answer the question with the grounded one-shot copilot's message.
        return {**gemini.ask(question, service.snapshot(engine.get(), scope), language), "steps": [], "actions": []}
    from google.genai import types
    tb = Toolbox(user, scope)
    site = (f" (the officer is using the site in {LANGUAGES[language]['name']}; use it when the "
            f"question's language is unclear)") if language in LANGUAGES and language != "en" else ""
    try:
        resp = gemini.client().models.generate_content(
            model=config.GEMINI_MODEL, contents=[question],
            config=types.GenerateContentConfig(
                system_instruction=AGENT_PROMPT.format(site_language=site, today=tb.r["today"],
                                                       scope=service.scope_label(scope)),
                tools=tb.tools(), temperature=0.2,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(maximum_remote_calls=8)))
        answer = resp.text or ""
    except Exception as e:
        log.exception("Gemini agent failed")
        return {"answer": f"Gemini request failed: {e}", "engine": "error", "steps": tb.steps, "actions": []}
    return {"answer": answer, "engine": config.GEMINI_MODEL, "steps": tb.steps, "actions": tb.actions}

