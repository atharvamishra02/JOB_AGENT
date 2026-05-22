import hashlib
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

class AgentMemoryManager:
    """
    Manages the agent's history and prevents navigation loops or action repetition.
    Implements semantic fingerprinting of page states.
    """
    
    def __init__(self, max_history: int = 50):
        self.history: List[Dict[str, Any]] = []
        self.state_hashes: Dict[str, int] = {}
        self.max_history = max_history

    def get_state_fingerprint(self, dom: str) -> str:
        """
        Creates a semantic fingerprint of the DOM.
        Focuses on interactive elements to avoid noise from dynamic non-interactive parts.
        """
        # Extract only data-agent-idx and surrounding text context
        # This makes the hash resilient to small dynamic changes like ads or tickers
        fingerprint_basis = []
        import re
        matches = re.findall(r'data-agent-idx="([^"]+)"[^>]*>([^<]*)', dom)
        for idx, text in matches:
            fingerprint_basis.append(f"{idx}:{text.strip()}")
            
        basis_str = "|".join(fingerprint_basis)
        return hashlib.md5(basis_str.encode()).hexdigest()

    def update(self, dom: str, action: Dict[str, Any], result: str):
        """Records a step in the agent's trajectory."""
        state_hash = self.get_state_fingerprint(dom)
        
        step = {
            "state_hash": state_hash,
            "action": action,
            "result": result
        }
        
        self.history.append(step)
        if len(self.history) > self.max_history:
            self.history.pop(0)
            
        self.state_hashes[state_hash] = self.state_hashes.get(state_hash, 0) + 1

    def is_stuck(self, current_dom: str) -> bool:
        """Detects if the agent is stuck in a loop or same-state cycle."""
        current_hash = self.get_state_fingerprint(current_dom)
        
        # If we've seen this exact interactive state more than 3 times, we're likely stuck
        if self.state_hashes.get(current_hash, 0) >= 3:
            return True
            
        # Check for navigation ping-pong (A -> B -> A)
        if len(self.history) >= 4:
            h1 = self.history[-1]["state_hash"]
            h2 = self.history[-2]["state_hash"]
            h3 = self.history[-3]["state_hash"]
            h4 = self.history[-4]["state_hash"]
            if h1 == h3 and h2 == h4:
                return True
                
        return False

    def get_recent_actions(self, n: int = 5) -> List[Dict[str, Any]]:
        """Returns the last N actions taken."""
        return [step["action"] for step in self.history[-n:]]

    def clear(self):
        self.history = []
        self.state_hashes = {}
