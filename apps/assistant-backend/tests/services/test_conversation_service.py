"""Tests for ConversationService."""

import asyncio
from datetime import datetime, timezone
import json
from unittest.mock import AsyncMock, Mock, patch
import uuid

import pytest
from sqlalchemy import select

from assistant.models.conversation import (
    CreateConversationWithMessageRequest,
    CreateMessageRequest,
)
from assistant.models.conversation_sql import Conversation, Message
from assistant.models.llm import (
    ChatCompletionMessageToolCall,
    ChatCompletionMessageToolCallFunction,
    CompletionUsage,
    LLMCompletionError,
    LLMCompletionErrorKind,
    StreamParserOutput,
)
from assistant.services.assistant_annotations import AssistantAnnotationService
from assistant.services.context_assembly import (
    ContextAssemblyResult,
    ContextAssemblyService,
)
from assistant.services.conversation_service import ConversationService
from assistant.services.llm_service import LLMService
from assistant.services.memory_storage import MemoryStorage
from assistant.services.tool_service import ToolService

pytestmark = pytest.mark.asyncio


# Integration tests for extract_and_save_background orchestration
async def test_extract_and_save_background_successful_with_summary_and_facts():
    """Extract and save background with both summary and facts extracted."""
    user_id = 'user123'
    conv_id = uuid.uuid4()
    assistant_msg_id = uuid.uuid4()
    user_msg_id = uuid.uuid4()

    # Mock LLM response with both summary and facts
    llm_response_text = (
        '{"summary": "Test summary", "facts": ['
        '{"subject": "Topic", "fact": "Important fact", "confidence": "high"}'
        ']}'
    )

    # Create mocks
    mock_llm_service = AsyncMock(spec=LLMService)
    mock_llm_service.complete_messages = AsyncMock(
        return_value=type(
            'Result',
            (),
            {
                'content': llm_response_text,
            },
        )()
    )

    mock_memory_storage = AsyncMock(spec=MemoryStorage)
    mock_summary = Message(
        id=uuid.uuid4(),
        conversation_id=conv_id,
        role='system',
        content='Test summary',
        sequence_number=0,
    )
    mock_fact = Message(
        id=uuid.uuid4(),
        conversation_id=conv_id,
        role='system',
        content='Important fact',
        sequence_number=1,
    )
    mock_memory_storage.upsert_conversation_summary = AsyncMock(
        return_value=mock_summary
    )
    mock_memory_storage.upsert_durable_fact = AsyncMock(return_value=mock_fact)

    service = ConversationService(
        llm_service=mock_llm_service,
        context_assembly=AsyncMock(spec=ContextAssemblyService),
        tool_service=Mock(spec=ToolService),
        annotation_service=AssistantAnnotationService(),
        memory_storage=mock_memory_storage,
    )

    # Mock database session and queries
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    service._get_conversation_for_user = AsyncMock(
        return_value=Conversation(
            id=conv_id,
            user_id=user_id,
            title='Test',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )

    assistant_msg = Message(
        id=assistant_msg_id,
        conversation_id=conv_id,
        role='assistant',
        content='Assistant response',
        sequence_number=1,
    )

    service._get_messages_for_conversation = AsyncMock(
        return_value=[
            Message(
                id=user_msg_id,
                conversation_id=conv_id,
                role='user',
                content='User question',
                sequence_number=0,
            ),
            assistant_msg,
        ]
    )

    service._enrich_assistant_annotations_with_memory_saved = AsyncMock()

    # Patch get_db_session to return our mock session
    with patch(
        'assistant.utils.database.get_db_session',
        return_value=mock_session,
    ):
        await service.extract_and_save_background(
            user_id=user_id,
            conversation_id=conv_id,
            assistant_message_id=assistant_msg_id,
            latest_user_message_id=user_msg_id,
        )

    # Verify summary was persisted
    mock_memory_storage.upsert_conversation_summary.assert_called_once()
    # Verify fact was persisted
    mock_memory_storage.upsert_durable_fact.assert_called_once()
    # Verify indexing was attempted
    mock_memory_storage.index_conversation_summary.assert_called_once()
    mock_memory_storage.index_durable_fact.assert_called_once()
    # Verify annotations were enriched
    service._enrich_assistant_annotations_with_memory_saved.assert_called_once()


async def test_extract_and_save_background_with_only_summary():
    """Extract and save background with summary but no facts."""
    user_id = 'user123'
    conv_id = uuid.uuid4()
    assistant_msg_id = uuid.uuid4()

    # Mock LLM response with only summary
    llm_response_text = '{"summary": "Only summary", "facts": []}'

    mock_llm_service = AsyncMock(spec=LLMService)
    mock_llm_service.complete_messages = AsyncMock(
        return_value=type(
            'Result',
            (),
            {
                'content': llm_response_text,
            },
        )()
    )

    mock_memory_storage = AsyncMock(spec=MemoryStorage)
    mock_summary = Message(
        id=uuid.uuid4(),
        conversation_id=conv_id,
        role='system',
        content='Only summary',
        sequence_number=0,
    )
    mock_memory_storage.upsert_conversation_summary = AsyncMock(
        return_value=mock_summary
    )

    service = ConversationService(
        llm_service=mock_llm_service,
        context_assembly=AsyncMock(spec=ContextAssemblyService),
        tool_service=Mock(spec=ToolService),
        annotation_service=AssistantAnnotationService(),
        memory_storage=mock_memory_storage,
    )

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    assistant_msg = Message(
        id=assistant_msg_id,
        conversation_id=conv_id,
        role='assistant',
        content='Response',
        sequence_number=1,
    )

    service._get_conversation_for_user = AsyncMock(
        return_value=Conversation(
            id=conv_id,
            user_id=user_id,
            title='Test',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    service._get_messages_for_conversation = AsyncMock(
        return_value=[assistant_msg]
    )
    service._enrich_assistant_annotations_with_memory_saved = AsyncMock()

    with patch(
        'assistant.utils.database.get_db_session',
        return_value=mock_session,
    ):
        await service.extract_and_save_background(
            user_id=user_id,
            conversation_id=conv_id,
            assistant_message_id=assistant_msg_id,
        )

    # Verify summary was persisted
    mock_memory_storage.upsert_conversation_summary.assert_called_once()
    # Verify no facts were persisted
    mock_memory_storage.upsert_durable_fact.assert_not_called()
    # Verify annotation enrichment was called (had summary save)
    service._enrich_assistant_annotations_with_memory_saved.assert_called_once()


async def test_extract_and_save_background_with_only_facts():
    """Extract and save background with facts but no summary."""
    user_id = 'user123'
    conv_id = uuid.uuid4()
    assistant_msg_id = uuid.uuid4()

    # Mock LLM response with only facts
    llm_response_text = (
        '{"summary": "", "facts": ['
        '{"subject": "Topic", "fact": "Fact text", "confidence": "medium"}'
        ']}'
    )

    mock_llm_service = AsyncMock(spec=LLMService)
    mock_llm_service.complete_messages = AsyncMock(
        return_value=type(
            'Result',
            (),
            {
                'content': llm_response_text,
            },
        )()
    )

    mock_memory_storage = AsyncMock(spec=MemoryStorage)
    mock_fact = Message(
        id=uuid.uuid4(),
        conversation_id=conv_id,
        role='system',
        content='Fact text',
        sequence_number=0,
    )
    mock_memory_storage.upsert_durable_fact = AsyncMock(return_value=mock_fact)

    service = ConversationService(
        llm_service=mock_llm_service,
        context_assembly=AsyncMock(spec=ContextAssemblyService),
        tool_service=Mock(spec=ToolService),
        annotation_service=AssistantAnnotationService(),
        memory_storage=mock_memory_storage,
    )

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    assistant_msg = Message(
        id=assistant_msg_id,
        conversation_id=conv_id,
        role='assistant',
        content='Response',
        sequence_number=0,
    )

    service._get_conversation_for_user = AsyncMock(
        return_value=Conversation(
            id=conv_id,
            user_id=user_id,
            title='Test',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    service._get_messages_for_conversation = AsyncMock(
        return_value=[assistant_msg]
    )
    service._enrich_assistant_annotations_with_memory_saved = AsyncMock()

    with patch(
        'assistant.utils.database.get_db_session',
        return_value=mock_session,
    ):
        await service.extract_and_save_background(
            user_id=user_id,
            conversation_id=conv_id,
            assistant_message_id=assistant_msg_id,
        )

    # Verify only facts were persisted
    mock_memory_storage.upsert_conversation_summary.assert_not_called()
    mock_memory_storage.upsert_durable_fact.assert_called_once()
    # Verify annotation enrichment was called (had facts)
    service._enrich_assistant_annotations_with_memory_saved.assert_called_once()


async def test_extract_and_save_background_no_extraction():
    """Extract and save background when nothing is extracted."""
    user_id = 'user123'
    conv_id = uuid.uuid4()
    assistant_msg_id = uuid.uuid4()

    # Mock LLM response with no content
    llm_response_text = '{"summary": "", "facts": []}'

    mock_llm_service = AsyncMock(spec=LLMService)
    mock_llm_service.complete_messages = AsyncMock(
        return_value=type(
            'Result',
            (),
            {
                'content': llm_response_text,
            },
        )()
    )

    mock_memory_storage = AsyncMock(spec=MemoryStorage)

    service = ConversationService(
        llm_service=mock_llm_service,
        context_assembly=AsyncMock(spec=ContextAssemblyService),
        tool_service=Mock(spec=ToolService),
        annotation_service=AssistantAnnotationService(),
        memory_storage=mock_memory_storage,
    )

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    assistant_msg = Message(
        id=assistant_msg_id,
        conversation_id=conv_id,
        role='assistant',
        content='Response',
        sequence_number=0,
    )

    service._get_conversation_for_user = AsyncMock(
        return_value=Conversation(
            id=conv_id,
            user_id=user_id,
            title='Test',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    service._get_messages_for_conversation = AsyncMock(
        return_value=[assistant_msg]
    )
    service._enrich_assistant_annotations_with_memory_saved = AsyncMock()

    with patch(
        'assistant.utils.database.get_db_session',
        return_value=mock_session,
    ):
        await service.extract_and_save_background(
            user_id=user_id,
            conversation_id=conv_id,
            assistant_message_id=assistant_msg_id,
        )

    # Verify nothing was persisted
    mock_memory_storage.upsert_conversation_summary.assert_not_called()
    mock_memory_storage.upsert_durable_fact.assert_not_called()
    # Verify annotation enrichment was NOT called (nothing saved)
    service._enrich_assistant_annotations_with_memory_saved.assert_not_called()


async def test_extract_and_save_background_missing_assistant_message():
    """Extract and save background when assistant message not found."""
    user_id = 'user123'
    conv_id = uuid.uuid4()
    assistant_msg_id = uuid.uuid4()

    service = ConversationService(
        llm_service=AsyncMock(spec=LLMService),
        context_assembly=AsyncMock(spec=ContextAssemblyService),
        tool_service=Mock(spec=ToolService),
        annotation_service=AssistantAnnotationService(),
    )

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    service._get_conversation_for_user = AsyncMock(
        return_value=Conversation(
            id=conv_id,
            user_id=user_id,
            title='Test',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    # Return messages without the assistant message
    service._get_messages_for_conversation = AsyncMock(
        return_value=[
            Message(
                id=uuid.uuid4(),
                conversation_id=conv_id,
                role='user',
                content='User message',
                sequence_number=0,
            )
        ]
    )

    with patch(
        'assistant.utils.database.get_db_session',
        return_value=mock_session,
    ):
        # Should return early without error
        await service.extract_and_save_background(
            user_id=user_id,
            conversation_id=conv_id,
            assistant_message_id=assistant_msg_id,
        )

    # LLM should not be called if message not found
    service.llm_service.complete_messages.assert_not_called()


async def test_extract_and_save_background_llm_error():
    """Extract and save background when LLM fails."""
    user_id = 'user123'
    conv_id = uuid.uuid4()
    assistant_msg_id = uuid.uuid4()

    # Mock LLM error
    mock_llm_service = AsyncMock(spec=LLMService)
    mock_llm_service.complete_messages = AsyncMock(
        side_effect=Exception('LLM service error')
    )

    mock_memory_storage = AsyncMock(spec=MemoryStorage)

    service = ConversationService(
        llm_service=mock_llm_service,
        context_assembly=AsyncMock(spec=ContextAssemblyService),
        tool_service=Mock(spec=ToolService),
        annotation_service=AssistantAnnotationService(),
        memory_storage=mock_memory_storage,
    )

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    assistant_msg = Message(
        id=assistant_msg_id,
        conversation_id=conv_id,
        role='assistant',
        content='Response',
        sequence_number=0,
    )

    service._get_conversation_for_user = AsyncMock(
        return_value=Conversation(
            id=conv_id,
            user_id=user_id,
            title='Test',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    service._get_messages_for_conversation = AsyncMock(
        return_value=[assistant_msg]
    )

    with patch(
        'assistant.utils.database.get_db_session',
        return_value=mock_session,
    ):
        # Should not raise - errors are logged but not propagated
        await service.extract_and_save_background(
            user_id=user_id,
            conversation_id=conv_id,
            assistant_message_id=assistant_msg_id,
        )

    # Session should be rolled back on error
    mock_session.rollback.assert_called()


async def test_extract_and_save_background_indexing_failure_nonfatal():
    """Extract and save background when Chroma indexing fails (should not propagate)."""
    user_id = 'user123'
    conv_id = uuid.uuid4()
    assistant_msg_id = uuid.uuid4()

    # Mock LLM response
    llm_response_text = (
        '{"summary": "Test", "facts": ['
        '{"subject": "Topic", "fact": "Fact", "confidence": "high"}'
        ']}'
    )

    mock_llm_service = AsyncMock(spec=LLMService)
    mock_llm_service.complete_messages = AsyncMock(
        return_value=type(
            'Result',
            (),
            {
                'content': llm_response_text,
            },
        )()
    )

    mock_memory_storage = AsyncMock(spec=MemoryStorage)
    mock_summary = Message(
        id=uuid.uuid4(),
        conversation_id=conv_id,
        role='system',
        content='Test',
        sequence_number=0,
    )
    mock_fact = Message(
        id=uuid.uuid4(),
        conversation_id=conv_id,
        role='system',
        content='Fact',
        sequence_number=1,
    )
    mock_memory_storage.upsert_conversation_summary = AsyncMock(
        return_value=mock_summary
    )
    mock_memory_storage.upsert_durable_fact = AsyncMock(return_value=mock_fact)
    # Index methods raise exceptions
    mock_memory_storage.index_conversation_summary = Mock(
        side_effect=Exception('Chroma error')
    )
    mock_memory_storage.index_durable_fact = Mock(
        side_effect=Exception('Chroma error')
    )

    service = ConversationService(
        llm_service=mock_llm_service,
        context_assembly=AsyncMock(spec=ContextAssemblyService),
        tool_service=Mock(spec=ToolService),
        annotation_service=AssistantAnnotationService(),
        memory_storage=mock_memory_storage,
    )

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    assistant_msg = Message(
        id=assistant_msg_id,
        conversation_id=conv_id,
        role='assistant',
        content='Response',
        sequence_number=0,
    )

    service._get_conversation_for_user = AsyncMock(
        return_value=Conversation(
            id=conv_id,
            user_id=user_id,
            title='Test',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    service._get_messages_for_conversation = AsyncMock(
        return_value=[assistant_msg]
    )
    service._enrich_assistant_annotations_with_memory_saved = AsyncMock()

    with patch(
        'assistant.utils.database.get_db_session',
        return_value=mock_session,
    ):
        # Should not raise even though indexing failed
        await service.extract_and_save_background(
            user_id=user_id,
            conversation_id=conv_id,
            assistant_message_id=assistant_msg_id,
        )

    # Verify memory was persisted despite indexing failure
    mock_memory_storage.upsert_conversation_summary.assert_called_once()
    # Verify enrichment still happened
    service._enrich_assistant_annotations_with_memory_saved.assert_called_once()


async def test_add_message_to_conversation_stream_persists_lifecycle_success(
    conversation_service,
    mock_llm_service,
    mock_context_assembly,
    async_session,
    test_user_id,
):
    """Streaming path persists user immediately and assistant on terminal completion."""
    conversation = Conversation(user_id=test_user_id, title='Streaming Test')
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)

    mock_context_assembly.assemble_context.return_value = ContextAssemblyResult(
        messages=[{'role': 'user', 'content': 'Hello stream'}],
        used_summary=False,
        summary_id=None,
        fact_ids=[],
    )

    async def stream_outputs():
        yield StreamParserOutput(thought='thinking...')
        yield StreamParserOutput(token='Hello')
        yield StreamParserOutput(
            token=' world',
            finish_reason='stop',
            usage=CompletionUsage(
                prompt_tokens=4,
                completion_tokens=2,
                total_tokens=6,
            ),
            model='test-model',
        )

    mock_llm_service.stream_messages = Mock(return_value=stream_outputs())

    payload = CreateMessageRequest(content='Hello stream')

    stream = conversation_service.add_message_to_conversation_stream(
        session=async_session,
        user_id=test_user_id,
        conversation_id=conversation.id,
        payload=payload,
    )

    first_event = await anext(stream)

    # User message should already be durable before stream completion.
    result = await async_session.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.sequence_number.asc())
    )
    in_flight_messages = list(result.scalars().all())
    assert len(in_flight_messages) == 1
    assert in_flight_messages[0].role == 'user'
    assert in_flight_messages[0].content == 'Hello stream'

    remaining_events = []
    async for event in stream:
        remaining_events.append(event)

    all_events = [first_event] + remaining_events
    assert any(event.startswith('event: thought') for event in all_events)
    assert any(event.startswith('event: token') for event in all_events)
    done_event = next(
        event for event in all_events if event.startswith('event: done')
    )
    done_payload = json.loads(done_event.split('data: ', 1)[1].strip())
    assert done_payload['conversation_id'] == str(conversation.id)
    assert done_payload['content'] == 'Hello world'
    assert done_payload['model'] == 'test-model'
    assert done_payload['usage']['total_tokens'] == 6
    assert done_payload['annotations']['thought'] == 'thinking...'

    result = await async_session.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.sequence_number.asc())
    )
    persisted_messages = list(result.scalars().all())
    assert len(persisted_messages) == 2
    assert persisted_messages[1].role == 'assistant'
    assert persisted_messages[1].content == 'Hello world'
    assert persisted_messages[1].error is None
    assert persisted_messages[1].annotations['thought'] == 'thinking...'


async def test_add_message_to_conversation_stream_persists_error_with_partial_assistant(
    conversation_service,
    mock_llm_service,
    mock_context_assembly,
    async_session,
    test_user_id,
):
    """Interrupted streams persist partial assistant output in terminal error state."""
    conversation = Conversation(user_id=test_user_id, title='Streaming Error')
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)

    mock_context_assembly.assemble_context.return_value = ContextAssemblyResult(
        messages=[{'role': 'user', 'content': 'Trigger stream error'}],
        used_summary=False,
        summary_id=None,
        fact_ids=[],
    )

    async def stream_outputs():
        yield StreamParserOutput(token='partial output')
        raise LLMCompletionError(
            kind=LLMCompletionErrorKind.timeout,
            message='LLM request timed out',
        )

    mock_llm_service.stream_messages = Mock(return_value=stream_outputs())

    payload = CreateMessageRequest(content='Trigger stream error')

    emitted_events = []
    async for event in conversation_service.add_message_to_conversation_stream(
        session=async_session,
        user_id=test_user_id,
        conversation_id=conversation.id,
        payload=payload,
    ):
        emitted_events.append(event)

    assert any(event.startswith('event: token') for event in emitted_events)
    error_event = next(
        event for event in emitted_events if event.startswith('event: error')
    )
    error_payload = json.loads(error_event.split('data: ', 1)[1].strip())
    assert 'timed out' in error_payload['detail'].lower()

    result = await async_session.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.sequence_number.asc())
    )
    persisted_messages = list(result.scalars().all())
    assert len(persisted_messages) == 2
    assert persisted_messages[1].role == 'assistant'
    assert persisted_messages[1].content == 'partial output'
    assert 'timed out' in (persisted_messages[1].error or '').lower()
    assert persisted_messages[1].annotations['failure']['stage'] == 'llm'


async def test_add_message_to_conversation_stream_skips_assistant_persistence_without_output(
    conversation_service,
    mock_llm_service,
    mock_context_assembly,
    async_session,
    test_user_id,
):
    """If stream fails before output starts, only the user message is persisted."""
    conversation = Conversation(
        user_id=test_user_id, title='Streaming Early Failure'
    )
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)

    mock_context_assembly.assemble_context.return_value = ContextAssemblyResult(
        messages=[{'role': 'user', 'content': 'Fail immediately'}],
        used_summary=False,
        summary_id=None,
        fact_ids=[],
    )

    async def stream_outputs():
        raise LLMCompletionError(
            kind=LLMCompletionErrorKind.unreachable,
            message='Failed to reach LLM backend',
        )
        yield  # pragma: no cover

    mock_llm_service.stream_messages = Mock(return_value=stream_outputs())

    payload = CreateMessageRequest(content='Fail immediately')

    emitted_events = []
    async for event in conversation_service.add_message_to_conversation_stream(
        session=async_session,
        user_id=test_user_id,
        conversation_id=conversation.id,
        payload=payload,
    ):
        emitted_events.append(event)

    assert len(emitted_events) == 1
    assert emitted_events[0].startswith('event: error')

    result = await async_session.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.sequence_number.asc())
    )
    persisted_messages = list(result.scalars().all())
    assert len(persisted_messages) == 1
    assert persisted_messages[0].role == 'user'


async def test_add_message_to_conversation_stream_errors_on_tool_calls(
    conversation_service,
    mock_llm_service,
    mock_context_assembly,
    async_session,
    test_user_id,
):
    """Streaming path emits terminal error when model returns tool calls."""
    conversation = Conversation(user_id=test_user_id, title='Streaming Tool')
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)

    mock_context_assembly.assemble_context.return_value = ContextAssemblyResult(
        messages=[{'role': 'user', 'content': 'Trigger tool call'}],
        used_summary=False,
        summary_id=None,
        fact_ids=[],
    )

    async def stream_outputs():
        yield StreamParserOutput(
            tool_calls=[
                ChatCompletionMessageToolCall(
                    id='call_1',
                    type='function',
                    function=ChatCompletionMessageToolCallFunction(
                        name='current_time', arguments='{}'
                    ),
                )
            ]
        )

    mock_llm_service.stream_messages = Mock(return_value=stream_outputs())

    payload = CreateMessageRequest(content='Trigger tool call')
    emitted_events = []
    async for event in conversation_service.add_message_to_conversation_stream(
        session=async_session,
        user_id=test_user_id,
        conversation_id=conversation.id,
        payload=payload,
    ):
        emitted_events.append(event)

    assert len(emitted_events) == 1
    assert emitted_events[0].startswith('event: error')
    error_payload = json.loads(emitted_events[0].split('data: ', 1)[1].strip())
    assert 'not yet supported' in error_payload['detail'].lower()

    result = await async_session.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.sequence_number.asc())
    )
    persisted_messages = list(result.scalars().all())
    assert len(persisted_messages) == 1
    assert persisted_messages[0].role == 'user'


async def test_add_message_to_conversation_stream_persists_partial_on_cancellation(
    conversation_service,
    mock_llm_service,
    mock_context_assembly,
    async_session,
    test_user_id,
):
    """Client cancellation persists assistant partial output in terminal error state."""
    conversation = Conversation(
        user_id=test_user_id, title='Streaming Cancellation'
    )
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)

    mock_context_assembly.assemble_context.return_value = ContextAssemblyResult(
        messages=[{'role': 'user', 'content': 'Trigger cancellation'}],
        used_summary=False,
        summary_id=None,
        fact_ids=[],
    )

    async def stream_outputs():
        yield StreamParserOutput(token='partial output')
        raise asyncio.CancelledError()

    mock_llm_service.stream_messages = Mock(return_value=stream_outputs())

    payload = CreateMessageRequest(content='Trigger cancellation')

    with pytest.raises(asyncio.CancelledError):
        async for _ in conversation_service.add_message_to_conversation_stream(
            session=async_session,
            user_id=test_user_id,
            conversation_id=conversation.id,
            payload=payload,
        ):
            pass

    result = await async_session.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.sequence_number.asc())
    )
    persisted_messages = list(result.scalars().all())
    assert len(persisted_messages) == 2
    assert persisted_messages[1].role == 'assistant'
    assert persisted_messages[1].content == 'partial output'
    assert 'interrupted' in (persisted_messages[1].error or '').lower()


async def test_create_conversation_with_message_stream_persists_lifecycle_success(
    conversation_service,
    mock_llm_service,
    mock_context_assembly,
    async_session,
    test_user_id,
):
    """New conversation stream persists user immediately and assistant on completion."""
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        ContextAssemblyResult(
            messages=[{'role': 'user', 'content': 'Start stream'}],
            used_summary=False,
            summary_id=None,
            fact_ids=[],
        )
    )

    async def stream_outputs():
        yield StreamParserOutput(thought='thinking...')
        yield StreamParserOutput(token='Hello')
        yield StreamParserOutput(
            token=' world',
            finish_reason='stop',
            usage=CompletionUsage(
                prompt_tokens=4,
                completion_tokens=2,
                total_tokens=6,
            ),
            model='test-model',
        )

    mock_llm_service.stream_messages = Mock(return_value=stream_outputs())

    payload = CreateConversationWithMessageRequest(content='Start stream')
    stream = conversation_service.create_conversation_with_message_stream(
        session=async_session,
        user_id=test_user_id,
        payload=payload,
    )
    first_event = await anext(stream)

    result = await async_session.execute(select(Conversation))
    conversations = list(result.scalars().all())
    assert len(conversations) == 1

    result = await async_session.execute(
        select(Message)
        .where(Message.conversation_id == conversations[0].id)
        .order_by(Message.sequence_number.asc())
    )
    in_flight_messages = list(result.scalars().all())
    assert len(in_flight_messages) == 1
    assert in_flight_messages[0].role == 'user'
    assert in_flight_messages[0].content == 'Start stream'

    remaining_events = []
    async for event in stream:
        remaining_events.append(event)

    all_events = [first_event] + remaining_events
    done_event = next(
        event for event in all_events if event.startswith('event: done')
    )
    done_payload = json.loads(done_event.split('data: ', 1)[1].strip())
    assert done_payload['conversation_id'] == str(conversations[0].id)
    assert done_payload['content'] == 'Hello world'
    assert done_payload['model'] == 'test-model'
    assert done_payload['annotations']['thought'] == 'thinking...'

    result = await async_session.execute(
        select(Message)
        .where(Message.conversation_id == conversations[0].id)
        .order_by(Message.sequence_number.asc())
    )
    persisted_messages = list(result.scalars().all())
    assert len(persisted_messages) == 2
    assert persisted_messages[1].role == 'assistant'
    assert persisted_messages[1].content == 'Hello world'
    assert persisted_messages[1].annotations['thought'] == 'thinking...'


async def test_create_conversation_with_message_stream_persists_error_with_partial_assistant(
    conversation_service,
    mock_llm_service,
    mock_context_assembly,
    async_session,
    test_user_id,
):
    """Interrupted new-conversation stream persists partial assistant in error state."""
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        ContextAssemblyResult(
            messages=[{'role': 'user', 'content': 'Start stream'}],
            used_summary=False,
            summary_id=None,
            fact_ids=[],
        )
    )

    async def stream_outputs():
        yield StreamParserOutput(token='partial output')
        raise LLMCompletionError(
            kind=LLMCompletionErrorKind.timeout,
            message='LLM request timed out',
        )

    mock_llm_service.stream_messages = Mock(return_value=stream_outputs())

    payload = CreateConversationWithMessageRequest(content='Start stream')
    emitted_events = []
    async for (
        event
    ) in conversation_service.create_conversation_with_message_stream(
        session=async_session,
        user_id=test_user_id,
        payload=payload,
    ):
        emitted_events.append(event)

    assert any(event.startswith('event: token') for event in emitted_events)
    assert any(event.startswith('event: error') for event in emitted_events)

    result = await async_session.execute(select(Conversation))
    conversations = list(result.scalars().all())
    assert len(conversations) == 1

    result = await async_session.execute(
        select(Message)
        .where(Message.conversation_id == conversations[0].id)
        .order_by(Message.sequence_number.asc())
    )
    persisted_messages = list(result.scalars().all())
    assert len(persisted_messages) == 2
    assert persisted_messages[1].role == 'assistant'
    assert persisted_messages[1].content == 'partial output'
    assert persisted_messages[1].annotations['failure']['stage'] == 'llm'


async def test_create_conversation_with_message_stream_skips_assistant_persistence_without_output(
    conversation_service,
    mock_llm_service,
    mock_context_assembly,
    async_session,
    test_user_id,
):
    """If new-conversation stream fails before output, only user message is persisted."""
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        ContextAssemblyResult(
            messages=[{'role': 'user', 'content': 'Start stream'}],
            used_summary=False,
            summary_id=None,
            fact_ids=[],
        )
    )

    async def stream_outputs():
        raise LLMCompletionError(
            kind=LLMCompletionErrorKind.unreachable,
            message='Failed to reach LLM backend',
        )
        yield  # pragma: no cover

    mock_llm_service.stream_messages = Mock(return_value=stream_outputs())

    payload = CreateConversationWithMessageRequest(content='Start stream')
    emitted_events = []
    async for (
        event
    ) in conversation_service.create_conversation_with_message_stream(
        session=async_session,
        user_id=test_user_id,
        payload=payload,
    ):
        emitted_events.append(event)

    assert len(emitted_events) == 1
    assert emitted_events[0].startswith('event: error')

    result = await async_session.execute(select(Conversation))
    conversations = list(result.scalars().all())
    assert len(conversations) == 1

    result = await async_session.execute(
        select(Message)
        .where(Message.conversation_id == conversations[0].id)
        .order_by(Message.sequence_number.asc())
    )
    persisted_messages = list(result.scalars().all())
    assert len(persisted_messages) == 1
    assert persisted_messages[0].role == 'user'
