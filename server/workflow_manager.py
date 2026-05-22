import asyncio
import logging
from typing import List, Dict, Any
from fastapi import WebSocket

logger = logging.getLogger("server.workflow_manager")

class UserWorkflowState:
    """Holds the live state for a single user's workflow."""
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.is_running = False
        self.completed = False
        self.error = ""
        self.current_step = "idle"
        self.progress = 0
        self.logs = []
        self.resume_path = ""
        self.resume_data = {}
        self.user_profile = {}
        self.job_list = []
        self.current_job_index = 0
        self.workflow_id = ""

    def add_log(self, message: str, level: str = "info", step: str = None):
        import time
        log_entry = {
            "message": message,
            "level": level,
            "step": step or self.current_step,
            "timestamp": time.time()
        }
        self.logs.append(log_entry)
        if len(self.logs) > 500:
            self.logs.pop(0)

class WorkflowManager:
    """Manages concurrent workflows for multiple users."""
    def __init__(self):
        self.user_states: Dict[int, UserWorkflowState] = {}
        self.connections: List[WebSocket] = []
        self.event_loop = None

    def get_state(self, user_id: int) -> UserWorkflowState:
        if user_id not in self.user_states:
            self.user_states[user_id] = UserWorkflowState(user_id)
        return self.user_states[user_id]

    async def broadcast_to_user(self, user_id: int, message: dict):
        """Send a message only to the sockets belonging to a specific user."""
        for ws in self.connections:
            if getattr(ws, "user_id", None) == user_id:
                try:
                    await ws.send_json(message)
                except Exception:
                    pass

    def add_log(self, user_id: int, message: str, level: str = "info", step: str = None):
        state = self.get_state(user_id)
        state.add_log(message, level, step)
        
        if self.event_loop and self.event_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self.broadcast_to_user(user_id, {
                    "type": "log",
                    "data": state.logs[-1],
                    "status": self.get_status(user_id)
                }),
                self.event_loop
            )

    def get_status(self, user_id: int) -> dict:
        state = self.get_state(user_id)
        return {
            "is_running": state.is_running,
            "current_step": state.current_step,
            "progress": state.progress,
            "completed": state.completed,
            "error": state.error,
            "workflow_id": state.workflow_id,
            "job_count": len(state.job_list),
            "current_job_index": state.current_job_index,
        }

# Global instance
wf_manager = WorkflowManager()
