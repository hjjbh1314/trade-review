"""Trade Review · FastAPI entrypoint.

Run with `./start.sh` (loopback) or `./start.sh --tailscale` (private mesh).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.ai import get_ai_engine
from backend.ai.claude_engine import ClaudeEngine
from backend.auth import TokenAuthMiddleware, token_required_for_client
from backend.api.chat import router as chat_router
from backend.api.daily import router as daily_router
from backend.api.flash import router as flash_router
from backend.api.market import router as market_router
from backend.api.mindset import router as mindset_router
from backend.api.positions import router as positions_router
from backend.api.trades import router as trades_router
from backend.db.repo import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    engine = None
    try:
        engine = get_ai_engine()
        if isinstance(engine, ClaudeEngine):
            log.info("warming up persistent Claude session ...")
            await engine.connect()
            log.info("Claude warm-up done ✓")
    except Exception as e:
        log.warning("Claude warm-up skipped (%s)", e)

    yield

    if isinstance(engine, ClaudeEngine):
        try:
            await engine.close()
        except Exception as e:
            log.warning("Claude shutdown error: %s", e)


app = FastAPI(title="Trade Review", version="0.1.0", lifespan=lifespan)

# CORS: this app is single-origin (frontend served from the same FastAPI port).
# We only relax during local dev when Vite runs on 5173.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
app.add_middleware(TokenAuthMiddleware)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/auth-status")
def auth_status() -> dict[str, bool]:
    """Frontend probe: does the server require a token for /api/* ?"""
    return {"required": token_required_for_client()}


app.include_router(chat_router)
app.include_router(daily_router)
app.include_router(flash_router)
app.include_router(market_router)
app.include_router(mindset_router)
app.include_router(positions_router)
app.include_router(trades_router)


# ─── Serve the built frontend (production single-port mode) ───────────
_DIST_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if _DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=_DIST_DIR / "assets"), name="assets")

    @app.get("/favicon.svg")
    def _favicon():
        return FileResponse(_DIST_DIR / "favicon.svg")

    @app.get("/icons.svg")
    def _icons():
        return FileResponse(_DIST_DIR / "icons.svg")

    @app.get("/{full_path:path}")
    def _spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(_DIST_DIR / "index.html")
else:
    log.warning(
        "frontend/dist not found — only the API is served. "
        "Run `npm run build` in frontend/ first, or use `./start.sh`."
    )
