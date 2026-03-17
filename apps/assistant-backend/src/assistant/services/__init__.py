from functools import lru_cache

from assistant.services.conversation_service import ConversationService
from assistant.services.llm_service import LLMService
from assistant.services.memory_storage import MemoryStorage
from assistant.settings import settings


@lru_cache(maxsize=1)
def get_llm_service() -> LLMService:
    """Return a lazily initialized singleton instance of LLMService."""
    return LLMService(
        base_url=settings.llm_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
    )


@lru_cache(maxsize=1)
def get_memory_storage() -> MemoryStorage:
    """Return a lazily initialized singleton instance of MemoryStorage."""
    return MemoryStorage(
        chroma_host=settings.chroma_host,
        chroma_port=settings.chroma_port,
        collection_name=settings.chroma_collection_name,
    )


@lru_cache(maxsize=1)
def get_conversation_service() -> ConversationService:
    """Return a lazily initialized singleton instance of ConversationService."""
    return ConversationService(
        llm_service=get_llm_service(), memory_storage=get_memory_storage()
    )
