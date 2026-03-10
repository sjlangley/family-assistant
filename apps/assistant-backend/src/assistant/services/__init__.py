from assistant.services.llm_service import LLMService
from assistant.settings import settings

llm_service = LLMService(
    base_url=settings.llm_base_url,
    timeout_seconds=settings.llm_timeout_seconds,
)
