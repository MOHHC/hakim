"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware.rate_limiter import RateLimitMiddleware
from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.api.routes.triage import router as triage_router
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    yield
    # Drain Langfuse's async event queue before the process exits
    from app.core.observability import flush  # noqa: PLC0415

    flush()


app = FastAPI(
    lifespan=lifespan,
    title=settings.app_name,
    version="0.1.0",
    description=(
        "AI-powered medical triage assistant for Arabic speakers. "
        "Supports Lebanese dialect, Franco-Arab, and English input."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# Middleware
#
# Starlette runs the middleware added LAST first, so CORS is added last to wrap
# everything: preflights are answered before the rate limiter, and the limiter's
# 429 still carries CORS headers.  With the order reversed the browser saw a
# 429 as a CORS failure and showed "Connection error" instead of "please wait".
# ---------------------------------------------------------------------------

app.add_middleware(RateLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(health_router)
app.include_router(chat_router)
app.include_router(triage_router)
