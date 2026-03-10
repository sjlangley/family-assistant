from functools import lru_cache

from assistant.services.llm_service import LLMService
from assistant.settings import settings


@lru_cache(maxsize=1)
def get_llm_service() -> LLMService:
    """Return a lazily initialized singleton instance of LLMService."""
    return LLMService(
        base_url=settings.llm_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
    )
