"""Rule-based fallback parser, used only when Gemini is not configured. It understands
English / Hinglish free text ("paracetamol 120 strips, ORS 40, beds 4, staff 9, OPD 85")
and the compact SMS grammar ("PCM 120 ORS 40 BED 4 STF 9 OPD 85")."""
import re

from .reference import DRUGS

NUM_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
    "ninety": 90, "hundred": 100,
    # Hindi (romanised)
    "ek": 1, "teen": 3, "char": 4, "paanch": 5, "panch": 5, "chhe": 6, "saat": 7,
    "aath": 8, "nau": 9, "das": 10, "bees": 20, "tees": 30, "chalis": 40, "pachas": 50, "sau": 100,
}
FIELD_WORDS = {
    "beds_occupied": ["bed", "beds", "bistar", "admitted", "inpatient", "ipd",
                      "बिस्तर", "पलंग", "படுக்கை", "ಹಾಸಿಗೆ", "ଶଯ୍ୟା"],
    "staff_present": ["staff", "stf", "present", "attendance", "karmachari",
                      "स्टाफ", "कर्मचारी", "ஊழியர்", "ಸಿಬ್ಬಂದಿ", "କର୍ମଚାରୀ"],
    "opd_count": ["opd", "patients", "patient", "footfall", "marij", "mareez",
                  "ओपीडी", "मरीज़", "मरीज", "புறநோயாளி", "ಹೊರರೋಗಿ", "ରୋଗୀ", "ଓପିଡି"],
    "fever_cases": ["fever", "bukhar", "jwar", "fvr", "बुखार", "காய்ச்சல்", "ಜ್ವರ", "ଜ୍ୱର"],
    "diarrhoea_cases": ["diarrhoea", "diarrhea", "loose motion", "dast", "dia", "दस्त",
                        "வயிற்றுப்போக்கு", "ಅತಿಸಾರ", "ଝାଡ଼ା"],
    "respiratory_cases": ["cough", "respiratory", "khansi", "resp", "breathing", "खांसी",
                          "இருமல்", "ಕೆಮ್ಮು", "କାଶ"],
}


def _find(key: str, text: str):
    """Word-boundary match for Latin keys; plain substring for Indic scripts (where combining
    marks make \\b unreliable)."""
    if key.isascii():
        return re.search(r"\b" + re.escape(key), text)
    return re.search(re.escape(key), text)


def _normalise_numbers(text: str) -> str:
    def repl(m):
        return str(NUM_WORDS[m.group(0).lower()])
    pattern = r"\b(" + "|".join(sorted(NUM_WORDS, key=len, reverse=True)) + r")\b"
    return re.sub(pattern, repl, text, flags=re.I)


def parse(text: str) -> dict:
    t = _normalise_numbers(text.lower())
    t = re.sub(r"(\d),(\d)", r"\1\2", t)
    tokens = [(m.start(), m.end(), float(m.group())) for m in re.finditer(r"\d+(?:\.\d+)?", t)]
    used = set()
    # Clause boundaries: a keyword only binds to a number in the same clause.
    bounds = [m.start() for m in re.finditer(r"[,;।|\n]|\.(?=\s|$)", t)]

    def clause(pos):
        return sum(1 for b in bounds if b < pos)

    def nearest_number(pos_start, pos_end):
        best = None
        c = clause(pos_start)
        for k, (s, e, v) in enumerate(tokens):
            if k in used or clause(s) != c:
                continue
            dist = s - pos_end if s >= pos_end else pos_start - e
            if dist < 0:
                dist = 0
            if dist <= 25 and (best is None or dist < best[0] or (dist == best[0] and s >= pos_end)):
                best = (dist, k, v)
        if best:
            used.add(best[1])
            return best[2]
        return None

    out = {"stock": [], "received": []}
    # Received mentions: "received 200 paracetamol"
    for drug in DRUGS:
        keys = [drug["code"].lower()] + drug["aliases"] + [n.split(" (")[0] for n in drug["names"].values()]
        for key in sorted(keys, key=len, reverse=True):
            m = re.search(r"\b" + re.escape(key) + r"\b", t) if key.isascii() else _find(key, t)
            if m:
                window = t[max(0, m.start() - 20): m.start()]
                val = nearest_number(m.start(), m.end())
                if val is not None:
                    target = "received" if "receiv" in window or "mila" in window else "stock"
                    out[target].append({"drug_code": drug["code"], "quantity": val})
                break
    for field, words in FIELD_WORDS.items():
        for w in words:
            m = _find(w, t)
            if m:
                val = nearest_number(m.start(), m.end())
                if val is not None:
                    out[field] = int(val)
                break
    return out
