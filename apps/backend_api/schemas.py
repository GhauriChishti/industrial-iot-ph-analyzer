from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TelemetryBase(BaseModel):
    timestamp: datetime
    ph: float = Field(ge=0, le=14)
    temperature: float = Field(ge=-20, le=100)
    status: int = Field(ge=0, le=1)
    alarm: int = Field(ge=0, le=3)
    health: int = Field(ge=0, le=100)


class TelemetryCreate(TelemetryBase):
    pass


class TelemetryRead(TelemetryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
