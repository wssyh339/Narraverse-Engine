from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.api.v1.endpoints import studio
from app.core.config import get_settings
from app.core.responses import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.db import models
from app.db.runtime_migrations import apply_sqlite_runtime_migrations
from app.db.session import Base, engine

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    apply_sqlite_runtime_migrations(engine)
    yield


app = FastAPI(title="叙界推演引擎 / Narraverse Engine API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)
app.include_router(api_router, prefix="/api/v1")
app.include_router(api_router, prefix="/api")
app.add_api_websocket_route("/ws/progress", studio.progress_websocket)
app.add_api_websocket_route("/ws/jobs/{job_id}", studio.job_websocket)
