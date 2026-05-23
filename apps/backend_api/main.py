from __future__ import annotations

import logging
from collections.abc import Sequence

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import TelemetryRecord
from .schemas import TelemetryCreate, TelemetryRead

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("backend_api")

app = FastAPI(title="Industrial IoT pH Analyzer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized and tables ensured.")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/telemetry", response_model=TelemetryRead, status_code=201)
def ingest_telemetry(payload: TelemetryCreate, db: Session = Depends(get_db)) -> TelemetryRecord:
    record = TelemetryRecord(**payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    logger.info(
        "Telemetry ingested: id=%s timestamp=%s ph=%s temperature=%s status=%s alarm=%s health=%s",
        record.id,
        record.timestamp,
        record.ph,
        record.temperature,
        record.status,
        record.alarm,
        record.health,
    )
    return record


@app.get("/api/v1/telemetry/latest", response_model=TelemetryRead)
def latest_telemetry(db: Session = Depends(get_db)) -> TelemetryRecord:
    record = db.query(TelemetryRecord).order_by(desc(TelemetryRecord.timestamp)).first()
    if record is None:
        raise HTTPException(status_code=404, detail="No telemetry records found")
    return record


@app.get("/api/v1/telemetry/history", response_model=list[TelemetryRead])
def telemetry_history(
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> Sequence[TelemetryRecord]:
    records = (
        db.query(TelemetryRecord)
        .order_by(desc(TelemetryRecord.timestamp))
        .limit(limit)
        .all()
    )
    return records
