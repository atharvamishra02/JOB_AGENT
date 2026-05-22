import os
import json
import logging

logger = logging.getLogger(__name__)

def get_memory_path(user_id: int | str) -> str:
    """Get the path to the user's learned memory file."""
    # Place it in the user's upload directory for isolation
    from pathlib import Path
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    user_dir = PROJECT_ROOT / "uploads" / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    return str(user_dir / "learned_placeholders.json")

def load_learned_data(user_id: int | str) -> dict:
    """Load the user's learned placeholders."""
    path = get_memory_path(user_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading memory: {e}")
    return {}

def save_learned_data(user_id: int | str, data: dict):
    """Save the user's learned placeholders."""
    path = get_memory_path(user_id)
    try:
        existing = load_learned_data(user_id)
        existing.update(data)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving memory: {e}")
