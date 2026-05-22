import json
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from db.database import init_db, get_all_applications
from datetime import datetime, timezone
from server.auth import get_current_user
from server.workflow_manager import wf_manager

router = APIRouter(prefix="/api", tags=["data"])
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

@router.post("/upload-resume")
async def upload_resume(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    """Upload a PDF resume file."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted")

    user_id = current_user["sub"]
    upload_dir = PROJECT_ROOT / "uploads" / str(user_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    dest = upload_dir / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    return {
        "message": "Resume uploaded successfully",
        "filename": file.filename,
        "path": str(dest),
    }

@router.get("/jobs")
async def get_jobs(current_user: dict = Depends(get_current_user)):
    """Get discovered jobs for the current user."""
    user_id = int(current_user["sub"])
    state = wf_manager.get_state(user_id)
    jobs = state.job_list or []
    return {
        "jobs": jobs,
        "total": len(jobs),
        "current_index": state.current_job_index,
    }

@router.get("/resume-data")
async def get_resume_data(current_user: dict = Depends(get_current_user)):
    """Get parsed resume data for the current user."""
    user_id = int(current_user["sub"])
    state = wf_manager.get_state(user_id)
    return {
        "resume_data": state.resume_data,
        "user_profile": state.user_profile,
    }

@router.get("/applications")
async def get_applications(current_user: dict = Depends(get_current_user)):
    """Get all application records for the current user from the database."""
    try:
        user_id = int(current_user["sub"])
        SessionFactory = init_db()
        with SessionFactory() as session:
            records = get_all_applications(session, user_id=user_id)
            return {
                "applications": [
                    {
                        "id": r.id,
                        "job_id": r.job_id,
                        "company": r.company,
                        "title": r.title,
                        "url": r.url,
                        "match_score": r.match_score,
                        "decision": r.decision,
                        "status": r.status,
                        "error": r.error,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                    }
                    for r in records
                ],
                "total": len(records),
            }
    except Exception as exc:
        raise HTTPException(500, f"Database error: {exc}")

@router.get("/learned-data")
async def get_learned_data(current_user: dict = Depends(get_current_user)):
    """Get learned placeholder data for the current user."""
    user_id = current_user["sub"]
    path = PROJECT_ROOT / "uploads" / str(user_id) / "learned_placeholders.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return {"data": json.load(f)}
    return {"data": {}}

@router.get("/resumes")
async def list_resumes(current_user: dict = Depends(get_current_user)):
    """List uploaded resumes for the current user."""
    user_id = current_user["sub"]
    upload_dir = PROJECT_ROOT / "uploads" / str(user_id)
    if not upload_dir.exists():
        return {"resumes": []}
    pdfs = list(upload_dir.glob("*.pdf"))
    return {
        "resumes": [
            {
                "name": p.name,
                "path": str(p),
                "size": p.stat().st_size,
                "created_at": datetime.fromtimestamp(p.stat().st_ctime, timezone.utc).isoformat()
            }
            for p in pdfs
        ]
    }

@router.get("/logs")
async def get_logs(current_user: dict = Depends(get_current_user)):
    """Get the latest logs for the current user."""
    user_id = int(current_user["sub"])
    state = wf_manager.get_state(user_id)
    return {"logs": state.logs[-100:]}
