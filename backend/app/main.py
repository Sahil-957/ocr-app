from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.batches import router as batch_router
from app.core.config import settings
from app.db.session import Base, SessionLocal, engine
from app.models import User  # noqa: F401
from app.services.security import hash_password


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router)
    app.include_router(batch_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def bootstrap() -> None:
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    settings.upload_root.mkdir(parents=True, exist_ok=True)
    settings.export_root.mkdir(parents=True, exist_ok=True)
    settings.ocr_model_root.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == settings.default_admin_username).first()
        if not admin:
            db.add(
                User(
                    username=settings.default_admin_username,
                    name="System Admin",
                    password_hash=hash_password(settings.default_admin_password),
                    is_active=True,
                )
            )
            db.commit()
    finally:
        db.close()


bootstrap()
app = create_app()
