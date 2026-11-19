"""Central configuration. Every value can be overridden with an environment
variable or a `.env` file in the project root."""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv is optional
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
MODELS_DIR = os.path.join(BACKEND_DIR, "models")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.getenv("DB_PATH", os.path.join(DATA_DIR, "credai.db"))

APP_NAME = os.getenv("APP_NAME", "CredAI")
VERSION = os.getenv("VERSION", "2.1.0")
LENDER_NAME = os.getenv("LENDER_NAME", "CredAI Finance (Demo NBFC)")

# Comma separated list. "*" allows every origin (credentials are then disabled).
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

# If ADMIN_API_KEY is empty the dashboard runs in open "demo mode".
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "").strip()

# Optional LLM (Groq, OpenAI-compatible). Without a key a deterministic
# rule-based profiler is used instead.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

# Optional server-side face recognition with DeepFace (heavy: TensorFlow).
# The browser already does face matching + liveness with face-api.js.
ENABLE_DEEPFACE = os.getenv("ENABLE_DEEPFACE", "auto").lower()  # auto | true | false

# Lending policy (all amounts in INR)
POLICY = {
    "min_age": 21,
    "max_age_at_maturity": 65,
    "min_monthly_income": 15000,
    "min_loan": 10000,
    "max_loan": 4000000,
    "max_foir": 0.50,            # max share of income going to all EMIs
    "min_tenure": 6,
    "max_tenure": 60,
    "base_rate": 10.5,          # best-case annual rate %
    "max_rate": 24.0,           # cap annual rate %
    "processing_fee_pct": 1.5,
    "population_default_rate": 0.0807,  # Home Credit training prior
}
