"""Feature-phone channels: USSD menu, SMS shortcode grammar and a Dialogflow CX (IVR) webhook.

USSD follows the Africa's Talking / Indian aggregator convention: every request carries the
full `text` path ("1*3*120*0"), and the reply starts with CON (continue) or END. The menu is
replayed from the path each time, so the gateway can be stateless and horizontally scaled."""
from typing import Optional

from . import gemini, nlu, service
from .db import get_conn, rows
from .reference import DRUGS

_submitted = set()   # USSD sessions already submitted (idempotency)


def worker_by_phone(phone: str) -> Optional[dict]:
    with get_conn() as conn:
        r = rows(conn, "SELECT w.*, p.code AS phc_code, p.name AS phc_name FROM workers w "
                       "JOIN phcs p ON p.id=w.phc_id WHERE w.phone=?", (phone,))
    return r[0] if r else None


def _replay(tokens):
    state, draft, note = "menu", {"stock": {}}, None
    for tok in tokens:
        tok = tok.strip()
        note = None
        if state == "menu":
            state = {"1": "drugs", "2": "beds", "3": "staff", "4": "opd", "5": "review"}.get(tok, "menu")
            if state == "menu":
                note = "Invalid option"
        elif state == "drugs":
            if tok == "0":
                state = "menu"
            elif tok.isdigit() and 1 <= int(tok) <= len(DRUGS):
                state = ("qty", DRUGS[int(tok) - 1]["code"])
            else:
                note = "Invalid option"
        elif isinstance(state, tuple):
            if tok.replace(".", "", 1).isdigit():
                draft["stock"][state[1]] = float(tok)
                note = f"Saved {state[1]} = {tok}"
                state = "saved"
            else:
                note = "Enter a number"
        elif state == "saved":
            state = "drugs" if tok == "1" else "menu"
        elif state in ("beds", "staff", "opd"):
            if tok.isdigit():
                draft[state] = int(tok)
                note = f"Saved {state} = {tok}"
                state = "menu"
            else:
                note = "Enter a number"
        elif state == "review":
            state = "submit" if tok == "1" else "menu"
    return state, draft, note


def ussd(session_id: str, phone: str, text: str) -> str:
    w = worker_by_phone(phone)
    if not w:
        return "END This number is not registered with PHC Pulse. Contact your MO."
    tokens = [t for t in (text or "").split("*") if t != ""]
    state, draft, note = _replay(tokens)
    head = (note + "\n") if note else ""
    if state == "menu":
        return (f"CON {head}PHC Pulse - {w['phc_code']}\n1. Drug stock\n2. Beds occupied\n"
                f"3. Staff present\n4. OPD today\n5. Review & submit")
    if state == "drugs":
        lines = "\n".join(f"{k + 1}. {d['code']} {d['name'].split(' ')[0]}" for k, d in enumerate(DRUGS))
        return f"CON {head}Select drug:\n{lines}\n0. Back"
    if isinstance(state, tuple):
        d = next(d for d in DRUGS if d["code"] == state[1])
        return f"CON {head}{d['name']}\nEnter {d['unit']} remaining:"
    if state == "saved":
        return f"CON {head}1. Another drug\n0. Main menu"
    if state in ("beds", "staff", "opd"):
        label = {"beds": "beds occupied now", "staff": "staff present today", "opd": "OPD patients today"}
        return f"CON {head}Enter {label[state]}:"
    report = _draft_to_report(draft)
    summary = _summary(report)
    if state == "review":
        return f"CON Today's report:\n{summary}\n1. Submit\n0. Edit"
    if state == "submit":
        if session_id not in _submitted:
            service.apply_report(w["phc_id"], report, "ussd", "en", "ussd-menu", reporter=phone)
            _submitted.add(session_id)
        return f"END Submitted for {w['phc_code']}. Thank you!\n{summary}"
    return "END Session ended."


def _draft_to_report(draft: dict) -> dict:
    rep = {"stock": [{"drug_code": c, "quantity": q, "kind": "remaining"}
                     for c, q in draft["stock"].items()]}
    if "beds" in draft: rep["beds_occupied"] = draft["beds"]
    if "staff" in draft: rep["staff_present"] = draft["staff"]
    if "opd" in draft: rep["opd_count"] = draft["opd"]
    return rep


def _summary(rep: dict) -> str:
    parts = [f"{s['drug_code']} {s['quantity']:g}" for s in rep.get("stock", [])]
    for k, lab in (("beds_occupied", "BED"), ("staff_present", "STF"), ("opd_count", "OPD")):
        if rep.get(k) is not None:
            parts.append(f"{lab} {rep[k]}")
    return ", ".join(parts) or "(empty)"


def sms(phone: str, text: str) -> dict:
    """SMS grammar: 'PCM 120 ORS 40 BED 4 STF 9 OPD 85' (free text also accepted)."""
    w = worker_by_phone(phone)
    if not w:
        return {"reply": "Number not registered with PHC Pulse.", "saved": False}
    p = nlu.parse(text)
    rep = {"stock": [{**s, "kind": "remaining"} for s in p["stock"]] +
                    [{**s, "kind": "received"} for s in p["received"]]}
    for k in ("opd_count", "fever_cases", "diarrhoea_cases", "respiratory_cases",
              "beds_occupied", "staff_present"):
        if p.get(k) is not None:
            rep[k] = p[k]
    if not rep["stock"] and len(rep) == 1:
        return {"reply": "Could not read report. Format: PCM 120 ORS 40 BED 4 STF 9 OPD 85",
                "saved": False}
    rep["transcript"] = text
    service.apply_report(w["phc_id"], rep, "sms", w["language"], "sms-grammar", reporter=phone)
    return {"reply": f"PHC Pulse: saved for {w['phc_code']} - {_summary(rep)}", "saved": True,
            "report": rep}


def dialogflow_webhook(body: dict) -> dict:
    """Dialogflow CX webhook. Expects session parameters collected by the IVR agent:
    caller_phone | phc_code, plus any of drug codes (pcm, ors, ...), beds, staff, opd, and
    optional free-text `utterance`. Tag 'submit-report' persists the report."""
    params = (body.get("sessionInfo") or {}).get("parameters") or {}
    tag = (body.get("fulfillmentInfo") or {}).get("tag", "submit-report")
    lang = (body.get("languageCode") or "en").split("-")[0]
    w = worker_by_phone(str(params.get("caller_phone", ""))) if params.get("caller_phone") else None
    phc = service.find_phc(params.get("phc_code")) if not w and params.get("phc_code") else None
    phc_id = w["phc_id"] if w else (phc["id"] if phc else None)
    if not phc_id:
        return _df_reply("Sorry, I could not identify your health centre.")
    rep = {"stock": []}
    for d in DRUGS:
        v = params.get(d["code"].lower())
        if v not in (None, ""):
            rep["stock"].append({"drug_code": d["code"], "quantity": float(v), "kind": "remaining"})
    for src, dst in (("beds", "beds_occupied"), ("staff", "staff_present"), ("opd", "opd_count")):
        if params.get(src) not in (None, ""):
            rep[dst] = int(float(params[src]))
    if params.get("utterance"):
        p = nlu.parse(str(params["utterance"]))
        rep["stock"] += [{**s, "kind": "remaining"} for s in p["stock"]]
    phc_row = service.get_phc(phc_id)
    rep["confirmation"] = gemini.confirmation_text(rep, lang, phc_row["name"])
    if tag == "submit-report":
        service.apply_report(phc_id, rep, "ivr", lang, "dialogflow-cx", reporter=str(params.get("caller_phone")))
    return _df_reply(rep["confirmation"])


def _df_reply(text: str) -> dict:
    return {"fulfillment_response": {"messages": [{"text": {"text": [text]}}]}}
