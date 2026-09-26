"""Prescriptive redistribution: which PHC should ship what, to whom, and when.

Formulated as a mixed-integer program solved with HiGHS (scipy.optimize.milp):

    min   sum_p  F_p * y_p                  (trip cost: fixed + per-km + inter-state paperwork)
        + sum_{p,j} h * x_pj                (handling per unit)
        + sum_{i,j} P_j * w_ij * u_ij       (shortage penalty, weighted by urgency and drug criticality)
    s.t.  sum_p x_pj + u_ij  = need_ij       for every deficit PHC i and drug j
          sum_p x_pj        <= surplus_kj   for every donor PHC k and drug j
          x_pj              <= M_pj * y_p   (a unit only moves if the trip is made)
          x, u >= 0,  y in {0,1}

`y_p` is shared by all drugs on the same donor -> recipient lane, so the optimiser
*consolidates* multiple medicines onto one vehicle. Needs a lane can't meet economically are
escalated to the district warehouse as emergency indents.
"""
import hashlib
import logging

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from . import config

# INR value of an unmet unit - encodes clinical criticality (ASV and oxytocin are life-saving).
SHORTAGE_PENALTY = {"PCM": 60, "ORS": 45, "ZNC": 60, "AMX": 90, "IFA": 40, "MET": 70,
                    "AML": 70, "ACT": 450, "ASV": 4000, "OXY": 900}
HANDLING_PER_UNIT = 0.5
CANDIDATES_PER_DEFICIT = 6
MAX_KM_SAME_STATE = 220.0
MAX_KM_CROSS_STATE = 450.0
log = logging.getLogger("phc.redistribution")


def lane_cost(road_km: float, cross_state: bool) -> float:
    return (config.FIXED_TRIP_COST + config.COST_PER_KM * road_km
            + (config.CROSS_STATE_ADMIN_COST if cross_state else 0.0))


def optimise(deficits: list, donors: list, phcs: list, road_km: np.ndarray,
             allow_cross_state: bool = False) -> dict:
    """Without inter-state lanes the problem separates by state: solve each state's MILP
    independently (this is also how it scales nationally - one small problem per state)."""
    if allow_cross_state:
        return _optimise(deficits, donors, phcs, road_km, True)
    parts = []
    for sc in sorted({p["state_code"] for p in phcs}):
        parts.append(_optimise([d for d in deficits if phcs[d["phc_idx"]]["state_code"] == sc],
                               [d for d in donors if phcs[d["phc_idx"]]["state_code"] == sc],
                               phcs, road_km, False))
    ships = sorted([s for p in parts for s in p["shipments"]], key=lambda s: s["urgency_days"])
    esc = sorted([e for p in parts for e in p["escalations"]], key=lambda e: e["needed_in_days"])
    met = sum(p["stats"]["units_moved"] for p in parts)
    need = sum(p["stats"]["units_needed"] for p in parts)
    return {"shipments": ships, "escalations": esc,
            "stats": _stats(len(ships), met, need, "HiGHS MILP, solved per state",
                            cost=float(sum(s["cost_inr"] for s in ships)),
                            lanes=sum(p["stats"].get("lanes", 0) for p in parts),
                            variables=sum(p["stats"].get("variables", 0) for p in parts),
                            failed=any(p["stats"].get("failed") for p in parts),
                            time_limited=any(p["stats"].get("time_limited") for p in parts))}


def _optimise(deficits: list, donors: list, phcs: list, road_km: np.ndarray,
              allow_cross_state: bool = False) -> dict:
    """deficits: [{phc_idx, drug, need, days_to_stockout}], donors: [{phc_idx, drug, surplus}]"""
    donors_by_drug = {}
    for d in donors:
        donors_by_drug.setdefault(d["drug"], []).append(d)

    # Candidate lanes: nearest eligible donors for each deficit.
    lanes = {}           # (k, i) -> list of (deficit_idx, donor_idx)
    for di, df in enumerate(deficits):
        i = df["phc_idx"]
        cands = []
        for ki, dn in enumerate(donors_by_drug.get(df["drug"], [])):
            k = dn["phc_idx"]
            if k == i:
                continue
            cross = phcs[k]["state_code"] != phcs[i]["state_code"]
            if cross and not allow_cross_state:
                continue
            if road_km[k, i] > (MAX_KM_CROSS_STATE if cross else MAX_KM_SAME_STATE):
                continue
            cands.append((road_km[k, i], dn))
        cands.sort(key=lambda c: c[0])
        for _, dn in cands[:CANDIDATES_PER_DEFICIT]:
            lanes.setdefault((dn["phc_idx"], i), []).append((di, id(dn)))

    donor_obj = {id(d): d for d in donors}
    lane_keys = list(lanes)
    x_index = []          # (lane_pos, deficit_idx, donor_obj_id)
    for lp, key in enumerate(lane_keys):
        for di, dnid in lanes[key]:
            x_index.append((lp, di, dnid))
    nx, ny, nu = len(x_index), len(lane_keys), len(deficits)
    if nu == 0:
        return {"shipments": [], "escalations": [], "stats": _stats(0, 0, 0, "no deficits")}

    # Objective
    c = np.zeros(nx + ny + nu)
    c[:nx] = HANDLING_PER_UNIT
    for lp, (k, i) in enumerate(lane_keys):
        cross = phcs[k]["state_code"] != phcs[i]["state_code"]
        c[nx + lp] = lane_cost(road_km[k, i], cross)
    for di, df in enumerate(deficits):
        urgency = 1.0 + 14.0 / (1.0 + max(df["days_to_stockout"], 0))
        c[nx + ny + di] = SHORTAGE_PENALTY.get(df["drug"], 60) * urgency

    A, lo, hi = [], [], []
    # demand balance per deficit
    for di, df in enumerate(deficits):
        row = np.zeros(nx + ny + nu)
        for xi, (_, d2, _) in enumerate(x_index):
            if d2 == di:
                row[xi] = 1
        row[nx + ny + di] = 1
        A.append(row); lo.append(df["need"]); hi.append(df["need"])
    # donor capacity
    for dn in donors:
        row = np.zeros(nx + ny + nu)
        used = False
        for xi, (_, _, dnid) in enumerate(x_index):
            if dnid == id(dn):
                row[xi] = 1; used = True
        if used:
            A.append(row); lo.append(-np.inf); hi.append(dn["surplus"])
    # linking x <= M y
    for xi, (lp, di, dnid) in enumerate(x_index):
        row = np.zeros(nx + ny + nu)
        row[xi] = 1
        row[nx + lp] = -min(deficits[di]["need"], donor_obj[dnid]["surplus"])
        A.append(row); lo.append(-np.inf); hi.append(0)

    integrality = np.zeros(nx + ny + nu)
    integrality[nx:nx + ny] = 1
    ub = np.full(nx + ny + nu, np.inf)
    ub[nx:nx + ny] = 1
    res = milp(c, constraints=LinearConstraint(np.array(A), lo, hi), integrality=integrality,
               bounds=Bounds(np.zeros_like(ub), ub),
               options={"time_limit": 8, "mip_rel_gap": 0.01})
    if res.x is None:
        # Never let a solver failure look like "nothing to move": flag it for the dashboard.
        log.error("redistribution MILP failed (status %s): %s", res.status, res.message)
        return {"shipments": [], "escalations": [], "stats": _stats(
            0, 0, float(sum(d["need"] for d in deficits)), res.message, failed=True)}
    if res.status == 1:
        log.warning("redistribution MILP hit its time limit; plan may be sub-optimal")

    x, y, u = res.x[:nx], res.x[nx:nx + ny], res.x[nx + ny:]
    shipments = {}
    for xi, (lp, di, dnid) in enumerate(x_index):
        qty = x[xi]
        if qty < 0.5 or y[lp] < 0.5:
            continue
        k, i = lane_keys[lp]
        dn, df = donor_obj[dnid], deficits[di]
        qty = float(min(np.ceil(qty), np.floor(dn["surplus"])))
        s = shipments.setdefault(lp, {"from_idx": k, "to_idx": i, "lines": []})
        s["lines"].append({"drug_code": df["drug"], "qty": qty,
                           "needed_in_days": df["days_to_stockout"], "need": df["need"],
                           "donor_surplus": dn["surplus"]})
    out = []
    for lp, s in shipments.items():
        k, i = s["from_idx"], s["to_idx"]
        cross = phcs[k]["state_code"] != phcs[i]["state_code"]
        km = float(road_km[k, i])
        s.update(
            distance_km=round(km, 1), cost_inr=round(lane_cost(km, cross)),
            eta_hours=round(km / config.AVG_SPEED_KMPH + 2.0, 1), cross_state=cross,
            cross_district=phcs[k]["district_code"] != phcs[i]["district_code"],
            urgency_days=min(l["needed_in_days"] for l in s["lines"]))
        sig = f"{k}-{i}-" + "-".join(f"{l['drug_code']}:{l['qty']}" for l in s["lines"])
        s["id"] = "REC-" + hashlib.sha1(sig.encode()).hexdigest()[:8].upper()
        out.append(s)
    out.sort(key=lambda s: s["urgency_days"])

    escalations = []
    for di, df in enumerate(deficits):
        if u[di] >= 1:
            escalations.append({"phc_idx": df["phc_idx"], "drug_code": df["drug"],
                                "qty": float(np.ceil(u[di])), "needed_in_days": df["days_to_stockout"]})
    escalations.sort(key=lambda e: e["needed_in_days"])
    met = float(x.sum())
    total_need = float(sum(d["need"] for d in deficits))
    return {"shipments": out, "escalations": escalations,
            "stats": _stats(len(out), met, total_need, res.message,
                            cost=float(sum(s["cost_inr"] for s in out)),
                            lanes=ny, variables=nx + ny + nu, time_limited=res.status == 1)}


def _stats(n, met, need, msg, **kw):
    return {"shipments": n, "units_moved": round(met), "units_needed": round(need),
            "coverage": round(met / need, 3) if need else None, "solver": str(msg), **kw}
