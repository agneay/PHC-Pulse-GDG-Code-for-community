"""Speech in every scheduled language: native-digit transcripts, localised keywords and drug names,
and Gemini read-aloud for languages the TTS model has no explicit language code for."""
from types import SimpleNamespace

import pytest

from app import gemini, nlu
from app.reference import DRUGS, LANGUAGES


@pytest.mark.parametrize("text", [
    "প্যারাসিটামল ১৫০, বেড ৩, কর্মী ৯, আজ ৭২ জন রোগী",          # Bengali, Bengali digits
    "పారాసిటమాల్ 150, 3 పడకలు, 9 మంది సిబ్బంది, 72 రోగులు",      # Telugu
    "पॅरासिटामॉल १५०, खाटा ३, कर्मचारी ९, रुग्ण ७२",               # Marathi, Devanagari digits
    "પેરાસિટામોલ 150, પથારી 3, કર્મચારી 9, દર્દી 72",             # Gujarati
    "പാരസെറ്റമോൾ 150, കിടക്ക 3, ജീവനക്കാർ 9, രോഗി 72",           # Malayalam
    "ਪੈਰਾਸੀਟਾਮੋਲ 150, ਬਿਸਤਰ 3, ਸਟਾਫ਼ 9, ਮਰੀਜ਼ 72",                  # Punjabi
    "پیراسیٹامول ۱۵۰، بستر ۳، عملہ ۹، مریض ۷۲",                   # Urdu, Arabic-Indic digits
])
def test_rules_parser_understands_transcripts(text):
    r = nlu.parse(text)
    assert (r["stock"][0]["drug_code"], r["stock"][0]["quantity"]) == ("PCM", 150)
    assert (r["beds_occupied"], r["staff_present"], r["opd_count"]) == (3, 9, 72)


@pytest.mark.parametrize("lang", sorted(set(LANGUAGES) - {"en", "sat", "mni"}))
def test_drug_names_for_read_back(lang):
    assert all(lang in d["names"] for d in DRUGS)
    text = gemini.confirmation_text({"stock": [{"drug_code": "ORS", "quantity": 40}]}, lang, "PHC X")
    assert DRUGS[1]["names"][lang] in text


def test_tts_retries_without_language_code(monkeypatch):
    calls = []

    def generate_content(model, contents, config):
        code = config.speech_config.language_code
        calls.append(code)
        if code:
            raise ValueError("400 INVALID_ARGUMENT: unsupported language code")
        part = SimpleNamespace(inline_data=SimpleNamespace(data=b"\0\0" * 100, mime_type="audio/L16;rate=24000"))
        return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])

    fake = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    monkeypatch.setattr(gemini, "client", lambda: fake)
    gemini._tts_cache.clear()
    wav = gemini.tts("ᱵᱮᱥ", "sat")
    assert wav[:4] == b"RIFF" and calls == ["sat-IN", None]
