from typing import Callable, Awaitable, Optional
from new.llm_client import LLMClient
from new.config import settings

EventCallback = Callable[[str, str, str], Awaitable[None]]


class BaseAgent:
    def __init__(
        self,
        name: str,
        llm_client: Optional[LLMClient] = None,
        on_event: Optional[EventCallback] = None,
    ):
        self.name = name
        self.llm_client = llm_client or LLMClient()
        self.on_event = on_event

    async def emit(self, status: str, message: str):
        if self.on_event:
            await self.on_event(self.name, status, message)

    async def run(self, context: dict) -> dict:
        raise NotImplementedError
