"""Demo role-based access with row-level scoping (mirrors BigQuery row-level security by state).

Personas: national command centre, state officers, district health officers (DHO) and PHC
staff. Tokens are HMAC-signed so the API can trust the scope claim."""
import base64
import hashlib
import hmac
import json
from typing import Optional

from fastapi import Header, HTTPException

from . import config
from .reference import DISTRICTS, STATES


def personas() -> list:
    out = [{"id": "national", "role": "national", "name": "MoHFW National Command Centre",
            "scope": {}}]
    for s in STATES:
        out.append({"id": f"state-{s['code']}", "role": "state",
                    "name": f"State Health Officer, {s['name']}", "scope": {"state": s["code"]}})
    for d in DISTRICTS:
        out.append({"id": f"dho-{d['code']}", "role": "district",
                    "name": f"District Health Officer, {d['name']}",
                    "scope": {"state": d["state"], "district": d["code"]}})
    out.append({"id": "phc-22", "role": "phc", "name": "Medical Officer, PHC-22 Vandavasi",
                "scope": {"state": "TN", "district": "TVM", "phc_id": 22}})
    return out


def _sign(payload: bytes) -> str:
    return hmac.new(config.AUTH_SECRET.encode(), payload, hashlib.sha256).hexdigest()[:32]


def issue(persona_id: str) -> dict:
    p = next((p for p in personas() if p["id"] == persona_id), None)
    if not p:
        raise HTTPException(404, "unknown persona")
    body = base64.urlsafe_b64encode(json.dumps(p).encode()).decode()
    return {"token": f"{body}.{_sign(body.encode())}", "user": p}


def current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    """No token -> national read-only view (public demo)."""
    if not authorization:
        return personas()[0]
    tok = authorization.removeprefix("Bearer ").strip()
    try:
        body, sig = tok.rsplit(".", 1)
    except ValueError:
        raise HTTPException(401, "bad token")
    if not hmac.compare_digest(sig, _sign(body.encode())):
        raise HTTPException(401, "bad signature")
    return json.loads(base64.urlsafe_b64decode(body.encode()))


def effective_scope(user: dict, state: Optional[str] = None, district: Optional[str] = None) -> dict:
    """Narrow the user's scope by optional filters; never widen it."""
    sc = dict(user.get("scope", {}))
    if state and sc.get("state") in (None, state):
        sc["state"] = state
    if district and sc.get("district") in (None, district):
        d = next((d for d in DISTRICTS if d["code"] == district), None)
        if d and sc.get("state") in (None, d["state"]):
            sc["district"], sc["state"] = district, d["state"]
    return sc


def in_scope(scope: dict, phc: dict) -> bool:
    if scope.get("phc_id") and phc["id"] != scope["phc_id"]:
        return False
    if scope.get("district") and phc["district_code"] != scope["district"]:
        return False
    if scope.get("state") and phc["state_code"] != scope["state"]:
        return False
    return True
