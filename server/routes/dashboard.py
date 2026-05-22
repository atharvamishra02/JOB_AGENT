from fastapi import APIRouter, Depends
from db.database import init_db, get_all_applications
from server.auth import get_current_user
from server.workflow_manager import wf_manager
from datetime import datetime, timedelta

router = APIRouter(prefix="/api", tags=["dashboard"])

@router.get("/dashboard")
async def get_dashboard_stats(current_user: dict = Depends(get_current_user)):
    """Aggregate dashboard statistics for the current user."""
    try:
        user_id = int(current_user["sub"])
        SessionFactory = init_db()
        with SessionFactory() as session:
            records = get_all_applications(session, user_id=user_id)

            total = len(records)
            applied = sum(1 for r in records if r.status in ("applied", "success"))
            skipped = sum(1 for r in records if r.status == "skipped")
            failed = sum(1 for r in records if r.status == "failed")
            pending = sum(1 for r in records if r.status == "pending")
            
            # Simple unique job_id count for duplicates
            job_ids = [r.job_id for r in records if r.job_id]
            duplicates = total - len(set(job_ids))
            
            # Match score distribution
            scores = [r.match_score for r in records if r.match_score is not None]
            avg_score = sum(scores) / len(scores) if scores else 0
            
            score_ranges = {"0-50": 0, "50-70": 0, "70-85": 0, "85-100": 0}
            for s in scores:
                if s < 50: score_ranges["0-50"] += 1
                elif s < 70: score_ranges["50-70"] += 1
                elif s < 85: score_ranges["70-85"] += 1
                else: score_ranges["85-100"] += 1

            # Source stats
            sources = {"LinkedIn": 0, "Naukri": 0, "Other": 0}
            for r in records:
                url = (r.url or "").lower()
                if "linkedin.com" in url: sources["LinkedIn"] += 1
                elif "naukri.com" in url: sources["Naukri"] += 1
                else: sources["Other"] += 1

            # Recent activity
            recent = [
                {"id": r.id, "title": r.title, "company": r.company, "status": r.status, "time": r.created_at.isoformat() if r.created_at else None}
                for r in records[:5]
            ]

            return {
                "total_jobs": total,
                "applied": applied,
                "skipped": skipped,
                "failed": failed,
                "pending": pending,
                "duplicates": duplicates,
                "success_rate": round((applied / total * 100) if total else 0, 1),
                "avg_match_score": round(avg_score, 1),
                "sources": sources,
                "score_distribution": score_ranges,
                "recent_activity": recent,
                "workflow_status": wf_manager.get_status(user_id),
            }
    except Exception:
        return {
            "total_jobs": 0, "applied": 0, "skipped": 0, "failed": 0,
            "pending": 0, "duplicates": 0, "success_rate": 0,
            "avg_match_score": 0, "sources": {}, "score_distribution": {},
            "recent_activity": [], "workflow_status": wf_manager.get_status(user_id),
        }
