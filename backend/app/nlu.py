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


# Stock removed from the shelf without being dispensed (expired, damaged). Recorded as an
# adjustment so it does not count as patient demand in the forecast.
_DISCARD_WORDS = (r"\b(?:expired?|expiry|exp|damaged?|dmg|discard(?:ed)?|wasted?|broken|"
                  r"kharab|nasht|barbaad)\b|खराब|नष्ट|एक्सपायर|காலாவதி|சேதம்|ಹಾಳಾದ|ಅವಧಿ ಮೀರಿದ|ନଷ୍ଟ")
DISCARD = re.compile(_DISCARD_WORDS)
TRAILING_DISCARD = re.compile(r"^\s*(?:[a-z]+\s+)?(?:" + _DISCARD_WORDS + ")")  # "5 [strips] expired"
RECEIVED = re.compile(r"receiv|\bmila|मिला|मिले")


def _drug_keys(d):
    return [d["code"].lower()] + d["aliases"] + [n.split(" (")[0] for n in d["names"].values()]


DRUG_START = re.compile(r"\s*(?:" + "|".join(
    (r"\b" + re.escape(k) + r"\b") if k.isascii() else re.escape(k)
    for k in sorted({k for d in DRUGS for k in _drug_keys(d)}, key=len, reverse=True)) + ")")


def _find(key: str, text: str):
    """Whole-word match for Latin keys (plural allowed: "bed" also finds "beds", but "dia" does not
    find "diabetes"); plain substring for Indic scripts, where combining marks make \\b unreliable."""
    if key.isascii():
        return re.search(r"\b" + re.escape(key) + r"(?:s|es)?\b", text)
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
            return best[1]
        return None

    def kind_of(m, k):
        """'received' / 'discarded' from words just before the drug name ("received 200 PCM",
        "expired ORS 5", SMS "DMG ORS 5") or right after the item ("ORS 5 expired", "5 ORS
        damaged"). A discard word between two items belongs to the one that follows it, so a
        trailing one only counts when no other drug comes straight after it."""
        c = clause(m.start())
        start = max(m.start() - 25, bounds[c - 1] + 1 if c else 0)
        prev_end = max((e for j, (_, e, _) in enumerate(tokens) if e <= m.start() and j != k), default=-1)
        before = t[max(start, prev_end):m.start()]
        rest = t[max(m.end(), tokens[k][1]):]
        tail = TRAILING_DISCARD.match(rest)
        if tail and not DRUG_START.match(rest[tail.end():]):
            return "discarded"
        if DISCARD.search(before):
            return "discarded"
        return "received" if RECEIVED.search(before) else "stock"

    out = {"stock": [], "received": [], "discarded": []}
    for drug in DRUGS:
        for key in sorted(_drug_keys(drug), key=len, reverse=True):
            pat = r"\b" + re.escape(key) + r"\b" if key.isascii() else re.escape(key)
            found = list(re.finditer(pat, t))
            for m in found:           # every mention: "PCM 120 ... expired PCM 10"
                k = nearest_number(m.start(), m.end())
                if k is not None:
                    out[kind_of(m, k)].append({"drug_code": drug["code"], "quantity": tokens[k][2]})
            if found:
                break
    for field, words in FIELD_WORDS.items():
        for w in words:
            m = _find(w, t)
            if m:
                k = nearest_number(m.start(), m.end())
                if k is not None:
                    out[field] = int(tokens[k][2])
                break
    return out
