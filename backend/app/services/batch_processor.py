from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.batch import Batch
from app.models.extracted_row import ExtractedRow
from app.models.field_audit import FieldAudit
from app.models.uploaded_file import UploadedFile
from app.services.ocr_engine import DomesticCostingExtractor


_extractor: DomesticCostingExtractor | None = None


def get_extractor() -> DomesticCostingExtractor:
    global _extractor
    if _extractor is None:
        _extractor = DomesticCostingExtractor()
    return _extractor


def process_batch(db: Session, batch_id: int) -> None:
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        return

    batch.status = "processing"
    batch.started_at = datetime.utcnow()
    db.commit()

    files = db.query(UploadedFile).filter(UploadedFile.batch_id == batch.id).all()
    for uploaded_file in files:
        try:
            _process_single_file(db, batch, uploaded_file)
        except Exception as exc:  # pragma: no cover
            uploaded_file.status = "failed"
            uploaded_file.error_message = str(exc)
            batch.failed_count += 1
            batch.last_error = str(exc)
            db.commit()

    batch.review_count = db.query(ExtractedRow).filter(
        ExtractedRow.batch_id == batch.id,
        ExtractedRow.status == "needs_review",
    ).count()
    batch.processed_files = db.query(UploadedFile).filter(
        UploadedFile.batch_id == batch.id,
        UploadedFile.status.in_(["processed", "needs_review", "failed"]),
    ).count()
    batch.status = "completed"
    batch.completed_at = datetime.utcnow()
    db.commit()


def _process_single_file(db: Session, batch: Batch, uploaded_file: UploadedFile) -> None:
    existing = db.query(ExtractedRow).filter(ExtractedRow.source_file_id == uploaded_file.id).first()
    if existing:
        return

    image_path = Path(uploaded_file.storage_path)
    extractor = get_extractor()
    data, field_results, confidence, issues = extractor.extract(image_path)
    row_status = "processed" if confidence >= settings.confidence_threshold and not issues else "needs_review"

    row = ExtractedRow(
        batch_id=batch.id,
        source_file_id=uploaded_file.id,
        status=row_status,
        confidence_summary=confidence,
        data=data,
        validation_issues=issues,
    )
    db.add(row)
    db.flush()

    for result in field_results:
        db.add(
            FieldAudit(
                row_id=row.id,
                field_name=result.field_name,
                raw_text=result.raw_text,
                normalized_value="" if result.value is None else str(result.value),
                confidence=result.confidence,
                validation_issues=result.issues,
                bbox=result.bbox,
            )
        )

    uploaded_file.status = row_status
    db.commit()
