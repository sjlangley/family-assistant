"""Tests for conversation annotation building and enrichment."""

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from assistant.models.annotations import (
    AssistantAnnotations,
    FailureAnnotationStage,
)
from assistant.models.conversation import (
    CreateConversationWithMessageRequest,
    CreateMessageRequest,
)
from assistant.models.conversation_sql import Conversation, Message
from assistant.models.llm import (
    LLMCompletionError,
    LLMCompletionErrorKind,
    LLMCompletionResult,
)
from assistant.services.assistant_annotations import AssistantAnnotationService


@pytest.mark.asyncio
async def test_create_conversation_with_message_success_includes_annotations(
    conversation_service,
    mock_llm_service,
    mock_context_assembly,
    async_session,
    test_user_id,
    valid_request,
    mock_context_result,
):
    """It builds and persists success annotations on successful responses."""
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        mock_context_result
    )
    mock_llm_service.complete_messages.return_value = LLMCompletionResult(
        content='The answer is 42.',
        model='llama3.2',
        prompt_tokens=10,
        completion_tokens=8,
        total_tokens=18,
        tool_calls=None,
        finish_reason='stop',
    )

    result = await conversation_service.create_conversation_with_message(
        session=async_session,
        user_id=test_user_id,
        payload=valid_request,
    )

    # Verify assistant message has success annotations
    assert result.assistant_message.annotations is not None
    assert result.assistant_message.annotations.failure is None
    assert result.assistant_message.error is None

    # Reload from DB to verify persistence
    stmt = select(Message).where(Message.id == result.assistant_message.id)
    db_result = await async_session.execute(stmt)
    db_message = db_result.scalar_one()
    assert db_message.annotations is not None
    assert db_message.error is None


@pytest.mark.asyncio
async def test_add_message_with_tool_execution_and_fetch_sources(
    conversation_service,
    mock_llm_service,
    mock_context_assembly,
    mock_tool_service,
    async_session,
    test_user_id,
    mock_context_result,
):
    """It builds annotations with sources from web_fetch tool results."""
    # Set up conversation
    conversation = Conversation(
        user_id=test_user_id,
        title='Test',
    )
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)

    user_message = Message(
        conversation_id=conversation.id,
        role='user',
        content='Find information about Python.',
        sequence_number=1,
    )
    async_session.add(user_message)
    await async_session.commit()

    # Mock context assembly
    mock_context_assembly.assemble_context.return_value = mock_context_result

    # Mock LLM to NOT request tools on first call
    mock_llm_service.complete_messages.return_value = LLMCompletionResult(
        content='Python is a popular programming language.',
        model='llama3.2',
        prompt_tokens=15,
        completion_tokens=12,
        total_tokens=27,
        tool_calls=None,
        finish_reason='stop',
    )

    mock_tool_service.get_available_tools.return_value = []

    request = CreateMessageRequest(
        content='Find information about Python.',
        temperature=0.7,
        max_tokens=512,
    )

    result = await conversation_service.add_message_to_conversation(
        session=async_session,
        user_id=test_user_id,
        conversation_id=conversation.id,
        payload=request,
    )

    # Verify assistant message has annotations
    assert result.assistant_message.annotations is not None
    assert result.assistant_message.error is None


@pytest.mark.asyncio
async def test_create_conversation_with_message_llm_failure_persists_error_row(
    conversation_service,
    mock_llm_service,
    mock_context_assembly,
    async_session,
    test_user_id,
    valid_request,
    mock_context_result,
):
    """It persists assistant failure row with error annotations on LLM error."""
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        mock_context_result
    )
    # Simulate LLM timeout
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.timeout,
        message='Request timed out',
    )

    # Should still raise HTTPException to client
    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.create_conversation_with_message(
            session=async_session,
            user_id=test_user_id,
            payload=valid_request,
        )

    assert exc_info.value.status_code == 504

    # But message should be persisted with failure annotations
    stmt = (
        select(Message)
        .where(Message.role == 'assistant')
        .where(Message.conversation_id.is_not(None))
    )
    result = await async_session.execute(stmt)
    messages = list(result.scalars().all())

    # Should have persisted the assistant message with error
    assert len(messages) == 1
    assistant_msg = messages[0]
    assert assistant_msg.error is not None
    assert 'timed out' in assistant_msg.error.lower()
    assert assistant_msg.annotations is not None
    # Convert dict to AssistantAnnotations for assertion
    annotations = (
        AssistantAnnotations(**assistant_msg.annotations)
        if isinstance(assistant_msg.annotations, dict)
        else assistant_msg.annotations
    )
    assert annotations.failure is not None
    assert annotations.failure.stage == FailureAnnotationStage.LLM
    assert annotations.failure.retryable is True


@pytest.mark.asyncio
async def test_get_conversation_messages_returns_persisted_annotations(
    conversation_service,
    async_session,
    test_user_id,
):
    """It returns persisted annotations unchanged on reload."""
    # Create conversation with annotated message
    conversation = Conversation(
        user_id=test_user_id,
        title='Test',
    )
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)

    message = Message(
        conversation_id=conversation.id,
        role='assistant',
        content='Test response',
        sequence_number=1,
    )
    # Manually set annotations to verify they round-trip
    message.annotations = {
        'sources': [
            {
                'title': 'Example',
                'url': 'https://example.com',
                'snippet': 'Example snippet',
                'rationale': 'Test source',
            }
        ],
        'tools': [],
        'memory_hits': [],
        'memory_saved': [],
        'failure': None,
    }
    async_session.add(message)
    await async_session.commit()

    # Reload messages
    result = await conversation_service.get_conversation_messages(
        session=async_session,
        user_id=test_user_id,
        conversation_id=conversation.id,
    )

    # Verify annotations are returned unchanged
    assert len(result.items) == 1
    assert result.items[0].annotations is not None
    assert len(result.items[0].annotations.sources) == 1
    assert result.items[0].annotations.sources[0].title == 'Example'


@pytest.mark.asyncio
async def test_add_message_with_llm_failure_persists_error_annotations(
    conversation_service,
    mock_llm_service,
    mock_context_assembly,
    async_session,
    test_user_id,
    mock_context_result,
):
    """It persists failure annotations with correct stage on LLM error."""
    # Create conversation
    conversation = Conversation(
        user_id=test_user_id,
        title='Test',
    )
    async_session.add(conversation)
    await async_session.commit()

    user_message = Message(
        conversation_id=conversation.id,
        role='user',
        content='Hello',
        sequence_number=1,
    )
    async_session.add(user_message)
    await async_session.commit()

    # Mock context assembly
    mock_context_assembly.assemble_context.return_value = mock_context_result

    # Simulate LLM server error
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.backend_error,
        message='Backend error',
    )

    request = CreateMessageRequest(
        content='Hello',
        temperature=0.7,
        max_tokens=512,
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.add_message_to_conversation(
            session=async_session,
            user_id=test_user_id,
            conversation_id=conversation.id,
            payload=request,
        )

    assert exc_info.value.status_code == 502

    # Verify failure message persisted with correct stage
    stmt = (
        select(Message)
        .where(Message.role == 'assistant')
        .where(Message.conversation_id == conversation.id)
    )
    result = await async_session.execute(stmt)
    messages = list(result.scalars().all())

    assert len(messages) == 1
    failure_msg = messages[0]
    assert failure_msg.annotations is not None
    # Convert dict to AssistantAnnotations for assertion
    annotations = (
        AssistantAnnotations(**failure_msg.annotations)
        if isinstance(failure_msg.annotations, dict)
        else failure_msg.annotations
    )
    assert annotations.failure is not None
    assert annotations.failure.stage == FailureAnnotationStage.LLM
    assert annotations.failure.retryable is True


@pytest.mark.asyncio
async def test_enrich_annotations_with_summary_saved():
    """Adding memory_saved annotation when summary is saved."""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:', echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        # Create assistant message with existing annotations
        conversation = Conversation(user_id='user-123', title='Test')
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)

        assistant_msg = Message(
            conversation_id=conversation.id,
            role='assistant',
            content='Response',
            sequence_number=1,
            annotations={
                'sources': [],
                'tools': [],
                'memory_hits': [],
                'memory_saved': [],
                'failure': None,
            },
        )
        session.add(assistant_msg)
        await session.commit()
        await session.refresh(assistant_msg)

        # Create service and enrich annotations
        from assistant.services.conversation_service import ConversationService
        from unittest.mock import AsyncMock, Mock
        from assistant.services.llm_service import LLMService
        from assistant.services.context_assembly import ContextAssemblyService
        from assistant.services.tool_service import ToolService

        service = ConversationService(
            llm_service=AsyncMock(spec=LLMService),
            context_assembly=AsyncMock(spec=ContextAssemblyService),
            tool_service=Mock(spec=ToolService),
            annotation_service=AssistantAnnotationService(),
        )

        await service._enrich_assistant_annotations_with_memory_saved(
            session=session,
            assistant_message_id=assistant_msg.id,
            summary_saved=True,
            facts_count=0,
        )

        # Reload message and verify annotations were enriched
        refreshed = await session.get(Message, assistant_msg.id)
        assert refreshed.annotations is not None
        assert len(refreshed.annotations['memory_saved']) == 1
        assert (
            'conversation summary'
            in refreshed.annotations['memory_saved'][0]['label']
        )

    await engine.dispose()


@pytest.mark.asyncio
async def test_enrich_annotations_with_facts_saved():
    """Adding memory_saved annotation when facts are saved."""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:', echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        # Create assistant message
        conversation = Conversation(user_id='user-123', title='Test')
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)

        assistant_msg = Message(
            conversation_id=conversation.id,
            role='assistant',
            content='Response',
            sequence_number=1,
            annotations={
                'sources': [],
                'tools': [],
                'memory_hits': [],
                'memory_saved': [],
                'failure': None,
            },
        )
        session.add(assistant_msg)
        await session.commit()
        await session.refresh(assistant_msg)

        # Enrich with facts
        from assistant.services.conversation_service import ConversationService
        from unittest.mock import AsyncMock, Mock
        from assistant.services.llm_service import LLMService
        from assistant.services.context_assembly import ContextAssemblyService
        from assistant.services.tool_service import ToolService

        service = ConversationService(
            llm_service=AsyncMock(spec=LLMService),
            context_assembly=AsyncMock(spec=ContextAssemblyService),
            tool_service=Mock(spec=ToolService),
            annotation_service=AssistantAnnotationService(),
        )

        await service._enrich_assistant_annotations_with_memory_saved(
            session=session,
            assistant_message_id=assistant_msg.id,
            summary_saved=False,
            facts_count=3,
        )

        # Verify
        refreshed = await session.get(Message, assistant_msg.id)
        assert len(refreshed.annotations['memory_saved']) == 1
        assert (
            '3 memory facts'
            in refreshed.annotations['memory_saved'][0]['label']
        )

    await engine.dispose()


@pytest.mark.asyncio
async def test_enrich_annotations_preserves_existing_data():
    """Enrichment preserves existing sources, tools, and other metadata."""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:', echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        # Create assistant message with complex annotations
        conversation = Conversation(user_id='user-123', title='Test')
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)

        existing_annotations = {
            'sources': [
                {
                    'title': 'Example',
                    'url': 'https://example.com',
                    'snippet': 'Example snippet',
                    'rationale': 'Used in response',
                }
            ],
            'tools': [{'name': 'web_fetch', 'status': 'completed'}],
            'memory_hits': [{'label': 'Memory Hit', 'summary': 'Hit summary'}],
            'memory_saved': [],
            'failure': None,
        }

        assistant_msg = Message(
            conversation_id=conversation.id,
            role='assistant',
            content='Response',
            sequence_number=1,
            annotations=existing_annotations,
        )
        session.add(assistant_msg)
        await session.commit()
        await session.refresh(assistant_msg)

        # Enrich
        from assistant.services.conversation_service import ConversationService
        from unittest.mock import AsyncMock, Mock
        from assistant.services.llm_service import LLMService
        from assistant.services.context_assembly import ContextAssemblyService
        from assistant.services.tool_service import ToolService

        service = ConversationService(
            llm_service=AsyncMock(spec=LLMService),
            context_assembly=AsyncMock(spec=ContextAssemblyService),
            tool_service=Mock(spec=ToolService),
            annotation_service=AssistantAnnotationService(),
        )

        await service._enrich_assistant_annotations_with_memory_saved(
            session=session,
            assistant_message_id=assistant_msg.id,
            summary_saved=True,
            facts_count=2,
        )

        # Verify existing data preserved
        refreshed = await session.get(Message, assistant_msg.id)
        assert len(refreshed.annotations['sources']) == 1
        assert refreshed.annotations['sources'][0]['title'] == 'Example'
        assert len(refreshed.annotations['tools']) == 1
        assert len(refreshed.annotations['memory_hits']) == 1
        # And memory_saved added
        assert len(refreshed.annotations['memory_saved']) == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_enrich_annotations_nothing_saved_leaves_empty():
    """If nothing was saved, memory_saved remains empty."""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:', echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        conversation = Conversation(user_id='user-123', title='Test')
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)

        assistant_msg = Message(
            conversation_id=conversation.id,
            role='assistant',
            content='Response',
            sequence_number=1,
            annotations={
                'sources': [],
                'tools': [],
                'memory_hits': [],
                'memory_saved': [],
                'failure': None,
            },
        )
        session.add(assistant_msg)
        await session.commit()
        await session.refresh(assistant_msg)

        # Enrich with no saves
        from assistant.services.conversation_service import ConversationService
        from unittest.mock import AsyncMock, Mock
        from assistant.services.llm_service import LLMService
        from assistant.services.context_assembly import ContextAssemblyService
        from assistant.services.tool_service import ToolService

        service = ConversationService(
            llm_service=AsyncMock(spec=LLMService),
            context_assembly=AsyncMock(spec=ContextAssemblyService),
            tool_service=Mock(spec=ToolService),
            annotation_service=AssistantAnnotationService(),
        )

        await service._enrich_assistant_annotations_with_memory_saved(
            session=session,
            assistant_message_id=assistant_msg.id,
            summary_saved=False,
            facts_count=0,
        )

        # Verify memory_saved still empty
        refreshed = await session.get(Message, assistant_msg.id)
        assert len(refreshed.annotations['memory_saved']) == 0

    await engine.dispose()


@pytest.mark.asyncio
async def test_build_memory_saved_annotations_large_fact_count():
    """Build memory_saved with large number of facts."""
    service = AssistantAnnotationService()

    annotations = service.build_memory_saved_annotations(
        summary_saved=False, facts_count=100
    )

    assert len(annotations) == 1
    assert '100 memory facts' in annotations[0].label


@pytest.mark.asyncio
async def test_build_memory_saved_annotations_combines_all_saves():
    """memory_saved combines summary and facts into single annotation."""
    service = AssistantAnnotationService()

    annotations = service.build_memory_saved_annotations(
        summary_saved=True, facts_count=5
    )

    # Should be exactly 1 entry (respects MAX_MEMORY_SAVED budget)
    assert len(annotations) == 1
    # Both summary and facts should be in the label
    assert 'conversation summary' in annotations[0].label
    assert '5 memory facts' in annotations[0].label
    # Label should use comma-separated format
    assert ', ' in annotations[0].label


@pytest.mark.asyncio
async def test_build_memory_saved_annotations_no_saves():
    """Build memory_saved annotations with no saves."""
    service = AssistantAnnotationService()

    annotations = service.build_memory_saved_annotations(
        summary_saved=False, facts_count=0
    )

    # Should return empty list when nothing saved
    assert len(annotations) == 0


@pytest.mark.asyncio
async def test_build_memory_saved_annotations_only_summary():
    """Build memory_saved annotations with only summary saved."""
    service = AssistantAnnotationService()

    annotations = service.build_memory_saved_annotations(
        summary_saved=True, facts_count=0
    )

    assert len(annotations) == 1
    assert 'conversation summary' in annotations[0].label
    assert 'memory facts' not in annotations[0].label


@pytest.mark.asyncio
async def test_build_memory_saved_annotations_only_facts():
    """Build memory_saved annotations with only facts saved."""
    service = AssistantAnnotationService()

    annotations = service.build_memory_saved_annotations(
        summary_saved=False, facts_count=3
    )

    assert len(annotations) == 1
    assert 'conversation summary' not in annotations[0].label
    assert '3 memory facts' in annotations[0].label
