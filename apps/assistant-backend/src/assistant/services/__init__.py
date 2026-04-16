from functools import lru_cache

from assistant.services.assistant_annotations import (
    AssistantAnnotationService,
)
from assistant.services.context_assembly import ContextAssemblyService
from assistant.services.conversation_service import ConversationService
from assistant.services.llm_service import LLMService
from assistant.services.memory_storage import MemoryStorage
from assistant.services.tool_service import ToolService
from assistant.services.tools.current_time import CurrentTimeTool
from assistant.services.tools.factory import ToolFactory
from assistant.services.tools.web_fetch import WebFetchTool
from assistant.services.tools.web_search import WebSearchTool
from assistant.settings import settings


@lru_cache(maxsize=1)
def get_tool_service() -> ToolService:
    """Return a lazily initialized singleton instance of ToolService."""
    # Register tools here. Currently, only CurrentTimeTool is wired in.
    factory = ToolFactory(
        tools=[CurrentTimeTool(), WebSearchTool(), WebFetchTool()]
    )
    return ToolService(factory=factory)


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
def get_context_assembly_service() -> ContextAssemblyService:
    """Return a lazily initialized singleton instance of ContextAssemblyService."""
    return ContextAssemblyService()


@lru_cache(maxsize=1)
def get_conversation_service() -> ConversationService:
    """Return a lazily initialized singleton instance of ConversationService."""
    return ConversationService(
        llm_service=get_llm_service(),
        context_assembly=get_context_assembly_service(),
        tool_service=get_tool_service(),
        annotation_service=AssistantAnnotationService(),
        memory_storage=get_memory_storage(),
    )
