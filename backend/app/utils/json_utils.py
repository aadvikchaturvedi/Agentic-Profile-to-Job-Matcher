import json
import re
from typing import Any, Dict, Optional


def extract_json_from_response(text: str) -> Optional[Dict[str, Any]]:
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    json_str = match.group(1) if match else None
    if not json_str:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        json_str = match.group(0) if match else None
    if not json_str:
        return None
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None
