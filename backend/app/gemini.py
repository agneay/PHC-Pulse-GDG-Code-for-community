"""Gemini integration: the GenAI layer of PHC Pulse.

1. Voice report understanding - raw audio (any Indian language) -> transcript, translation and
   a validated structured report, plus a read-back confirmation in the worker's language and
   a follow-up question for anything missing. One multimodal call; no separate STT hop.
2. District / state briefings - turns the engine's numbers into a prioritised action brief
   in the officer's language.
3. Copilot Q&A - grounded answers over the live resilience snapshot.
4. Outbreak alert drafting - an IDSP-style rapid-response alert for a detected cluster.

Every function degrades gracefully to deterministic templates when no Gemini credentials are
configured, and reports which engine produced the output.
"""
import json
import logging
from typing import List, Optional

from pydantic import BaseModel, Field

from . import config, nlu
from .reference import DRUGS, LANGUAGES

log = logging.getLogger("phc.gemini")
STOCK_KINDS = ("remaining", "received", "discarded")
_client = None
_client_err = None


def client():
    global _client, _client_err
    if _client is not None or _client_err is not None:
        return _client
    try:
        from google import genai
        if config.USE_VERTEX:
            _client = genai.Client(vertexai=True, project=config.GCP_PROJECT,
                                   location=config.GCP_LOCATION)
        elif config.GEMINI_API_KEY:
            _client = genai.Client(api_key=config.GEMINI_API_KEY)
        else:
            _client_err = "no GEMINI_API_KEY / Vertex AI configured"
    except Exception as e:  # pragma: no cover
        _client_err = str(e)
    return _client


def status() -> dict:
    c = client()
    return {"enabled": c is not None, "model": config.GEMINI_MODEL if c else None,
            "backend": ("vertex-ai" if config.USE_VERTEX else "ai-studio") if c else None,
            "reason": None if c else _client_err}


# --------------------------------------------------------------------------- schemas
class StockLine(BaseModel):
    drug_code: str = Field(description="One of the drug codes from the catalogue")
    quantity: float = Field(description="Number of units (strips/sachets/vials/...)")
    kind: str = Field(description="'remaining' for current stock on shelf, 'received' for new supply "
                                  "received today, 'discarded' for expired or damaged stock thrown away today")


class ParsedReport(BaseModel):
    transcript: str = Field(description="Verbatim transcript in the original language and script")
    detected_language: str = Field(description="ISO 639-1 code, e.g. hi, ta, kn, or, te, bn, mr, en")
    english_translation: str
    stock: List[StockLine]
    opd_count: Optional[int] = None
    fever_cases: Optional[int] = None
    diarrhoea_cases: Optional[int] = None
    respiratory_cases: Optional[int] = None
    beds_occupied: Optional[int] = None
    staff_present: Optional[int] = None
    notes: Optional[str] = Field(default=None, description="Anything else clinically relevant, in English")
    confirmation: str = Field(description="Short read-back of the recorded numbers in the worker's language")
    follow_up_question: Optional[str] = Field(
        default=None, description="One short question in the worker's language asking for the most important missing item, or null")
    confidence: float = Field(description="0-1 confidence that numbers were captured correctly")


class Briefing(BaseModel):
    headline: str
    summary: str
    actions: List[str]
    risks: List[str]


def _catalogue() -> str:
    return "\n".join(
        f"- {d['code']}: {d['name']} (unit: {d['unit']}; also called: {', '.join(d['aliases'][:4])}; "
        f"hi: {d['names']['hi']}, ta: {d['names']['ta']}, kn: {d['names']['kn']}, or: {d['names']['or']})"
        for d in DRUGS)


VOICE_PROMPT = """You are the voice-report assistant of PHC Pulse, used by ASHA/ANM and Primary
Health Centre staff in India. The worker at {phc_name} ({district}, {state}) has just reported
today's status by voice, possibly in {lang_name} or mixing languages (code-switching is normal).

Extract a structured daily report:
- Remaining stock (and any stock received today) for the drugs below. Map local-language or
  brand names to the drug code. Quantities are in the drug's unit; if the worker says "boxes"
  or "packets", keep the number as said and mention it in notes.
- Expired or damaged units that were thrown away are kind "discarded" (not "remaining"), so
  they are not mistaken for medicine given to patients.
- OPD footfall today, fever / diarrhoea / respiratory case counts, beds occupied, staff present.
- Never invent numbers that were not said. Use null for anything not mentioned.

Drug catalogue:
{catalogue}

{previous}
Then write `confirmation`: a short, friendly read-back of every number you recorded, in the
worker's language ({lang_name}, native script), suitable for text-to-speech.
If an important item is missing (beds, staff, OPD, or paracetamol/ORS stock) write ONE short
`follow_up_question` in the same language; otherwise null."""


def _gen_json(contents, schema):
    from google.genai import types
    resp = client().models.generate_content(
        model=config.GEMINI_MODEL, contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=schema, temperature=0.1))
    if getattr(resp, "parsed", None) is not None:
        p = resp.parsed
        return p.model_dump() if hasattr(p, "model_dump") else p
    return json.loads(resp.text)


def parse_report(*, phc: dict, district: str, state: str, language: str,
                 audio: Optional[bytes] = None, mime_type: str = "audio/wav",
                 text: Optional[str] = None, previous: Optional[dict] = None) -> dict:
    """Returns {"report": ParsedReport-like dict, "engine": str}."""
    lang_name = LANGUAGES.get(language, LANGUAGES["en"])["name"]
    if client() is not None:
        from google.genai import types
        prev = ""
        if previous:
            prev = ("This is a FOLLOW-UP answer. Merge it with the earlier partial report below; "
                    "keep earlier values unless the worker corrects them:\n"
                    + json.dumps({k: v for k, v in previous.items() if k not in ("confirmation",)},
                                 ensure_ascii=False) + "\n")
        prompt = VOICE_PROMPT.format(phc_name=phc["name"], district=district, state=state,
                                     lang_name=lang_name, catalogue=_catalogue(), previous=prev)
        contents = [prompt]
        if audio:
            contents.append(types.Part.from_bytes(data=audio, mime_type=mime_type))
        if text:
            contents.append(f"Worker's report (transcribed text): {text}")
        try:
            rep = _gen_json(contents, ParsedReport)
            rep["stock"] = [{**s, "kind": s.get("kind") if s.get("kind") in STOCK_KINDS else "remaining"}
                            for s in rep.get("stock", []) if s.get("drug_code") in
                            {d["code"] for d in DRUGS}]
            return {"report": rep, "engine": config.GEMINI_MODEL}
        except Exception as e:
            log.exception("Gemini parse failed")
            if not text:
                raise RuntimeError(f"Gemini could not process the audio: {e}") from e
    if not text:
        raise RuntimeError("Audio understanding needs Gemini. Configure GEMINI_API_KEY, or use the "
                           "browser speech-to-text / text mode.")
    return {"report": _fallback_report(text, language, phc, previous), "engine": "rules-fallback"}


CONFIRM_TEMPLATES = {
    "en": "Thank you. Recorded for {phc}: {items}.",
    "hi": "धन्यवाद। {phc} के लिए दर्ज किया गया: {items}।",
    "ta": "நன்றி. {phc} க்காக பதிவு செய்யப்பட்டது: {items}.",
    "kn": "ಧನ್ಯವಾದಗಳು. {phc} ಗಾಗಿ ದಾಖಲಿಸಲಾಗಿದೆ: {items}.",
    "or": "ଧନ୍ୟବାଦ। {phc} ପାଇଁ ରେକର୍ଡ କରାଗଲା: {items}।",
}
FIELD_LABELS = {
    "en": {"beds_occupied": "beds occupied", "staff_present": "staff present", "opd_count": "OPD patients"},
    "hi": {"beds_occupied": "भरे बिस्तर", "staff_present": "उपस्थित स्टाफ", "opd_count": "ओपीडी मरीज़"},
    "ta": {"beds_occupied": "நிரம்பிய படுக்கைகள்", "staff_present": "பணியிலுள்ள ஊழியர்கள்", "opd_count": "புறநோயாளிகள்"},
    "kn": {"beds_occupied": "ಭರ್ತಿಯಾದ ಹಾಸಿಗೆಗಳು", "staff_present": "ಹಾಜರಿರುವ ಸಿಬ್ಬಂದಿ", "opd_count": "ಹೊರರೋಗಿಗಳು"},
    "or": {"beds_occupied": "ଭର୍ତ୍ତି ଶଯ୍ୟା", "staff_present": "ଉପସ୍ଥିତ କର୍ମଚାରୀ", "opd_count": "ଓପିଡି ରୋଗୀ"},
}
KIND_LABELS = {
    "en": {"received": "received", "discarded": "discarded"},
    "hi": {"received": "प्राप्त", "discarded": "नष्ट"},
    "ta": {"received": "பெறப்பட்டது", "discarded": "அழிக்கப்பட்டது"},
    "kn": {"received": "ಸ್ವೀಕರಿಸಲಾಗಿದೆ", "discarded": "ನಾಶಪಡಿಸಲಾಗಿದೆ"},
    "or": {"received": "ପ୍ରାପ୍ତ", "discarded": "ନଷ୍ଟ"},
}
FOLLOW_UP = {
    "en": "How many beds are occupied and how many staff are present today?",
    "hi": "आज कितने बिस्तर भरे हैं और कितने स्टाफ उपस्थित हैं?",
    "ta": "இன்று எத்தனை படுக்கைகள் நிரம்பியுள்ளன, எத்தனை ஊழியர்கள் வந்துள்ளனர்?",
    "kn": "ಇಂದು ಎಷ್ಟು ಹಾಸಿಗೆಗಳು ಭರ್ತಿಯಾಗಿವೆ ಮತ್ತು ಎಷ್ಟು ಸಿಬ್ಬಂದಿ ಹಾಜರಿದ್ದಾರೆ?",
    "or": "ଆଜି କେତୋଟି ଶଯ୍ୟା ଭର୍ତ୍ତି ଅଛି ଏବଂ କେତେ ଜଣ କର୍ମଚାରୀ ଉପସ୍ଥିତ ଅଛନ୍ତି?",
}


def confirmation_text(rep: dict, language: str, phc_name: str) -> str:
    lang = language if language in CONFIRM_TEMPLATES else "en"
    parts = []
    for s in rep.get("stock", []):
        d = next(d for d in DRUGS if d["code"] == s["drug_code"])
        name = d["names"].get(lang, d["name"]) if lang != "en" else d["name"]
        tag = f" ({KIND_LABELS[lang][s['kind']]})" if s.get("kind") in KIND_LABELS[lang] else ""
        parts.append(f"{name} {s['quantity']:g}{tag}")
    for k in ("beds_occupied", "staff_present", "opd_count"):
        if rep.get(k) is not None:
            parts.append(f"{FIELD_LABELS[lang][k]} {rep[k]}")
    return CONFIRM_TEMPLATES[lang].format(phc=phc_name, items=", ".join(parts) or "-")


def _fallback_report(text: str, language: str, phc: dict, previous: Optional[dict]) -> dict:
    p = nlu.parse(text)
    rep = dict(previous or {})
    stock = {(s["drug_code"], s.get("kind", "remaining")): s for s in rep.get("stock", [])}
    for s in p["stock"]:
        stock[(s["drug_code"], "remaining")] = {**s, "kind": "remaining"}
    for kind in ("received", "discarded"):
        for s in p[kind]:
            stock[(s["drug_code"], kind)] = {**s, "kind": kind}
    rep["stock"] = list(stock.values())
    for k in ("opd_count", "fever_cases", "diarrhoea_cases", "respiratory_cases",
              "beds_occupied", "staff_present"):
        if p.get(k) is not None:
            rep[k] = p[k]
    rep["transcript"] = ((previous or {}).get("transcript", "") + " " + text).strip()
    rep["detected_language"] = language
    rep["english_translation"] = rep["transcript"] if language == "en" else None
    rep["confirmation"] = confirmation_text(rep, language, phc["name"])
    missing = rep.get("beds_occupied") is None or rep.get("staff_present") is None
    rep["follow_up_question"] = FOLLOW_UP.get(language, FOLLOW_UP["en"]) if missing else None
    rep["confidence"] = 0.6
    rep.setdefault("notes", None)
    return rep


# --------------------------------------------------------------------------- briefings
BRIEF_PROMPT = """You are the analytics officer for PHC Pulse, briefing a {audience} in India.
Write in {lang_name} (native script). Be specific: name PHCs, drugs, days and quantities from the
data. Prioritise life-threatening items (anti-snake venom, oxytocin, malaria ACT) and outbreak
clusters. `actions` = 3-6 imperative, concrete next steps for today (approve named transfers,
send rapid-response team, raise emergency indent...). `risks` = 2-4 short bullets.
Only use facts present in the snapshot.

Snapshot (JSON):
{snapshot}"""


def briefing(snapshot: dict, audience: str, language: str) -> dict:
    lang_name = LANGUAGES.get(language, LANGUAGES["en"])["name"]
    if client() is not None:
        try:
            out = _gen_json([BRIEF_PROMPT.format(audience=audience, lang_name=lang_name,
                                                 snapshot=json.dumps(snapshot, ensure_ascii=False))],
                            Briefing)
            return {**out, "engine": config.GEMINI_MODEL}
        except Exception:
            log.exception("Gemini briefing failed")
    return {**_fallback_briefing(snapshot), "engine": "rules-fallback"}


def _fallback_briefing(s: dict) -> dict:
    k = s["kpis"]
    actions = []
    for sh in s.get("top_transfers", [])[:3]:
        actions.append(f"Approve transfer {sh['from']} -> {sh['to']}: " +
                       ", ".join(f"{l['qty']:g} {l['drug']}" for l in sh["lines"]) +
                       f" (needed in {sh['urgency_days']} days).")
    for c in s.get("clusters", [])[:2]:
        actions.append(f"Dispatch rapid response team to {', '.join(c['phcs'])} "
                       f"({c['syndrome']} cluster, {c['excess_cases']} excess cases).")
    for e in s.get("escalations", [])[:2]:
        actions.append(f"Raise emergency indent: {e['qty']:g} {e['drug']} for {e['phc']}.")
    silent = s.get("silent_phcs", [])
    if silent:
        actions.append(f"Call {len(silent)} PHC(s) silent for 3+ days before acting on their numbers: "
                       + ", ".join(p["phc"].split(" ")[0] for p in silent[:5]) + ".")
    return {
        "headline": f"{k['predicted_stockouts']} predicted stock-outs, {k['outbreak_clusters']} outbreak "
                    f"cluster(s), {k['recommended_transfers']} transfers ready for approval.",
        "summary": f"{k['phcs_reporting_today']} of {k['phcs']} PHCs reported today. "
                   f"{k['stocked_out_items']} drug lines are already at zero stock and "
                   f"{k['predicted_stockouts']} will run out before the next scheduled supply. "
                   f"Bed occupancy is {round(100 * (k['bed_occupancy'] or 0))}% and staff attendance "
                   f"{round(100 * (k['staff_attendance'] or 0))}%.",
        "actions": actions or ["No urgent action required today."],
        "risks": [f"{c['syndrome'].title()} cluster in {c['district']}" for c in s.get("clusters", [])][:4],
    }


ASK_PROMPT = """You are PHC Pulse Copilot for Indian public-health officers. Answer the question
using ONLY the live snapshot below. Be concise (<= 120 words), cite PHC codes and numbers, and
answer in the language of the question. If the snapshot doesn't contain the answer, say so.

Snapshot (JSON):
{snapshot}

Question: {question}"""


def ask(question: str, snapshot: dict) -> dict:
    if client() is None:
        return {"answer": "Gemini is not configured on this deployment, so free-form questions are "
                          "unavailable. Set GEMINI_API_KEY (or Vertex AI) to enable the copilot.",
                "engine": "rules-fallback"}
    try:
        resp = client().models.generate_content(
            model=config.GEMINI_MODEL,
            contents=[ASK_PROMPT.format(snapshot=json.dumps(snapshot, ensure_ascii=False),
                                        question=question)])
        return {"answer": resp.text, "engine": config.GEMINI_MODEL}
    except Exception as e:
        log.exception("Gemini ask failed")
        return {"answer": f"Gemini request failed: {e}", "engine": "error"}


class AlertDraft(BaseModel):
    title: str
    english: str
    local_language: str
    recommended_response: List[str]


ALERT_PROMPT = """Draft an early-warning alert for the District Surveillance Unit (IDSP) about
the following footfall anomaly cluster detected by PHC Pulse. Include likely differential
(e.g. acute diarrhoeal disease / cholera after flooding, dengue / AES / malaria for fever),
what to verify on the ground, samples to collect, and logistics (ORS/zinc, ACT, RDT kits).
`english`: <= 120 words. `local_language`: the same alert in {lang_name} for block-level staff.
`recommended_response`: 4-6 concrete steps. Cluster data: {cluster}"""


def outbreak_alert(cluster: dict, language: str) -> dict:
    lang_name = LANGUAGES.get(language, LANGUAGES["en"])["name"]
    if client() is not None:
        try:
            out = _gen_json([ALERT_PROMPT.format(lang_name=lang_name,
                                                 cluster=json.dumps(cluster, ensure_ascii=False))],
                            AlertDraft)
            return {**out, "engine": config.GEMINI_MODEL}
        except Exception:
            log.exception("Gemini alert failed")
    syn = cluster["syndrome"]
    steps = {
        "diarrhoea": ["Verify cases line-list at each PHC within 24h",
                      "Collect stool samples / rectal swabs for cholera culture",
                      "Test drinking-water sources; chlorinate wells and tanks",
                      "Pre-position ORS and zinc; open ORT corners",
                      "Report to IDSP on Form P/L"],
        "fever": ["Verify line-list and test with malaria RDT and dengue NS1/IgM",
                  "Look for AES signs (altered sensorium) and refer promptly",
                  "Intensify vector control and fogging around affected villages",
                  "Pre-position paracetamol, ACT and RDT kits", "Report to IDSP on Form P/L"],
    }.get(syn, ["Verify line-list", "Collect appropriate samples", "Report to IDSP"])
    text = (f"PHC Pulse detected a {syn} cluster in {cluster.get('district_name', cluster['district_code'])}: "
            f"{len(cluster['phc_codes'])} PHCs ({', '.join(cluster['phc_codes'])}) show footfall up to "
            f"{cluster['max_ratio']}x the expected level, ~{cluster['excess_cases']} excess cases over "
            f"{cluster['max_consecutive_days']} day(s). Rapid verification advised.")
    return {"title": f"Possible {syn} outbreak - {cluster.get('district_name', '')}", "english": text,
            "local_language": text, "recommended_response": steps, "engine": "rules-fallback"}
