import json
from typing import Dict, Any, Optional, BinaryIO
from pathlib import Path

import requests


class APIClientError(Exception):
    pass


class APIClient:
    def __init__(self, base_url: str = "http://localhost:8000", timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> Dict[str, Any]:
        resp = requests.get(f"{self.base_url}/health", timeout=10)
        resp.raise_for_status()
        return resp.json()

    def match(self, resume_bytes: bytes, filename: str, jd_text: str) -> Dict[str, Any]:
        resp = requests.post(
            f"{self.base_url}/api/match",
            files={"resume": (filename, resume_bytes)},
            data={"job_description": jd_text},
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise APIClientError(f"Match failed ({resp.status_code}): {resp.text[:300]}")
        return resp.json()

    def match_jobs_stream(
        self, resume_bytes: bytes, filename: str, search_query: str, location: str = ""
    ) -> Dict[str, Any]:
        with requests.post(
            f"{self.base_url}/api/match-jobs",
            files={"resume": (filename, resume_bytes)},
            data={"search_query": search_query, "location": location},
            stream=True,
            timeout=self.timeout,
        ) as resp:
            if resp.status_code != 200:
                raise APIClientError(f"Match-jobs failed ({resp.status_code}): {resp.text[:300]}")
            event_type = None
            for raw in resp.iter_lines(decode_unicode=True):
                line = raw.strip()
                if not line:
                    continue
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                    continue
                if line.startswith("data:"):
                    payload = json.loads(line[5:].strip())
                    if event_type == "complete":
                        return payload
                    event_type = None
            raise APIClientError("Stream ended without complete event")
