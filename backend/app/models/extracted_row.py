from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ExtractedRow(Base):
    __tablename__ = "extracted_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), index=True)
    source_file_id: Mapped[int] = mapped_column(ForeignKey("uploaded_files.id"), unique=True)
    status: Mapped[str] = mapped_column(String(50), default="processed")
    confidence_summary: Mapped[float] = mapped_column(Float, default=0.0)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    reviewed_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation_issues: Mapped[list] = mapped_column(JSON, default=list)
    last_edited_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    last_edited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    batch = relationship("Batch", back_populates="rows")
    source_file = relationship("UploadedFile", back_populates="row")
    last_edited_by = relationship("User")
    audits = relationship("FieldAudit", back_populates="row", cascade="all, delete-orphan")
