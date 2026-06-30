import json
import httpx
from typing import Optional, Type
from pydantic import BaseModel
from new.config import settings


class LLMClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        provider: Optional[str] = None,
    ):
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.model = model or settings.llm_model
        self.api_key = api_key or settings.llm_api_key
        self.provider = provider or settings.llm_provider

    async def complete(
        self, prompt: str, schema: Optional[Type[BaseModel]] = None,
        timeout: Optional[float] = None,
    ) -> str:
        if self.provider == "ollama":
            return await self._ollama_complete(prompt, schema, timeout)
        return await self._openai_complete(prompt, schema, timeout)

    async def _ollama_complete(
        self, prompt: str, schema: Optional[Type[BaseModel]] = None,
        timeout: Optional[float] = None,
    ) -> str:
        url = f"{self.base_url}/api/generate"
        json_schema = None
        if schema:
            json_schema = schema.model_json_schema()
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "temperature": 0.3,
            "format": "json",
        }
        async with httpx.AsyncClient(timeout=timeout or 120.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        raw = data.get("response", "")
        return raw

    async def _openai_complete(
        self, prompt: str, schema: Optional[Type[BaseModel]] = None,
        timeout: Optional[float] = None,
    ) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        messages = [{"role": "user", "content": prompt}]
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
        }
        if schema:
            payload["response_format"] = {"type": "json_object"}
        async with httpx.AsyncClient(timeout=timeout or 120.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def is_available(self) -> bool:
        try:
            if self.provider == "ollama":
                url = f"{self.base_url}/api/tags"
            else:
                url = f"{self.base_url}/models"
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                return resp.status_code == 200
        except Exception:
            return False

    async def verify_completion(self) -> str:
        """Run a trivial completion to verify the model is actually responsive."""
        return await self._ollama_complete(
            "Respond with a single word: ok",
            timeout=15.0,
        )
