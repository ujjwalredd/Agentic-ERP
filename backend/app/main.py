from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.base import init_db
from app.routers import (
    entities,
    inbox,
    ledger,
    observability,
    reports,
    simulate,
    webhooks,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Flow — Agentic Accounting ERP", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(inbox.router)
app.include_router(ledger.router)
app.include_router(reports.router)
app.include_router(entities.router)
app.include_router(simulate.router)
app.include_router(webhooks.router)
app.include_router(observability.router)


@app.get("/health")
def health():
    return {"status": "ok"}
