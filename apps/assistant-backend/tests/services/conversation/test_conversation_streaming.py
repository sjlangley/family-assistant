"""Tests for ConversationService streaming operations."""

import asyncio
from datetime import datetime, timezone
import json
from unittest.mock import Mock

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
from assistant.models.tool import ToolExecutionResult, ToolExecutionStatus
from assistant.services.context_assembly import ContextAssemblyResult


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_add_message_to_conversation_stream_errors_on_tool_calls(
    conversation_service,
    mock_llm_service,
    mock_context_assembly,
    mock_tool_service,
    async_session,
    test_user_id,
):
    """Streaming path executes tool calls and continues the assistant turn."""
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

    async def first_round():
        yield StreamParserOutput(token='Checking ')
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

    async def second_round():
        yield StreamParserOutput(
            token='the current time.',
            finish_reason='stop',
            usage=CompletionUsage(
                prompt_tokens=8,
                completion_tokens=5,
                total_tokens=13,
            ),
            model='test-model',
        )

    mock_llm_service.stream_messages = Mock(
        side_effect=[first_round(), second_round()]
    )
    mock_tool_service.execute_tool.return_value = ToolExecutionResult(
        tool_name='current_time',
        status=ToolExecutionStatus.SUCCESS,
        tool_call={
            'name': 'current_time',
            'arguments': {},
            'started_at': datetime.now(timezone.utc),
            'finished_at': datetime.now(timezone.utc),
            'status': ToolExecutionStatus.SUCCESS,
        },
        llm_context='The current time is 10:00.',
    )

    payload = CreateMessageRequest(content='Trigger tool call')
    emitted_events = []
    async for event in conversation_service.add_message_to_conversation_stream(
        session=async_session,
        user_id=test_user_id,
        conversation_id=conversation.id,
        payload=payload,
    ):
        emitted_events.append(event)

    assert any(event.startswith('event: token') for event in emitted_events)
    tool_events = [
        json.loads(event.split('data: ', 1)[1].strip())
        for event in emitted_events
        if event.startswith('event: tool_call')
    ]
    assert [tool_event['status'] for tool_event in tool_events] == [
        'requested',
        'running',
        'completed',
    ]
    assert tool_events[-1]['name'] == 'current_time'
    done_event = next(
        event for event in emitted_events if event.startswith('event: done')
    )
    done_payload = json.loads(done_event.split('data: ', 1)[1].strip())
    assert done_payload['content'] == 'Checking the current time.'
    assert done_payload['annotations']['tools'] == [
        {'id': None, 'name': 'current_time', 'status': 'completed'}
    ]

    result = await async_session.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.sequence_number.asc())
    )
    persisted_messages = list(result.scalars().all())
    assert len(persisted_messages) == 2
    assert persisted_messages[1].role == 'assistant'
    assert persisted_messages[1].content == 'Checking the current time.'
    assert persisted_messages[1].annotations['tools'] == [
        {'id': None, 'name': 'current_time', 'status': 'completed'}
    ]


@pytest.mark.asyncio
async def test_add_message_to_conversation_stream_emits_failed_tool_lifecycle(
    conversation_service,
    mock_llm_service,
    mock_context_assembly,
    mock_tool_service,
    async_session,
    test_user_id,
):
    """Streaming path persists a terminal tool error with tool lifecycle metadata."""
    conversation = Conversation(
        user_id=test_user_id, title='Streaming Tool Failure'
    )
    async_session.add(conversation)
    await async_session.commit()
    await async_session.refresh(conversation)

    mock_context_assembly.assemble_context.return_value = ContextAssemblyResult(
        messages=[{'role': 'user', 'content': 'Trigger tool failure'}],
        used_summary=False,
        summary_id=None,
        fact_ids=[],
    )

    async def stream_outputs():
        yield StreamParserOutput(token='Trying ')
        yield StreamParserOutput(
            tool_calls=[
                ChatCompletionMessageToolCall(
                    id='call_fail',
                    type='function',
                    function=ChatCompletionMessageToolCallFunction(
                        name='current_time', arguments='{}'
                    ),
                )
            ]
        )

    mock_llm_service.stream_messages = Mock(return_value=stream_outputs())
    mock_tool_service.execute_tool.side_effect = RuntimeError('tool exploded')

    payload = CreateMessageRequest(content='Trigger tool failure')
    emitted_events = []
    async for event in conversation_service.add_message_to_conversation_stream(
        session=async_session,
        user_id=test_user_id,
        conversation_id=conversation.id,
        payload=payload,
    ):
        emitted_events.append(event)

    tool_events = [
        json.loads(event.split('data: ', 1)[1].strip())
        for event in emitted_events
        if event.startswith('event: tool_call')
    ]
    assert [tool_event['status'] for tool_event in tool_events] == [
        'requested',
        'running',
        'failed',
    ]
    assert tool_events[-1]['detail'] == 'tool exploded'

    error_event = next(
        event for event in emitted_events if event.startswith('event: error')
    )
    error_payload = json.loads(error_event.split('data: ', 1)[1].strip())
    assert 'tool exploded' in error_payload['detail'].lower()

    result = await async_session.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.sequence_number.asc())
    )
    persisted_messages = list(result.scalars().all())
    assert len(persisted_messages) == 2
    assert persisted_messages[1].role == 'assistant'
    assert persisted_messages[1].content == 'Trying '
    assert persisted_messages[1].annotations['failure']['stage'] == 'tool'


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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
