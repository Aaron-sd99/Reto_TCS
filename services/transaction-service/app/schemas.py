from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class TransferStatus(StrEnum):
    RECEIVED = "RECEIVED"
    PENDING_CORE = "PENDING_CORE"
    SETTLED = "SETTLED"
    REJECTED = "REJECTED"
    PENDING_RECONCILIATION = "PENDING_RECONCILIATION"


class TransferRequest(BaseModel):
    source_account: str = Field(min_length=3, max_length=32)
    destination_account: str = Field(min_length=3, max_length=32)
    amount: Decimal = Field(gt=0, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)
    customer_id: str = Field(min_length=3, max_length=32)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("destination_account")
    @classmethod
    def different_accounts(cls, value: str, info):
        if info.data.get("source_account") == value:
            raise ValueError("source_account and destination_account must be different")
        return value


class TransferResponse(BaseModel):
    id: UUID
    status: TransferStatus
    source_account: str
    destination_account: str
    amount: Decimal
    currency: str
    customer_id: str
    core_reference: str | None = None
    rejection_reason: str | None = None
    correlation_id: str
    created_at: str
    updated_at: str


class HealthResponse(BaseModel):
    status: str
