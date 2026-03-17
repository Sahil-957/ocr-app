# Company-Facing Costing OCR Platform

This workspace now contains a production-style starter implementation for a company-facing OCR platform that:

- authenticates internal users
- accepts bulk folder uploads of same-layout costing screenshots
- extracts structured data with a template-based OCR pipeline
- routes low-confidence rows into a review workflow
- exports downloadable Excel workbooks with summary, audit, and error sheets

## Project structure

- `backend/` FastAPI API, persistence, OCR pipeline, export logic, and tests
- `frontend/` React + Vite company-facing UI
- `extractor.py` original prototype kept as a legacy reference

## Local development

## Python compatibility

This backend currently needs `Python 3.11` or `Python 3.12`.

`Python 3.13` does not work with the current OCR dependency stack because:

- `paddleocr==2.9.1` requires `numpy<2.0`
- on your Windows/Python 3.13 environment, pip is resolving newer `numpy` constraints and cannot build a compatible set

If you want to test this project locally, install Python `3.11.x` first and create a virtual environment with that interpreter.

### Backend

1. Create a virtual environment.
2. Install dependencies:

```bash
pip install -r backend/requirements.txt
```

3. Start the API from the `backend` folder:

```bash
python -m uvicorn app.main:app --reload
```

Default login:

- username: `admin`
- password: `admin123`

The backend uses SQLite in `backend/storage/app.db` by default for local development. The architecture is ready to move to PostgreSQL/Redis-backed workers later through configuration and service replacement.

### Frontend

1. Install dependencies:

```bash
cd frontend
npm install
```

2. Start the app:

```bash
npm run dev
```

The frontend expects the backend at `http://127.0.0.1:8000`.

## Current implementation notes

- The OCR engine is template-driven for the fixed `DOMESTIC COSTING` layout.
- A JSON template file defines the crop regions for fields and table cells.
- Batch processing currently uses FastAPI background tasks for local/dev simplicity.
- Rows with validation issues or confidence below the threshold are marked `needs_review`.
- Excel export includes `Summary`, `Audit`, and `Errors` sheets.

## Recommended production hardening next

- Move from SQLite/background tasks to PostgreSQL + Redis/Celery or RQ.
- Add user management screens and password reset flow.
- Add persistent object storage such as S3 or Azure Blob.
- Expand the labeled golden dataset from your sample images.
- Tune the template coordinates and validation rules against real company data.
- Add image preview and per-field confidence heatmaps in the review UI.

## Quick demo deployment

For a company demo, the fastest reliable path is:

1. Host the backend on a single VM or Windows/Linux server.
2. Host the frontend separately as a static site.
3. Point the frontend to the backend URL with `VITE_API_BASE`.

### Backend demo deployment

- Install Python `3.11`
- Copy the `backend/` folder to the server
- Create `.env` inside `backend/` with at least:

```env
SECRET_KEY=replace-this
DATABASE_URL=sqlite:///./storage/app.db
CORS_ORIGINS=["https://your-frontend-domain.com"]
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=admin123
```

- Install dependencies:

```bash
pip install -r requirements.txt
```

- Start the API from `backend/`:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Frontend demo deployment

- Copy `frontend/.env.example` to `frontend/.env`
- Set:

```env
VITE_API_BASE=https://your-backend-domain.com
```

- Build:

```bash
npm install
npm run build
```

- Deploy the generated `frontend/dist/` on any static host

Examples:
- Netlify
- Vercel
- an Nginx site on the same server

### Important note

This current version is good for a demo, but it is not yet ideal for long-term production hosting because it still uses:

- SQLite
- local file storage
- in-process background tasks

For a company pilot, that is okay. For real production, move to PostgreSQL, Redis workers, and persistent object storage.
