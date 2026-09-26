"""The Gemini code path, with the model call mocked (CI has no API key)."""
import os
import tempfile

os.environ.setdefault("PHC_DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))

from fastapi.testclient import TestClient  # noqa: E402

from app import gemini  # noqa: E402
from app.main import app  # noqa: E402

FAKE = {
    "transcript": "பாராசிட்டமால் 150, ஓஆர்எஸ் 60", "detected_language": "ta",
    "english_translation": "Paracetamol 150, ORS 60",
    "stock": [{"drug_code": "PCM", "quantity": 150, "kind": "remaining"},
              {"drug_code": "XYZ", "quantity": 5, "kind": "remaining"}],   # hallucinated code
    "opd_count": 70, "fever_cases": None, "diarrhoea_cases": None, "respiratory_cases": None,
    "beds_occupied": None, "staff_present": None, "notes": None,
    "confirmation": "நன்றி", "follow_up_question": "எத்தனை படுக்கைகள்?", "confidence": 0.9,
}


def _auth(c):
    tok = c.post("/api/auth/login", json={"persona_id": "phc-22"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_voice_upload_uses_gemini(monkeypatch):
    seen = {}

    def fake_gen(contents, schema):
        seen["parts"] = contents
        return dict(FAKE)

    monkeypatch.setattr(gemini, "client", lambda: object())
    monkeypatch.setattr(gemini, "_gen_json", fake_gen)
    with TestClient(app) as c:
        wav = b"RIFF" + b"\x00" * 40
        r = c.post("/api/reports/voice", headers=_auth(c), data={"phc_id": 22, "language": "ta"},
                   files={"audio": ("r.wav", wav, "audio/wav")})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["engine"] == gemini.config.GEMINI_MODEL
    assert [s["drug_code"] for s in out["report"]["stock"]] == ["PCM"]   # invalid code dropped
    assert "Tamil" in seen["parts"][0]                                   # prompt names the language
    assert len(seen["parts"]) == 2                                       # prompt + audio part


def test_tts_returns_wav(monkeypatch):
    from types import SimpleNamespace
    seen = {}

    class Models:
        def generate_content(self, model, contents, config):
            seen["model"], seen["lang"] = model, config.speech_config.language_code
            part = SimpleNamespace(inline_data=SimpleNamespace(data=b"\x00\x01" * 2400,
                                                               mime_type="audio/L16;codec=pcm;rate=24000"))
            return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])

    fake = SimpleNamespace(models=Models())
    monkeypatch.setattr(gemini, "client", lambda: fake)
    gemini._tts_cache.clear()
    with TestClient(app) as c:
        assert c.post("/api/tts", json={"text": "நன்றி", "language": "ta"}).status_code == 401
        r = c.post("/api/tts", headers=_auth(c), json={"text": "நன்றி", "language": "ta"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    assert r.content[:4] == b"RIFF" and r.content[8:12] == b"WAVE"
    assert seen == {"model": gemini.config.GEMINI_TTS_MODEL, "lang": "ta-IN"}


def test_tts_without_gemini_is_explicit(monkeypatch):
    monkeypatch.setattr(gemini, "client", lambda: None)
    with TestClient(app) as c:
        r = c.post("/api/tts", headers=_auth(c), json={"text": "hello", "language": "en"})
    assert r.status_code == 503


def test_voice_without_gemini_is_explicit(monkeypatch):
    monkeypatch.setattr(gemini, "client", lambda: None)
    with TestClient(app) as c:
        r = c.post("/api/reports/voice", headers=_auth(c), data={"phc_id": 22, "language": "hi"},
                   files={"audio": ("r.wav", b"RIFF", "audio/wav")})
    assert r.status_code == 503 and "Gemini" in r.json()["detail"]
