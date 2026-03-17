from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BatchCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class BatchResponse(BaseModel):
    id: int
    name: str
    status: str
    created_at: datetime
    total_files: int
    processed_files: int
    review_count: int
    failed_count: int
    export_status: str
    last_error: str | None

    model_config = {"from_attributes": True}


class FieldAuditResponse(BaseModel):
    field_name: str
    raw_text: str | None
    normalized_value: str | None
    confidence: float
    validation_issues: list[str]
    bbox: dict[str, Any] | None

    model_config = {"from_attributes": True}


class RowResponse(BaseModel):
    id: int
    status: str
    confidence_summary: float
    data: dict[str, Any]
    reviewed_data: dict[str, Any] | None
    validation_issues: list[str]
    source_file_name: str
    last_edited_at: datetime | None
    audits: list[FieldAuditResponse]


class RowUpdateRequest(BaseModel):
    reviewed_data: dict[str, Any]
    status: str = "approved"


class ExportResponse(BaseModel):
    id: int
    status: str
    download_url: str | None = None
