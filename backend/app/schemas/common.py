"""Shared API shapes."""

from pydantic import BaseModel, Field


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


class StatusMessage(BaseModel):
    status: str
    detail: str | None = None


class FxRateOut(BaseModel):
    currency: str
    usd_per_unit: float


class FxRateUpdate(BaseModel):
    usd_per_unit: float = Field(gt=0, lt=1000)
