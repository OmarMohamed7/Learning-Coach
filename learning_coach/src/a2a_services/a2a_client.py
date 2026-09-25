import os

import httpx
import json
import uuid

from logger import get_logger

QUIZ_SERVICE_URL  = os.getenv("QUIZ_SERVICE_URL",  "http://localhost:9001")
STUDY_BUDDY_URL   = os.getenv("STUDY_BUDDY_URL",   "http://localhost:9002")
DEFAULT_TIMEOUT   = 120.0

logger = get_logger(__name__)

def discover_Agent(base_url: str) -> dict:
    """ Fetch an Agent Card to discover capabilities. Return {} if unreachable. """
    card_url = f"{base_url.rstrip('/')}/.well-known/agent-card.json"
    try:
        response = httpx.get(card_url, timeout=5.0)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[A2A Client] Cannot reach {card_url}: {e}")
        return {}
    
def send_task(
    base_url: str,
    message_text: str,
    task_id: str | None = None,
    timeout: float = DEFAULT_TIMEOUT
) -> dict:
    """
    Submit a task to an A2A agent via JSON-RPC 2.0.
    
    """
    
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tasks/send",
        "params":{
            "id": task_id or str(uuid.uuid4()),
            "message": {
                "role":  "user",
                "parts": [{"type": "text", "text": message_text}],
            },
        }
    }
    
    url = f"{base_url.rstrip('/')}/tasks/send"
    
    try:
        response = httpx.post(url=url, json=payload, timeout= timeout)
        response.raise_for_status()
        data = response.json()
        
        
    except Exception as e:
        raise e

    
    return {}  