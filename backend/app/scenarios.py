"""Health-emergency simulator: "what if a flood / dengue outbreak / heatwave hits these districts?"

A scenario scales forecast demand for the drugs that emergency drives, at every PHC in the chosen
districts, for its duration. The engine then re-runs early warning and the redistribution MILP on
the what-if forecast, so officers see which PHCs would run out, what can be moved in advance and
what has to be indented from the warehouse, before the emergency arrives. Nothing is saved.

Multipliers are planning assumptions drawn from typical post-event caseload patterns (e.g. ORS
and zinc after floods, paracetamol and ACT in vector-borne outbreaks, anti-snake venom after
flooding displaces snakes); state programmes can tune them.
"""
import json
import threading

from . import engine
from .reference import DRUG_BY_CODE, LIFE_SAVING

PRESETS = {
    "flood": {"drugs": {"ORS": 3.0, "ZNC": 3.0, "AMX": 1.8, "PCM": 1.6, "ASV": 2.5, "ACT": 1.5},
              "opd": 1.8, "duration": 21},
    "cyclone": {"drugs": {"ORS": 2.5, "ZNC": 2.5, "AMX": 2.0, "PCM": 1.8, "ASV": 2.0, "OXY": 1.3},
                "opd": 1.9, "duration": 14},
    "vector": {"drugs": {"PCM": 3.0, "ACT": 3.0, "ORS": 1.5}, "opd": 1.7, "duration": 28},
    "cholera": {"drugs": {"ORS": 4.0, "ZNC": 4.0, "AMX": 1.5}, "opd": 1.6, "duration": 21},
    "heatwave": {"drugs": {"ORS": 3.5, "ZNC": 1.5, "PCM": 1.3}, "opd": 1.4, "duration": 14},
}
SEVERITY = {"moderate": 0.5, "severe": 1.0, "extreme": 1.6}

_cache, _lock = {}, threading.Lock()


def multipliers(kind: str, severity: str) -> dict:
    k = SEVERITY[severity]
    return {code: round(1 + (m - 1) * k, 2) for code, m in PRESETS[kind]["drugs"].items()}


def run(kind: str, districts: list, severity: str = "severe", duration: int = None,
        cross_state: bool = False, scope_phc_ids: set = None) -> dict:
    """Baseline vs scenario for the PHCs in `districts` (and the redistribution plan around them)."""
    base = engine.get(cross_state)
    duration = int(duration or PRESETS[kind]["duration"])
    affected = {p["id"] for p in base["phcs"] if p["district_code"] in districts}
    key = json.dumps([base["computed_at"], kind, sorted(districts), severity, duration, cross_state])
    with _lock:
        if key not in _cache:
            if len(_cache) > 16:
                _cache.clear()
            _cache[key] = engine.compute(cross_state, {"phc_ids": affected, "duration": duration,
                                                       "drug_mult": multipliers(kind, severity)})
    sim = _cache[key]
    visible = scope_phc_ids if scope_phc_ids is not None else {p["id"] for p in base["phcs"]}

    def at_risk(r, ids):
        return [i for i in r["items"] if i["phc_id"] in ids
                and i["status"] in ("critical", "high", "stocked_out")]

    phc = {p["id"]: p for p in base["phcs"]}
    base_risk = {(i["phc_id"], i["drug_code"]) for i in at_risk(base, affected)}
    new_lines = sorted((i for i in at_risk(sim, affected) if (i["phc_id"], i["drug_code"]) not in base_risk),
                       key=lambda i: (i["drug_code"] not in LIFE_SAVING, i["days_to_stockout"] or 0))
    opd_x = 1 + (PRESETS[kind]["opd"] - 1) * SEVERITY[severity]
    over_beds = [p for p in (phc[i] for i in affected)
                 if p["bed_occupancy"] is not None and p["bed_occupancy"] * opd_x > 1]

    def touches(s):
        return s["to"]["id"] in affected or s["from"]["id"] in affected

    ships = [s for s in sim["plan"]["shipments"] if touches(s) and (s["to"]["id"] in visible or s["from"]["id"] in visible)]
    escal = [e for e in sim["plan"]["escalations"] if e["phc"]["id"] in affected and e["phc"]["id"] in visible]
    units = sum(ln["qty"] for s in ships for ln in s["lines"])
    return {
        "kind": kind, "severity": severity, "duration": duration, "districts": districts,
        "multipliers": multipliers(kind, severity), "opd_multiplier": round(opd_x, 2),
        "affected_phcs": len(affected),
        "baseline": {"at_risk_lines": len(base_risk),
                     "stocked_out": sum(1 for i in base["items"] if i["phc_id"] in affected and i["status"] == "stocked_out")},
        "scenario": {"at_risk_lines": len(at_risk(sim, affected)),
                     "stocked_out": sum(1 for i in sim["items"] if i["phc_id"] in affected and i["status"] == "stocked_out"),
                     "phcs_over_bed_capacity": len(over_beds)},
        "new_risks": [{"phc": {k: phc[i["phc_id"]][k] for k in ("id", "code", "name", "district_code")},
                       "drug_code": i["drug_code"], "drug": DRUG_BY_CODE[i["drug_code"]]["name"],
                       "days_to_stockout": i["days_to_stockout"], "stock": i["stock"],
                       "daily_forecast": i["daily_forecast"], "lifesaving": i["drug_code"] in LIFE_SAVING}
                      for i in new_lines if i["phc_id"] in visible][:40],
        "plan": {"shipments": ships[:40], "shipment_count": len(ships), "units": round(units),
                 "cost_inr": round(sum(s["cost_inr"] for s in ships)),
                 "escalations": escal[:40], "escalation_count": len(escal),
                 "escalation_units": round(sum(e["qty"] for e in escal))},
        "compute_ms": sim["compute_ms"],
    }
