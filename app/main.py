"""
Entry point FastAPI — Voice Agent Garage
Point d'entrée principal de l'application
"""
import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================================
# LIFESPAN (startup / shutdown)
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialisation et nettoyage de l'application."""

    # ── Startup ──────────────────────────────────────────────
    logger.info("🚀 Démarrage de Voice Agent Garage API")
    logger.info(f"   ENV     : {settings.APP_ENV}")
    logger.info(f"   PORT    : {settings.APP_PORT}")
    logger.info(f"   LLM     : {settings.ANTHROPIC_MODEL}")

    # Initialiser Supabase
    from app.db.supabase_client import init_supabase
    init_supabase()
    logger.info("✅ Supabase connecté")

    yield

    # ── Shutdown ─────────────────────────────────────────────
    from app.integrations.vapi_client import vapi_client
    await vapi_client.close()
    logger.info("👋 Arrêt de l'application")


# ============================================================
# APPLICATION FASTAPI
# ============================================================

app = FastAPI(
    title="Voice Agent Garage API",
    description=(
        "Agent IA vocal autonome pour garagistes et dépanneurs. "
        "Gestion des appels entrants, prise de RDV, "
        "détection d'urgences et synchronisation agenda."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs"     if not settings.is_production else None,
    redoc_url="/redoc"   if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
)

# ── CORS ─────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.APP_FRONTEND_URL, settings.APP_BASE_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# ROUTES
# ============================================================

# ── Health check ─────────────────────────────────────────────
@app.get("/health", tags=["monitoring"])
async def health_check():
    """Endpoint de santé pour Google Cloud Run."""
    return {
        "status":  "healthy",
        "env":     settings.APP_ENV,
        "version": "1.0.0",
    }

@app.get("/", tags=["monitoring"])
async def root():
    """Route racine."""
    return {
        "name":    "Voice Agent Garage API",
        "status":  "running",
        "version": "1.0.0",
    }


# ── Webhooks Vapi ─────────────────────────────────────────────
from app.api.webhooks import router as webhooks_router
app.include_router(webhooks_router, prefix="/api")


# ── Tools (appelés par l'agent Vapi) ─────────────────────────
from app.api.tools import router as tools_router
app.include_router(tools_router, prefix="/api")


# ============================================================
# GESTION DES ERREURS
# ============================================================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"❌ Erreur non gérée : {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error":   "internal_server_error",
            "message": "Une erreur interne est survenue.",
        },
    )


# ============================================================
# LANCEMENT LOCAL
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.APP_PORT,
        reload=settings.is_development,
        log_level=settings.LOG_LEVEL.lower(),
    )