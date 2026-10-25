from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .config import get_settings
from .database import engine
from .routers import auth, internal, leads

settings = get_settings()
app = FastAPI(title="LeadFlow API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def enforce_origin(request: Request, call_next):
    unsafe = request.method in {"POST", "PUT", "PATCH", "DELETE"}
    internal_dispatch = request.url.path == "/api/internal/notifications/dispatch"
    if request.url.path.startswith("/api/") and unsafe and not internal_dispatch:
        origin = request.headers.get("origin", "").rstrip("/")
        if not origin or origin not in settings.allowed_origins:
            return JSONResponse(status_code=403, content={"detail": "Origin not allowed"})
    return await call_next(request)


@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable") from None
    return {"status": "ok"}


app.include_router(auth.router, prefix="/api")
app.include_router(leads.router, prefix="/api")
app.include_router(internal.router, prefix="/api")
