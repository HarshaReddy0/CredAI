"""CredAI — FastAPI entry point.

Run locally:  uvicorn backend.main:app --reload --port 8000
Then open:    http://127.0.0.1:8000
"""
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend import db
from backend.config import ADMIN_API_KEY, APP_NAME, CORS_ORIGINS, ENABLE_DEEPFACE, FRONTEND_DIR, GROQ_API_KEY, VERSION
from backend.routes import admin, applications, assistant, face, session, tools
from backend.services import face_service
from backend.services.risk_service import load_models, models_loaded

log = logging.getLogger("credai")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    try:
        load_models()
        log.info("Risk model loaded")
    except Exception as e:  # app still serves the UI and tells the user
        log.error("Could not load risk model: %s", e)
    if ENABLE_DEEPFACE != "false":
        # warm the optional heavy import in the background so startup stays fast
        threading.Thread(target=face_service.deepface, daemon=True).start()
    yield


app = FastAPI(title=f"{APP_NAME} API", version=VERSION, lifespan=lifespan,
              description="AI video-KYC loan onboarding: voice interview, liveness, risk & fraud scoring.")

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials="*" not in CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    errors = [f"{'.'.join(str(p) for p in e['loc'][1:])}: {e['msg']}" for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": {"message": "Invalid request", "errors": errors}})


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(self), geolocation=(self)")
    if request.url.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


# ---- API routes must be registered BEFORE the static mount at "/"
for r in (assistant.router, session.router, applications.router, admin.router, face.router, tools.router):
    app.include_router(r)


@app.get("/api/health", tags=["Meta"])
def health():
    return {
        "status": "ok" if models_loaded() else "degraded",
        "version": VERSION,
        "models_loaded": models_loaded(),
        "server_face_engine": face_service.status(),
        "llm": "groq" if GROQ_API_KEY else "rule-based",
        "admin_protected": bool(ADMIN_API_KEY),
    }


# Old URLs from v1 keep working
_LEGACY = {"/credai-voice-kyc.html": "/", "/voice-app.html": "/apply.html",
           "/credai-voice-loan.html": "/apply.html", "/onboarding.html": "/apply.html"}


@app.middleware("http")
async def legacy_redirects(request: Request, call_next):
    if request.url.path in _LEGACY:
        return RedirectResponse(_LEGACY[request.url.path], status_code=301)
    return await call_next(request)


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
