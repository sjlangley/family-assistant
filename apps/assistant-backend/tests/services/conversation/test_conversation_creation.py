"""Tests for ConversationService conversation creation operations."""

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from assistant.models.conversation import (
    ConversationWithMessagesResponse,
    CreateConversationWithMessageRequest,
)
from assistant.models.conversation_sql import Conversation, Message
from assistant.models.llm import (
    LLMCompletionError,
    LLMCompletionErrorKind,
    LLMCompletionResult,
)


@pytest.mark.asyncio
async def test_create_conversation_with_message_success(
    conversation_service,
    mock_llm_service,
    mock_context_assembly,
    async_session,
    test_user_id,
    valid_request,
    mock_llm_response,
    mock_context_result,
):
    """It creates a conversation with user and assistant messages."""
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        mock_context_result
    )
    mock_llm_service.complete_messages.return_value = mock_llm_response

    result = await conversation_service.create_conversation_with_message(
        session=async_session,
        user_id=test_user_id,
        payload=valid_request,
    )

    # Verify the response structure
    assert isinstance(result, ConversationWithMessagesResponse)
    assert result.conversation.title == 'Hello, how are you?'
    assert result.user_message.content == 'Hello, how are you?'
    assert result.user_message.role == 'user'
    assert result.user_message.sequence_number == 1
    assert result.assistant_message.content == 'I am doing well, thank you!'
    assert result.assistant_message.role == 'assistant'
    assert result.assistant_message.sequence_number == 2

    # Verify context assembly was called
    mock_context_assembly.assemble_context_new_conversation.assert_called_once()

    # Verify LLM service was called correctly
    mock_llm_service.complete_messages.assert_called_once()
    call_kwargs = mock_llm_service.complete_messages.call_args.kwargs
    assert call_kwargs['model'] is not None
    assert call_kwargs['temperature'] == 0.7
    assert call_kwargs['max_tokens'] == 512
    # Messages should have system message + context assembly messages
    assert len(call_kwargs['messages']) == 2  # system + user
    assert call_kwargs['messages'][0]['role'] == 'system'
    assert call_kwargs['messages'][1] == mock_context_result.messages[0]

    # Verify data was saved to database
    # Re-query to ensure persistence

    stmt = select(Conversation).where(Conversation.id == result.conversation.id)
    db_result = await async_session.execute(stmt)
    db_conversation = db_result.scalar_one()
    assert db_conversation.user_id == test_user_id
    assert db_conversation.title == 'Hello, how are you?'

    stmt = (
        select(Message)
        .where(Message.conversation_id == db_conversation.id)
        .order_by(Message.sequence_number.asc())
    )
    db_result = await async_session.execute(stmt)
    db_messages = list(db_result.scalars().all())
    assert len(db_messages) == 2
    assert db_messages[0].role == 'user'
    assert db_messages[1].role == 'assistant'


@pytest.mark.asyncio
async def test_create_conversation_with_message_empty_content(
    conversation_service,
    async_session,
    test_user_id,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when content is empty."""
    request = CreateConversationWithMessageRequest(
        content='   ',  # Only whitespace
        temperature=0.7,
        max_tokens=512,
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.create_conversation_with_message(
            session=async_session,
            user_id=test_user_id,
            payload=request,
        )

    assert exc_info.value.status_code == 400
    assert 'empty' in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_create_conversation_with_message_llm_timeout(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    valid_request,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when LLM times out."""
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        mock_context_result
    )
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.timeout,
        message='LLM request timed out',
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.create_conversation_with_message(
            session=async_session,
            user_id=test_user_id,
            payload=valid_request,
        )

    assert exc_info.value.status_code == 504
    assert 'timed out' in exc_info.value.detail.lower()

    stmt = select(Conversation)
    result = await async_session.execute(stmt)
    conversations = list(result.scalars().all())
    # We save the conversation anyway.
    assert len(conversations) == 1


@pytest.mark.asyncio
async def test_create_conversation_with_message_llm_connection_error(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    valid_request,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when LLM connection fails."""
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        mock_context_result
    )
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.unreachable,
        message='Failed to reach LLM backend',
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.create_conversation_with_message(
            session=async_session,
            user_id=test_user_id,
            payload=valid_request,
        )

    assert exc_info.value.status_code == 502
    assert 'failed to reach' in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_create_conversation_with_message_llm_http_error(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    valid_request,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when LLM returns HTTP error."""
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        mock_context_result
    )
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.backend_error,
        message='LLM backend returned an error',
        backend_status_code=500,
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.create_conversation_with_message(
            session=async_session,
            user_id=test_user_id,
            payload=valid_request,
        )

    assert exc_info.value.status_code == 502
    assert 'error' in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_create_conversation_with_message_invalid_llm_response(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    valid_request,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when LLM response is invalid."""
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        mock_context_result
    )
    # Return an invalid response structure
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.invalid_response,
        message='LLM response has unexpected response shape',
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.create_conversation_with_message(
            session=async_session,
            user_id=test_user_id,
            payload=valid_request,
        )

    assert exc_info.value.status_code == 502
    assert 'unexpected response' in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_create_conversation_with_message_empty_choices(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    valid_request,
    mock_context_assembly,
    mock_context_result,
):
    """It raises HTTPException when LLM returns no choices."""
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        mock_context_result
    )
    mock_llm_service.complete_messages.side_effect = LLMCompletionError(
        kind=LLMCompletionErrorKind.invalid_response,
        message='LLM backend did not return any choices',
    )

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.create_conversation_with_message(
            session=async_session,
            user_id=test_user_id,
            payload=valid_request,
        )

    assert exc_info.value.status_code == 502
    assert 'did not return any choices' in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_create_conversation_with_message_long_content_title(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    mock_llm_response,
    mock_context_assembly,
    mock_context_result,
):
    """It truncates long messages for conversation title."""
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        mock_context_result
    )
    long_content = 'A' * 100  # More than 60 characters
    request = CreateConversationWithMessageRequest(
        content=long_content,
        temperature=0.7,
        max_tokens=512,
    )
    mock_llm_service.complete_messages.return_value = mock_llm_response

    result = await conversation_service.create_conversation_with_message(
        session=async_session,
        user_id=test_user_id,
        payload=request,
    )

    # Title should be truncated to 60 characters
    assert len(result.conversation.title) == 60
    assert result.conversation.title == 'A' * 60


@pytest.mark.asyncio
async def test_create_conversation_with_message_empty_assistant_content(
    conversation_service,
    mock_llm_service,
    async_session,
    test_user_id,
    valid_request,
    mock_context_assembly,
    mock_context_result,
):
    """It handles empty assistant content gracefully."""
    mock_context_assembly.assemble_context_new_conversation.return_value = (
        mock_context_result
    )
    mock_llm_service.complete_messages.return_value = LLMCompletionResult(
        content='',
        model='llama3.2',
        prompt_tokens=10,
        completion_tokens=0,
        total_tokens=10,
        tool_calls=None,
        finish_reason='stop',
    )

    result = await conversation_service.create_conversation_with_message(
        session=async_session,
        user_id=test_user_id,
        payload=valid_request,
    )

    # Should handle empty content by replacing with placeholder
    assert (
        result.assistant_message.content
        == 'Unable to generate a response. Please try again.'
    )
