from sqlalchemy import Float, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class FieldAudit(Base):
    __tablename__ = "field_audits"

    id: Mapped[int] = mapped_column(primary_key=True)
    row_id: Mapped[int] = mapped_column(ForeignKey("extracted_rows.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(150), index=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    validation_issues: Mapped[list] = mapped_column(JSON, default=list)
    bbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    row = relationship("ExtractedRow", back_populates="audits")
