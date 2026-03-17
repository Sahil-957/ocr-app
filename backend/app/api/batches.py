from datetime import datetime
from pathlib import Path
import shutil

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.batch import Batch
from app.models.extracted_row import ExtractedRow
from app.models.uploaded_file import UploadedFile
from app.models.user import User
from app.schemas.batch import BatchCreateRequest, BatchResponse, ExportResponse, RowResponse, RowUpdateRequest
from app.services.batch_processor import process_batch
from app.services.exporter import create_export


router = APIRouter(prefix="/batches", tags=["batches"])


@router.post("", response_model=BatchResponse)
def create_batch(
    payload: BatchCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Batch:
    batch = Batch(name=payload.name, created_by_id=current_user.id)
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


@router.get("/{batch_id}", response_model=BatchResponse)
def get_batch(batch_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Batch:
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")
    return batch


@router.post("/{batch_id}/files", response_model=BatchResponse)
def upload_files(
    batch_id: int,
    files: list[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Batch:
    batch = db.query(Batch).filter(Batch.id == batch_id, Batch.created_by_id == current_user.id).first()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")

    batch_dir = settings.upload_root / f"batch_{batch.id}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    for incoming in files:
        target_path = batch_dir / incoming.filename
        with target_path.open("wb") as destination:
            shutil.copyfileobj(incoming.file, destination)
        db.add(UploadedFile(batch_id=batch.id, original_name=incoming.filename, storage_path=str(target_path.resolve())))

    db.commit()
    batch.total_files = db.query(UploadedFile).filter(UploadedFile.batch_id == batch.id).count()
    db.commit()
    db.refresh(batch)
    return batch


@router.post("/{batch_id}/start", response_model=BatchResponse)
def start_batch(
    batch_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Batch:
    batch = db.query(Batch).filter(Batch.id == batch_id, Batch.created_by_id == current_user.id).first()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")
    batch.status = "queued"
    batch.started_at = datetime.utcnow()
    db.commit()
    background_tasks.add_task(_run_batch_in_new_session, batch.id)
    db.refresh(batch)
    return batch


def _run_batch_in_new_session(batch_id: int) -> None:
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        process_batch(db, batch_id)
    finally:
        db.close()


@router.get("/{batch_id}/rows", response_model=list[RowResponse])
def list_rows(batch_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[RowResponse]:
    rows = db.query(ExtractedRow).filter(ExtractedRow.batch_id == batch_id).all()
    return [
        RowResponse(
            id=row.id,
            status=row.status,
            confidence_summary=row.confidence_summary,
            data=row.data,
            reviewed_data=row.reviewed_data,
            validation_issues=row.validation_issues,
            source_file_name=row.source_file.original_name,
            last_edited_at=row.last_edited_at,
            audits=row.audits,
        )
        for row in rows
    ]


@router.patch("/rows/{row_id}", response_model=RowResponse)
def update_row(
    row_id: int,
    payload: RowUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RowResponse:
    row = db.query(ExtractedRow).filter(ExtractedRow.id == row_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")

    row.reviewed_data = payload.reviewed_data
    row.status = payload.status
    row.last_edited_by_id = current_user.id
    row.last_edited_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return RowResponse(
        id=row.id,
        status=row.status,
        confidence_summary=row.confidence_summary,
        data=row.data,
        reviewed_data=row.reviewed_data,
        validation_issues=row.validation_issues,
        source_file_name=row.source_file.original_name,
        last_edited_at=row.last_edited_at,
        audits=row.audits,
    )


@router.post("/{batch_id}/export", response_model=ExportResponse)
def export_batch(batch_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ExportResponse:
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")

    export = create_export(db, batch, current_user.id)
    return ExportResponse(id=export.id, status=export.status, download_url=f"/batches/exports/{export.id}/download")


@router.get("/exports/{export_id}/download")
def download_export(export_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> FileResponse:
    from app.models.export_job import ExportJob

    export = db.query(ExportJob).filter(ExportJob.id == export_id).first()
    if not export or not export.file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    return FileResponse(Path(export.file_path), filename=Path(export.file_path).name)
