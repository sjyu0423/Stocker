from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from marketmind.api.routes import catalog, collections, health, research
from marketmind.config import get_settings

app = FastAPI(
    title="MarketMind API",
    version="0.1.0",
    description="Market intelligence foundation API (M0A)",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(health.router, prefix="/api/v1")
app.include_router(catalog.router, prefix="/api/v1")
app.include_router(collections.router, prefix="/api/v1")
app.include_router(research.router, prefix="/api/v1")
