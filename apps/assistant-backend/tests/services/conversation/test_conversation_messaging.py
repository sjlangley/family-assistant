"""Tests for ConversationService message addition operations."""

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from assistant.models.conversation import CreateMessageRequest
from assistant.models.conversation_sql import Conversation, Message
from assistant.models.llm import (
    LLMCompletionError,
    LLMCompletionErrorKind,
)


@pytest.mark.asyncio
async def test_add_message_to_conversation_success(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    mock_llm_response,
    mock_context_assembly,
    mock_context_result,
):
    """It adds a message to an existing conversation."""
    mock_context_assembly.assemble_context.return_value = mock_context_result
    # Create a conversation with initial messages
    conversation = Conversation(
        user_id=test_user_id,
        title='Existing Conversation',
    )
    async_session.add(conversation)
    await async_session.flush()

    message1 = Message(
        conversation_id=conversation.id,
        role='user',
        content='Hello',
        sequence_number=1,
    )
    async_session.add(message1)

    message2 = Message(
        conversation_id=conversation.id,
        role='assistant',
        content='Hi there!',
        sequence_number=2,
    )
    async_session.add(message2)

    await async_session.commit()
    await async_session.refresh(conversation)

    original_updated_at = conversation.updated_at

    # Add a new message
    payload = CreateMessageRequest(
        content='How are you?',
        temperature=0.7,
        max_tokens=512,
    )
    mock_llm_service.complete_messages.return_value = mock_llm_response

    result = await conversation_service.add_message_to_conversation(
        session=async_session,
        user_id=test_user_id,
        conversation_id=conversation.id,
        payload=payload,
    )

    # Verify the response
    assert result.user_message.content == 'How are you?'
    assert result.user_message.sequence_number == 3
    assert result.user_message.role == 'user'
    assert result.assistant_message.content == 'I am doing well, thank you!'
    assert result.assistant_message.sequence_number == 4
    assert result.assistant_message.role == 'assistant'

    # Verify LLM was called with all messages
    mock_llm_service.complete_messages.assert_called_once()
    call_kwargs = mock_llm_service.complete_messages.call_args.kwargs
    # Should have system message + context assembly messages
    assert len(call_kwargs['messages']) == 2  # system + user
    assert call_kwargs['messages'][0]['role'] == 'system'
    assert call_kwargs['messages'][1] == mock_context_result.messages[0]

    # Verify messages were saved to database
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.sequence_number.asc())
    )
    db_result = await async_session.execute(stmt)
    all_messages = list(db_result.scalars().all())
    assert len(all_messages) == 4
    assert all_messages[2].content == 'How are you?'
    assert all_messages[3].content == 'I am doing well, thank you!'

    # Verify updated_at was updated
    await async_session.refresh(conversation)
    assert conversation.updated_at >= original_updated_at


@pytest.mark.asyncio
async def test_add_message_to_conversation_empty_content(
    conversation_service,
    async_session,
    test_user_id,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when content is empty."""

    conversation = Conversation(
        user_id=test_user_id,
        title='Test',
    )
    async_session.add(conversation)
    await async_session.commit()

    payload = CreateMessageRequest(
        content='   ',  # Only whitespace
        temperature=0.7,
        max_tokens=512,
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.add_message_to_conversation(
            session=async_session,
            user_id=test_user_id,
            conversation_id=conversation.id,
            payload=payload,
        )

    assert exc_info.value.status_code == 400
    assert 'empty' in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_add_message_to_conversation_not_found(
    conversation_service,
    async_session,
    test_user_id,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when conversation doesn't exist."""

    non_existent_id = uuid.uuid4()
    payload = CreateMessageRequest(
        content='Hello',
        temperature=0.7,
        max_tokens=512,
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.add_message_to_conversation(
            session=async_session,
            user_id=test_user_id,
            conversation_id=non_existent_id,
            payload=payload,
        )

    assert exc_info.value.status_code == 404
    assert 'not found' in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_add_message_to_conversation_wrong_user(
    conversation_service,
    async_session,
    test_user_id,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when user doesn't own the conversation."""

    other_user_id = str(uuid.uuid4())

    conversation = Conversation(
        user_id=other_user_id,
        title='Other User Conversation',
    )
    async_session.add(conversation)
    await async_session.commit()

    payload = CreateMessageRequest(
        content='Hello',
        temperature=0.7,
        max_tokens=512,
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.add_message_to_conversation(
            session=async_session,
            user_id=test_user_id,
            conversation_id=conversation.id,
            payload=payload,
        )

    assert exc_info.value.status_code == 404
    assert 'not found' in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_add_message_to_conversation_with_no_existing_messages(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    mock_llm_response,
    mock_context_assembly,
    mock_context_result,
):
    """It handles adding a message to a conversation with no messages."""
    mock_context_assembly.assemble_context.return_value = mock_context_result

    conversation = Conversation(
        user_id=test_user_id,
        title='Empty Conversation',
    )
    async_session.add(conversation)
    await async_session.commit()

    payload = CreateMessageRequest(
        content='First message',
        temperature=0.7,
        max_tokens=512,
    )
    mock_llm_service.complete_messages.return_value = mock_llm_response

    result = await conversation_service.add_message_to_conversation(
        session=async_session,
        user_id=test_user_id,
        conversation_id=conversation.id,
        payload=payload,
    )

    # Should start sequence numbers at 1
    assert result.user_message.sequence_number == 1
    assert result.assistant_message.sequence_number == 2


@pytest.mark.asyncio
async def test_add_message_to_conversation_llm_timeout(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when LLM times out."""
    mock_context_assembly.assemble_context.return_value = mock_context_result

    conversation = Conversation(
        user_id=test_user_id,
        title='Test',
    )
    async_session.add(conversation)
    await async_session.commit()

    payload = CreateMessageRequest(
        content='Hello',
        temperature=0.7,
        max_tokens=512,
    )
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.timeout,
        message='LLM request timed out',
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.add_message_to_conversation(
            session=async_session,
            user_id=test_user_id,
            conversation_id=conversation.id,
            payload=payload,
        )

    assert exc_info.value.status_code == 504
    assert 'timed out' in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_add_message_to_conversation_llm_connection_error(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when LLM connection fails."""
    mock_context_assembly.assemble_context.return_value = mock_context_result

    conversation = Conversation(
        user_id=test_user_id,
        title='Test',
    )
    async_session.add(conversation)
    await async_session.commit()

    payload = CreateMessageRequest(
        content='Hello',
        temperature=0.7,
        max_tokens=512,
    )
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.unreachable,
        message='Failed to reach LLM backend',
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.add_message_to_conversation(
            session=async_session,
            user_id=test_user_id,
            conversation_id=conversation.id,
            payload=payload,
        )

    assert exc_info.value.status_code == 502
    assert 'failed to reach' in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_add_message_to_conversation_llm_http_error(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when LLM returns HTTP error."""
    mock_context_assembly.assemble_context.return_value = mock_context_result

    conversation = Conversation(
        user_id=test_user_id,
        title='Test',
    )
    async_session.add(conversation)
    await async_session.commit()

    payload = CreateMessageRequest(
        content='Hello',
        temperature=0.7,
        max_tokens=512,
    )
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.backend_error,
        message='LLM backend returned an error',
        backend_status_code=500,
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.add_message_to_conversation(
            session=async_session,
            user_id=test_user_id,
            conversation_id=conversation.id,
            payload=payload,
        )

    assert exc_info.value.status_code == 502
    assert 'error' in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_add_message_to_conversation_invalid_llm_response(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when LLM response is invalid."""
    mock_context_assembly.assemble_context.return_value = mock_context_result

    conversation = Conversation(
        user_id=test_user_id,
        title='Test',
    )
    async_session.add(conversation)
    await async_session.commit()

    payload = CreateMessageRequest(
        content='Hello',
        temperature=0.7,
        max_tokens=512,
    )
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.invalid_response,
        message='LLM response has unexpected response shape',
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.add_message_to_conversation(
            session=async_session,
            user_id=test_user_id,
            conversation_id=conversation.id,
            payload=payload,
        )

    assert exc_info.value.status_code == 502
    assert 'unexpected response' in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_add_message_to_conversation_empty_llm_choices(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when LLM returns no choices."""
    mock_context_assembly.assemble_context.return_value = mock_context_result

    conversation = Conversation(
        user_id=test_user_id,
        title='Test',
    )
    async_session.add(conversation)
    await async_session.commit()

    payload = CreateMessageRequest(
        content='Hello',
        temperature=0.7,
        max_tokens=512,
    )
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.invalid_response,
        message='LLM backend did not return any choices',
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.add_message_to_conversation(
            session=async_session,
            user_id=test_user_id,
            conversation_id=conversation.id,
            payload=payload,
        )

    assert exc_info.value.status_code == 502
    assert 'did not return any choices' in exc_info.value.detail.lower()
