"""Shared fixtures for conversation service tests."""

from unittest.mock import AsyncMock, Mock
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from assistant.models.conversation import (
    CreateConversationWithMessageRequest,
)
from assistant.models.llm import (
    LLMCompletionResult,
)
from assistant.services.context_assembly import (
    ContextAssemblyResult,
    ContextAssemblyService,
)
from assistant.services.conversation_service import ConversationService
from assistant.services.llm_service import LLMService
from assistant.services.memory_storage import MemoryStorage
from assistant.services.tool_service import ToolService


@pytest_asyncio.fixture
async def async_session():
    """Create an in-memory SQLite database session for testing."""
    engine = create_async_engine(
        'sqlite+aiosqlite:///:memory:',
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def mock_llm_service():
    """Create a mock LLM service."""
    return AsyncMock(spec=LLMService)


@pytest.fixture
def mock_memory_storage():
    """Create a mock MemoryStorage."""
    return AsyncMock(spec=MemoryStorage)


@pytest.fixture
def mock_context_assembly():
    """Create a mock ContextAssemblyService."""
    return AsyncMock(spec=ContextAssemblyService)


@pytest.fixture
def mock_tool_service():
    """Create a mock ToolService."""
    mock_service = Mock(spec=ToolService)
    mock_service.execute_tool = AsyncMock()
    mock_service.get_available_tools.return_value = []
    return mock_service


@pytest.fixture
def conversation_service(
    mock_llm_service,
    mock_memory_storage,
    mock_context_assembly,
    mock_tool_service,
):
    """Create a ConversationService with mocked dependencies."""
    return ConversationService(
        llm_service=mock_llm_service,
        memory_storage=mock_memory_storage,
        context_assembly=mock_context_assembly,
        tool_service=mock_tool_service,
    )


@pytest.fixture
def test_user_id():
    """Generate a test user ID."""
    return str(uuid.uuid4())


@pytest.fixture
def valid_request():
    """Create a valid conversation request."""
    return CreateConversationWithMessageRequest(
        content='Hello, how are you?',
        temperature=0.7,
        max_tokens=512,
    )


@pytest.fixture
def mock_llm_response():
    """Create a mock LLM response."""
    return LLMCompletionResult(
        content='I am doing well, thank you!',
        model='llama3.2',
        prompt_tokens=10,
        completion_tokens=15,
        total_tokens=25,
        tool_calls=None,
        finish_reason='stop',
    )


@pytest.fixture
def mock_context_result():
    """Create a mock context assembly result for new conversation."""
    return ContextAssemblyResult(
        messages=[{'role': 'user', 'content': 'Hello, how are you?'}],
        used_summary=False,
        summary_id=None,
        fact_ids=[],
    )
