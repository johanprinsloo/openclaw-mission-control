from fastapi import FastAPI
from app.api.v1 import api_router
from app.core.database import engine
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()

app = FastAPI(title="Mission Control", version="1.0.0", lifespan=lifespan)

app.include_router(api_router, prefix="/api/v1")

@app.get("/health")
async def health():
    return {"status": "ok"}
