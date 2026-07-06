"""FastAPI application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from polymarket_us.errors import APIStatusError, PolymarketUSError

from app.client import MissingCredentialsError
from app.config import get_settings
from app.routers import dashboard, raw

settings = get_settings()

app = FastAPI(
    title="Polymarket US Dashboard API",
    description="Groups Polymarket US order/position/trade data by event and contract.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(MissingCredentialsError)
async def _missing_credentials_handler(
    _request: Request, exc: MissingCredentialsError
) -> JSONResponse:
    """Configuration problem -> 503 with a clear, actionable message."""
    return JSONResponse(status_code=503, content={"error": "missing_credentials", "detail": str(exc)})


@app.exception_handler(APIStatusError)
async def _api_status_handler(_request: Request, exc: APIStatusError) -> JSONResponse:
    """Translate an upstream HTTP error into a sensible proxy status.

    Upstream 5xx becomes 502 (bad gateway); upstream 4xx is passed through so
    the caller sees the real cause (bad auth, not found, rate limited, ...).
    """
    status = 502 if exc.status_code >= 500 else exc.status_code
    return JSONResponse(
        status_code=status,
        content={"error": "upstream_error", "upstream_status": exc.status_code, "detail": exc.message},
    )


@app.exception_handler(PolymarketUSError)
async def _sdk_error_handler(_request: Request, exc: PolymarketUSError) -> JSONResponse:
    """Any other SDK error (connection/timeout) -> 502."""
    return JSONResponse(
        status_code=502,
        content={"error": "upstream_error", "detail": str(exc) or exc.__class__.__name__},
    )


@app.get("/api/health", tags=["health"])
def health() -> dict[str, object]:
    """Liveness probe. Reports whether credentials are configured (no secrets)."""
    return {
        "status": "ok",
        "credentials_configured": settings.has_credentials,
        "gateway_base_url": settings.polymarket_gateway_base_url,
        "api_base_url": settings.polymarket_api_base_url,
    }


app.include_router(dashboard.router)
app.include_router(raw.router)
