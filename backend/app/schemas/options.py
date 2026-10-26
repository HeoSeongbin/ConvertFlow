from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class ConversionOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    page_size: Literal["original", "A4", "Letter"] = Field("original", alias="pageSize")
    orientation: Literal["auto", "portrait", "landscape"] = "auto"
    margin_mm: float = Field(0, ge=0, le=50, allow_inf_nan=False, alias="marginMm")
    fit: Literal["contain", "cover"] = "contain"
    quality: int = Field(90, ge=1, le=100, strict=True)
