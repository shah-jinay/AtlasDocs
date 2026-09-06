"""FastAPI application entrypoint. Runs only the interactive query/control
plane -- ingestion happens in app.workers.main, a separate process/container,
which is the entire point of the architecture (blueprint section 4.2).
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import documents, health, query
from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(service="api", level=settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title="AtlasDocs API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment != "prod" else [],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(query.router)


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("AtlasDocs API starting", extra={"context": {"environment": settings.environment}})
