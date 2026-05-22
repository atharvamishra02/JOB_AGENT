from fastapi import APIRouter, Depends, HTTPException
from db.database import init_db, get_user_by_id, update_user_settings
from server.auth import get_current_user

router = APIRouter(prefix="/api/user", tags=["user"])

@router.get("/settings")
async def get_settings(current_user: dict = Depends(get_current_user)):
    """Get the current user's AI settings."""
    SessionFactory = init_db()
    with SessionFactory() as session:
        user = get_user_by_id(session, int(current_user["sub"]))
        if not user:
            raise HTTPException(404, "User not found")
        return {
            "openai_api_key": user.openai_api_key,
            "gemini_api_key": user.gemini_api_key,
            "preferred_model": user.preferred_model,
            "name": user.name,
            "email": user.email,
        }

@router.post("/settings")
async def update_settings(body: dict, current_user: dict = Depends(get_current_user)):
    """Update the current user's AI settings."""
    SessionFactory = init_db()
    with SessionFactory() as session:
        user = update_user_settings(session, int(current_user["sub"]), body)
        if not user:
            raise HTTPException(404, "User not found")
        return {"message": "Settings updated successfully"}
