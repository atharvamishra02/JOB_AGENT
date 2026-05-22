import logging
import uuid
import asyncio
from .workflow_manager import wf_manager

logger = logging.getLogger("server.workflow")

def run_workflow_thread(resume_path: str, user_profile: dict):
    """Execute the full LangGraph workflow in a background thread."""
    user_id = user_profile.get("user_id")
    if not user_id:
        logger.error("No user_id provided for workflow")
        return

    state = wf_manager.get_state(user_id)
    
    state.is_running = True
    state.completed = False
    state.error = ""
    state.workflow_id = str(uuid.uuid4())[:12]
    state.resume_path = resume_path
    state.logs = []
    state.job_list = []
    state.current_job_index = 0

    try:
        state.current_step = "initializing"
        state.progress = 0
        wf_manager.add_log(user_id, "🚀 Workflow starting...", "info", "initializing")

        from graph.workflow import build_graph
        from graph.state import build_initial_state

        initial_state = build_initial_state(resume_path, user_profile or {})
        compiled = build_graph()

        wf_manager.add_log(user_id, "✅ LangGraph workflow compiled", "success", "initializing")

        # Run the full workflow
        for output in compiled.stream(initial_state):
            if not state.is_running:
                wf_manager.add_log(user_id, "🛑 Workflow halted by user request", "warning")
                break

            for node_name, state_update in output.items():
                state.current_step = node_name
                
                if "resume_data" in state_update:
                    state.resume_data = state_update["resume_data"]
                if "user_profile" in state_update:
                    state.user_profile = state_update["user_profile"]
                if "job_list" in state_update:
                    state.job_list = state_update["job_list"]
                if "current_job_index" in state_update:
                    state.current_job_index = state_update["current_job_index"]
                    
                for log_entry in state_update.get("logs", []):
                    wf_manager.add_log(user_id, log_entry, "info", node_name)

        state.progress = 100
        state.current_step = "completed"
        state.completed = True
        
        wf_manager.add_log(
            user_id,
            f"🎉 Workflow complete! Evaluated {len(state.job_list)} jobs.",
            "success",
            "completed",
        )

    except Exception as exc:
        logger.exception("Workflow failed")
        state.error = str(exc)
        state.current_step = "error"
        wf_manager.add_log(user_id, f"❌ Workflow error: {exc}", "error", "error")

    finally:
        state.is_running = False
