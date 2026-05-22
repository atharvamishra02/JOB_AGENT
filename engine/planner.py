import logging
import time
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class ExecutionPlanner:
    """
    Manages the high-level application trajectory.
    Handles step budgeting and platform-specific complexity scoring.
    """
    
    def __init__(self, max_steps: int = 60):
        self.max_steps = max_steps
        self.current_step = 0
        self.start_time = time.time()
        self.platform_scores = {
            "linkedin": 1.5,
            "naukri": 1.3,
            "workday": 2.5,
            "greenhouse": 1.0,
        }

    def get_adaptive_budget(self, url: str) -> int:
        """Calculates step budget based on the platform."""
        for platform, multiplier in self.platform_scores.items():
            if platform in url.lower():
                return int(self.max_steps * multiplier)
        return self.max_steps

    def should_continue(self, step_count: int, url: str) -> bool:
        """Determines if the agent should continue based on budget and time."""
        budget = self.get_adaptive_budget(url)
        if step_count >= budget:
            logger.warning(f"Planner: Step budget exceeded ({step_count}/{budget})")
            return False
            
        # Max 15 minutes per application
        if time.time() - self.start_time > 900:
            logger.warning("Planner: Time budget exceeded (10 minutes)")
            return False
            
        return True
