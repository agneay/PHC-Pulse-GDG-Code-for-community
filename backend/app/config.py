"""Runtime configuration, read from environment variables."""
import os
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("PHC_DB_PATH", BASE_DIR / "data" / "phc_pulse.db"))
STATIC_DIR = Path(os.getenv("PHC_STATIC_DIR", BASE_DIR.parent / "frontend" / "dist"))

# Gemini: either an AI Studio key, or Vertex AI via Application Default Credentials.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
USE_VERTEX = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true", "yes")
GCP_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
GCP_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
# Read-aloud fallback for devices without an Indian-language voice.
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
GEMINI_TTS_VOICE = os.getenv("GEMINI_TTS_VOICE", "Kore")

# Token signing for the demo role-based access (row-level scoping by state/district/PHC).
AUTH_SECRET = os.getenv("PHC_AUTH_SECRET") or "phc-pulse-demo-secret-change-me"
if AUTH_SECRET in ("phc-pulse-demo-secret-change-me", "change-me") and os.getenv("K_SERVICE"):
    # K_SERVICE is set by Cloud Run: never serve publicly with a secret that is in the repo.
    raise RuntimeError("PHC_AUTH_SECRET must be set to a strong random value on Cloud Run")

# Seed: history length and the simulated "today". Defaults to the real current date.
HISTORY_DAYS = int(os.getenv("PHC_HISTORY_DAYS", "180"))
SEED = int(os.getenv("PHC_SEED", "42"))
_today_env = os.getenv("PHC_TODAY")
TODAY = date.fromisoformat(_today_env) if _today_env else date.today()
# The synthetic history is anchored to TODAY; re-seed when a stored database was generated for a
# different day (otherwise nobody has "reported today" and the demo scenario drifts away).
RESEED_IF_STALE = os.getenv("PHC_RESEED_IF_STALE", "1").lower() in ("1", "true", "yes")

# Planning parameters (the business rules of the early-warning + redistribution engine).
FORECAST_HORIZON = 28          # days forecast per PHC x drug
WARNING_WINDOW = 21            # flag a stock-out predicted within this many days
STALE_DAYS = 3                 # a PHC silent this long is shown as unverified and kept out of
                               # outbreak detection and redistribution until it reports again
SUPPLY_CYCLE_DAYS = 30        # monthly indent from the district drug warehouse
SAFETY_DAYS = 7                # buffer stock both donor and recipient must keep after a transfer
SAFETY_FACTOR = 1.2            # donors plan against 120% of their own forecast demand
COST_PER_KM = 18.0             # INR per road-km for a district vehicle
FIXED_TRIP_COST = 600.0        # INR fixed dispatch/handling cost per shipment
CROSS_STATE_ADMIN_COST = 2500.0  # INR extra paperwork cost for inter-state transfer
ROAD_FACTOR = 1.3              # road distance ~ haversine x 1.3
AVG_SPEED_KMPH = 35.0
