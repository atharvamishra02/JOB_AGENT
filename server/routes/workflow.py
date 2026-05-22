import threading
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from server.workflow_manager import wf_manager
from server.workflow_runner import run_workflow_thread
from server.auth import get_current_user
from db.database import init_db, get_user_by_id

router = APIRouter(prefix="/api", tags=["workflow"])
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

@router.get("/workflow-status")
async def get_workflow_status(current_user: dict = Depends(get_current_user)):
    """Return the current status of the workflow."""
    user_id = int(current_user["sub"])
    return wf_manager.get_status(user_id)

@router.post("/start-workflow")
async def start_workflow(body: dict = {}, current_user: dict = Depends(get_current_user)):
    """Start the autonomous job application workflow for the current user."""
    user_id = int(current_user["sub"])
    state = wf_manager.get_state(user_id)
    if state.is_running:
        raise HTTPException(409, "Workflow is already running")

    resume_path = body.get("resume_path", "")
    user_profile = body.get("user_profile", {})
    
    # Inject user_id into profile
    user_id = int(current_user["sub"])
    user_profile["user_id"] = user_id
    
    # Fetch user-owned API keys and preferred model from DB
    SessionFactory = init_db()
    with SessionFactory() as session:
        user = get_user_by_id(session, user_id)
        if user:
            user_profile["api_keys"] = {
                "openai": user.openai_api_key or "",
                "gemini": user.gemini_api_key or "",
            }
            user_profile["preferred_model"] = user.preferred_model or "gpt-4o"

    if not resume_path:
        # Auto-detect resume in user's folder
        user_upload_dir = PROJECT_ROOT / "uploads" / str(user_id)
        pdfs = list(user_upload_dir.glob("*.pdf")) if user_upload_dir.exists() else []
        
        # Fallback to project root
        if not pdfs:
            pdfs = list(PROJECT_ROOT.glob("*.pdf"))
            
        resume_keywords = ["resume", "cv", "curriculum"]
        for pdf in pdfs:
            if any(kw in pdf.stem.lower() for kw in resume_keywords):
                resume_path = str(pdf)
                break
        if not resume_path and pdfs:
            resume_path = str(pdfs[0])

    if not resume_path or not Path(resume_path).exists():
        raise HTTPException(400, "Resume file not found. Please upload one first.")

    # Run in a background thread to avoid blocking the main event loop
    thread = threading.Thread(
        target=run_workflow_thread,
        args=(resume_path, user_profile),
        daemon=True,
    )
    thread.start()

    return {"message": "Workflow started", "resume_path": resume_path}

@router.post("/stop-workflow")
async def stop_workflow(current_user: dict = Depends(get_current_user)):
    """Request the current workflow to stop."""
    user_id = int(current_user["sub"])
    state = wf_manager.get_state(user_id)
    state.is_running = False
    wf_manager.add_log(user_id, "🛑 Stop requested by user", "warning")
    return {"message": "Stop requested"}
