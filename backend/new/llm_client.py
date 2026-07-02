import json
import logging
import httpx

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, base_url: str, model: str, api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def complete(self, prompt: str, expect_json: bool = False) -> str:
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }
        if expect_json:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    url, headers=self._headers(), json=payload
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                logger.debug(f"[LLMClient] raw response: {content[:300]}")
                return content
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"[LLMClient] HTTP {e.response.status_code}: {e.response.text[:300]}"
                )
                raise
            except Exception as e:
                logger.error(f"[LLMClient] request failed: {e}")
                raise

    async def health_check(self) -> bool:
        try:
            url = f"{self.base_url}/v1/models"
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url, headers=self._headers())
                r.raise_for_status()
                logger.info(f"[LLMClient] health check passed at {self.base_url}")
                return True
        except Exception as e:
            logger.error(f"[LLMClient] health check failed: {e}")
            return False

    @staticmethod
    def parse_json(raw: str) -> dict:
        """
        Robustly extract a JSON object from LLM output.

        Handles markdown fences (```json...``` and ```...```), preamble text,
        and trailing content. Always raises ValueError (never a bare
        json.JSONDecodeError) so callers can catch a single exception type.
        """
        if raw is None:
            raise ValueError("No JSON object found in LLM response: <empty>")

        text = raw.strip()

        # Strip markdown fences by splitting on ``` rather than using a
        # non-greedy regex (which can fail on nested braces).
        if "```" in text:
            parts = text.split("```")
            # parts alternates: [preamble, fence_lang_or_body, ..., body_or_text, ...]
            # We look for the first fenced block that contains a '{'.
            for i in range(1, len(parts), 2):
                block = parts[i]
                # Strip a leading language tag like "json" or "JSON".
                stripped = block.lstrip()
                if stripped[:4].lower() == "json":
                    stripped = stripped[4:].lstrip()
                if "{" in stripped:
                    text = stripped
                    break

        # Find the outermost '{' and '}' in the cleaned text and slice.
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError(
                f"No JSON object found in LLM response: {raw[:300]}"
            )

        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Failed to decode JSON from LLM response: {raw[:300]} "
                f"(error: {e})"
            ) from e
