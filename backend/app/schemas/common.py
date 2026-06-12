from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Direction = Literal["YES", "NO"]
SignalDirection = Literal["YES", "NO", "NEUTRAL"]
AccountLabelValue = Literal["NEW_ACCOUNT", "HIGH_WIN_RATE", "ABNORMAL_POSITION", "OTHER"]
TicketStatus = Literal["PENDING_USER_CONFIRMATION", "CONFIRMED", "SUBMITTED", "REJECTED",
                       "FAILED", "CANCELLED", "EXPIRED"]
PaperTradeStatus = Literal["OPEN", "CLOSED", "CANCELLED"]
GeoMode = Literal["OK", "CLOSE_ONLY", "BLOCKED"]

ADDRESS_PATTERN = r"^0x[0-9a-fA-F]{40}$"


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    error: ErrorBody
