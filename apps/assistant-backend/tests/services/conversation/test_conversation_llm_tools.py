"""Tests for ConversationService LLM and tool calling operations."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from assistant.models.conversation import CreateMessageRequest
from assistant.models.conversation_sql import Conversation, Message
from assistant.models.llm import (
    ChatCompletionMessageToolCall,
    ChatCompletionMessageToolCallFunction,
    LLMCompletionResult,
)
from assistant.models.tool import (
    ToolExecutionResult,
    ToolExecutionStatus,
)
from assistant.services.tools.errors import UnsupportedToolError


@pytest.fixture
def mock_tool_result():
    """Create a mock tool execution result."""
    return ToolExecutionResult(
        tool_name='test_tool',
        status=ToolExecutionStatus.SUCCESS,
        tool_call={
            'name': 'test_tool',
            'arguments': {'query': 'test'},
            'started_at': datetime.now(timezone.utc),
            'finished_at': datetime.now(timezone.utc),
            'status': ToolExecutionStatus.SUCCESS,
        },
        llm_context='Tool execution successful',
    )


@pytest.fixture
def llm_response_with_tool_call():
    """Create an LLM response with a tool call."""
    tool_call = ChatCompletionMessageToolCall(
        id='call_123',
        type='function',
        function=ChatCompletionMessageToolCallFunction(
            name='test_tool',
            arguments='{"query": "test"}',
        ),
    )
    return LLMCompletionResult(
        content='I will search for that information.',
        model='llama3.2',
        prompt_tokens=10,
        completion_tokens=15,
        total_tokens=25,
        tool_calls=[tool_call],
        finish_reason='tool_calls',
    )


@pytest.fixture
def llm_response_with_multiple_tool_calls():
    """Create an LLM response with multiple tool calls."""
    tool_calls = [
        ChatCompletionMessageToolCall(
            id='call_1',
            type='function',
            function=ChatCompletionMessageToolCallFunction(
                name='search_tool',
                arguments='{"query": "python"}',
            ),
        ),
        ChatCompletionMessageToolCall(
            id='call_2',
            type='function',
            function=ChatCompletionMessageToolCallFunction(
                name='fetch_tool',
                arguments='{"url": "https://example.com"}',
            ),
        ),
    ]
    return LLMCompletionResult(
        content='I will search and fetch information.',
        model='llama3.2',
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        tool_calls=tool_calls,
        finish_reason='tool_calls',
    )


@pytest.mark.asyncio
async def test_call_llm_chat_completion_single_tool_call(
    conversation_service,
    mock_llm_service,
    mock_tool_service,
    llm_response_with_tool_call,
    mock_tool_result,
):
    """It executes a single tool call and returns final assistant content."""
    # First call returns tool call, second call returns content
    final_response = LLMCompletionResult(
        content='Here is the search result.',
        model='llama3.2',
        prompt_tokens=20,
        completion_tokens=25,
        total_tokens=45,
        tool_calls=None,
        finish_reason='stop',
    )

    mock_llm_service.complete_messages.side_effect = [
        llm_response_with_tool_call,
        final_response,
    ]
    mock_tool_service.execute_tool.return_value = mock_tool_result
    mock_tool_service.get_available_tools.return_value = []

    result = await conversation_service._call_llm_chat_completion(
        messages=[{'role': 'user', 'content': 'Search for python'}],
        temperature=0.7,
        max_tokens=512,
    )

    # Verify final content is returned
    assert result.content == 'Here is the search result.'
    assert result.error is None

    # Verify LLM was called twice (initial + follow-up)
    assert mock_llm_service.complete_messages.call_count == 2

    # Verify tool was executed
    mock_tool_service.execute_tool.assert_called_once_with(
        name='test_tool',
        arguments={'query': 'test'},
    )


@pytest.mark.asyncio
async def test_call_llm_chat_completion_multiple_tool_calls_same_round(
    conversation_service,
    mock_llm_service,
    mock_tool_service,
    llm_response_with_multiple_tool_calls,
    mock_tool_result,
):
    """It executes multiple tool calls in the same round."""
    final_response = LLMCompletionResult(
        content='Here are the results from both tools.',
        model='llama3.2',
        prompt_tokens=30,
        completion_tokens=35,
        total_tokens=65,
        tool_calls=None,
        finish_reason='stop',
    )

    mock_llm_service.complete_messages.side_effect = [
        llm_response_with_multiple_tool_calls,
        final_response,
    ]
    mock_tool_service.execute_tool.return_value = mock_tool_result
    mock_tool_service.get_available_tools.return_value = []

    result = await conversation_service._call_llm_chat_completion(
        messages=[{'role': 'user', 'content': 'Search and fetch'}],
        temperature=0.7,
        max_tokens=512,
    )

    assert result.content == 'Here are the results from both tools.'
    assert result.error is None

    # Both tools should have been executed
    assert mock_tool_service.execute_tool.call_count == 2


@pytest.mark.asyncio
async def test_call_llm_chat_completion_multiple_rounds(
    conversation_service,
    mock_llm_service,
    mock_tool_service,
    llm_response_with_tool_call,
    mock_tool_result,
):
    """It handles multiple rounds of tool calling."""
    # Create second tool call response
    second_tool_response = LLMCompletionResult(
        content='I will also search for related info.',
        model='llama3.2',
        prompt_tokens=30,
        completion_tokens=15,
        total_tokens=45,
        tool_calls=[
            ChatCompletionMessageToolCall(
                id='call_456',
                type='function',
                function=ChatCompletionMessageToolCallFunction(
                    name='test_tool',
                    arguments='{"query": "related"}',
                ),
            ),
        ],
        finish_reason='tool_calls',
    )

    final_response = LLMCompletionResult(
        content='Here are all the results.',
        model='llama3.2',
        prompt_tokens=50,
        completion_tokens=30,
        total_tokens=80,
        tool_calls=None,
        finish_reason='stop',
    )

    mock_llm_service.complete_messages.side_effect = [
        llm_response_with_tool_call,
        second_tool_response,
        final_response,
    ]
    mock_tool_service.execute_tool.return_value = mock_tool_result
    mock_tool_service.get_available_tools.return_value = []

    result = await conversation_service._call_llm_chat_completion(
        messages=[{'role': 'user', 'content': 'Search for info'}],
        temperature=0.7,
        max_tokens=512,
    )

    assert result.content == 'Here are all the results.'
    assert result.error is None

    # LLM called 3 times and tool executed 2 times
    assert mock_llm_service.complete_messages.call_count == 3
    assert mock_tool_service.execute_tool.call_count == 2


@pytest.mark.asyncio
async def test_call_llm_chat_completion_tool_execution_error(
    conversation_service,
    mock_llm_service,
    mock_tool_service,
    llm_response_with_tool_call,
):
    """It returns error result when tool execution fails."""
    mock_llm_service.complete_messages.return_value = (
        llm_response_with_tool_call
    )
    mock_tool_service.get_available_tools.return_value = []
    mock_tool_service.execute_tool.side_effect = UnsupportedToolError(
        'test_tool'
    )

    result = await conversation_service._call_llm_chat_completion(
        messages=[{'role': 'user', 'content': 'Search'}],
        temperature=0.7,
        max_tokens=512,
    )

    assert result.error is not None
    assert 'unsupported tool' in str(result.error.message).lower()


@pytest.mark.asyncio
async def test_call_llm_chat_completion_max_rounds_exceeded(
    conversation_service,
    mock_llm_service,
    mock_tool_service,
):
    """It returns error result when maximum tool rounds are exceeded."""
    tool_call_response = LLMCompletionResult(
        content='I will search.',
        model='llama3.2',
        prompt_tokens=10,
        completion_tokens=10,
        total_tokens=20,
        tool_calls=[
            ChatCompletionMessageToolCall(
                id='call_123',
                type='function',
                function=ChatCompletionMessageToolCallFunction(
                    name='test_tool',
                    arguments='{"query": "test"}',
                ),
            ),
        ],
        finish_reason='tool_calls',
    )

    # Always return tool calls to trigger max rounds
    mock_llm_service.complete_messages.return_value = tool_call_response
    mock_tool_service.get_available_tools.return_value = []

    mock_tool_service.execute_tool.return_value = ToolExecutionResult(
        tool_name='test_tool',
        status=ToolExecutionStatus.SUCCESS,
        tool_call={
            'name': 'test_tool',
            'arguments': {},
            'started_at': datetime.now(timezone.utc),
            'finished_at': datetime.now(timezone.utc),
            'status': ToolExecutionStatus.SUCCESS,
        },
        llm_context='Result',
    )

    result = await conversation_service._call_llm_chat_completion(
        messages=[{'role': 'user', 'content': 'Search'}],
        temperature=0.7,
        max_tokens=512,
    )

    assert result.error is not None
    assert 'exceeded maximum tool rounds' in result.error.message.lower()


@pytest.mark.asyncio
async def test_call_llm_chat_completion_tool_messages_appended_correctly(
    conversation_service,
    mock_llm_service,
    mock_tool_service,
    llm_response_with_tool_call,
    mock_tool_result,
):
    """It appends tool results correctly to message history."""
    final_response = LLMCompletionResult(
        content='Final answer.',
        model='llama3.2',
        prompt_tokens=30,
        completion_tokens=15,
        total_tokens=45,
        tool_calls=None,
        finish_reason='stop',
    )

    mock_llm_service.complete_messages.side_effect = [
        llm_response_with_tool_call,
        final_response,
    ]
    mock_tool_service.execute_tool.return_value = mock_tool_result
    mock_tool_service.get_available_tools.return_value = []

    await conversation_service._call_llm_chat_completion(
        messages=[{'role': 'user', 'content': 'Test'}],
        temperature=0.7,
        max_tokens=512,
    )

    # Verify second LLM call includes tool result message
    second_call_args = mock_llm_service.complete_messages.call_args_list[1]
    messages = second_call_args.kwargs['messages']

    # Should have system message + user message + assistant message with tool_calls + tool result message
    assert len(messages) >= 4
    # Last message should be tool result
    tool_message = messages[-1]
    assert tool_message['role'] == 'tool'
    assert tool_message['tool_call_id'] == 'call_123'
    assert tool_message['content'] == mock_tool_result.llm_context


@pytest.mark.asyncio
async def test_call_llm_chat_completion_with_json_tool_arguments(
    conversation_service,
    mock_llm_service,
    mock_tool_service,
    mock_tool_result,
):
    """It correctly parses JSON arguments from tool calls."""
    # Tool call with complex JSON arguments
    tool_call_with_json = ChatCompletionMessageToolCall(
        id='call_json',
        type='function',
        function=ChatCompletionMessageToolCallFunction(
            name='complex_tool',
            arguments='{"query": "test", "filters": {"type": "article", "limit": 10}, "sort": "date"}',
        ),
    )

    tool_response = LLMCompletionResult(
        content='I will execute the complex tool.',
        model='llama3.2',
        prompt_tokens=10,
        completion_tokens=12,
        total_tokens=22,
        tool_calls=[tool_call_with_json],
        finish_reason='tool_calls',
    )

    final_response = LLMCompletionResult(
        content='Here are the results.',
        model='llama3.2',
        prompt_tokens=30,
        completion_tokens=10,
        total_tokens=40,
        tool_calls=None,
        finish_reason='stop',
    )

    mock_llm_service.complete_messages.side_effect = [
        tool_response,
        final_response,
    ]
    mock_tool_service.execute_tool.return_value = mock_tool_result
    mock_tool_service.get_available_tools.return_value = []

    result = await conversation_service._call_llm_chat_completion(
        messages=[{'role': 'user', 'content': 'Complex search'}],
        temperature=0.7,
        max_tokens=512,
    )

    assert result.content == 'Here are the results.'
    assert result.error is None

    # Verify tool was called with parsed JSON arguments
    mock_tool_service.execute_tool.assert_called_once_with(
        name='complex_tool',
        arguments={
            'query': 'test',
            'filters': {'type': 'article', 'limit': 10},
            'sort': 'date',
        },
    )


@pytest.mark.asyncio
async def test_add_message_with_tool_call_flow(
    conversation_service,
    mock_llm_service,
    mock_tool_service,
    async_session,
    test_user_id,
    mock_context_assembly,
    mock_context_result,
    mock_tool_result,
):
    """It handles complete message addition with tool calling."""
    # Create a conversation
    conversation = Conversation(
        user_id=test_user_id,
        title='Tool Calling Conversation',
    )
    async_session.add(conversation)
    await async_session.flush()

    user_message = Message(
        conversation_id=conversation.id,
        role='user',
        content='Initial message',
        sequence_number=1,
    )
    async_session.add(user_message)

    assistant_message = Message(
        conversation_id=conversation.id,
        role='assistant',
        content='Initial response',
        sequence_number=2,
    )
    async_session.add(assistant_message)
    await async_session.commit()

    # Set up mock responses for tool calling
    tool_call_response = LLMCompletionResult(
        content='I will search for that.',
        model='llama3.2',
        prompt_tokens=15,
        completion_tokens=10,
        total_tokens=25,
        tool_calls=[
            ChatCompletionMessageToolCall(
                id='call_abc',
                type='function',
                function=ChatCompletionMessageToolCallFunction(
                    name='search_tool',
                    arguments='{"q": "python"}',
                ),
            ),
        ],
        finish_reason='tool_calls',
    )

    final_response = LLMCompletionResult(
        content='Python is a programming language.',
        model='llama3.2',
        prompt_tokens=30,
        completion_tokens=20,
        total_tokens=50,
        tool_calls=None,
        finish_reason='stop',
    )

    mock_context_assembly.assemble_context.return_value = mock_context_result
    mock_llm_service.complete_messages.side_effect = [
        tool_call_response,
        final_response,
    ]
    mock_tool_service.get_available_tools.return_value = []
    mock_tool_service.execute_tool.return_value = mock_tool_result

    # Add new message
    payload = CreateMessageRequest(
        content='What is Python?',
        temperature=0.7,
        max_tokens=512,
    )

    result = await conversation_service.add_message_to_conversation(
        session=async_session,
        user_id=test_user_id,
        conversation_id=conversation.id,
        payload=payload,
    )

    # Verify final assistant response is from after tool execution
    assert (
        result.assistant_message.content == 'Python is a programming language.'
    )

    # Verify conversation was updated
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.sequence_number.asc())
    )
    db_result = await async_session.execute(stmt)
    messages = list(db_result.scalars().all())

    # Should have initial messages + new user message + final assistant response
    assert len(messages) == 4
    assert messages[2].content == 'What is Python?'
    assert messages[3].content == 'Python is a programming language.'


@pytest.mark.asyncio
async def test_call_llm_chat_completion_malformed_json_arguments(
    conversation_service,
    mock_llm_service,
    mock_tool_service,
):
    """It returns error result when tool arguments are malformed JSON."""
    # Tool call with invalid JSON
    malformed_tool_call = ChatCompletionMessageToolCall(
        id='call_bad',
        type='function',
        function=ChatCompletionMessageToolCallFunction(
            name='broken_tool',
            arguments='{invalid json}',  # Not valid JSON
        ),
    )

    tool_response = LLMCompletionResult(
        content='I will execute the tool.',
        model='llama3.2',
        prompt_tokens=10,
        completion_tokens=12,
        total_tokens=22,
        tool_calls=[malformed_tool_call],
        finish_reason='tool_calls',
    )

    mock_llm_service.complete_messages.return_value = tool_response
    mock_tool_service.get_available_tools.return_value = []

    result = await conversation_service._call_llm_chat_completion(
        messages=[{'role': 'user', 'content': 'Test'}],
        temperature=0.7,
        max_tokens=512,
    )

    assert result.error is not None
    assert 'unable to parse tool arguments' in result.error.message.lower()


@pytest.mark.asyncio
async def test_call_llm_chat_completion_tool_arguments_array(
    conversation_service,
    mock_llm_service,
    mock_tool_service,
):
    """It returns error result when tool arguments are JSON array instead of object."""
    # Tool call with JSON array instead of object
    array_tool_call = ChatCompletionMessageToolCall(
        id='call_array',
        type='function',
        function=ChatCompletionMessageToolCallFunction(
            name='array_tool',
            arguments='["arg1", "arg2"]',  # Valid JSON but not an object
        ),
    )

    tool_response = LLMCompletionResult(
        content='I will execute the tool.',
        model='llama3.2',
        prompt_tokens=10,
        completion_tokens=12,
        total_tokens=22,
        tool_calls=[array_tool_call],
        finish_reason='tool_calls',
    )

    mock_llm_service.complete_messages.return_value = tool_response
    mock_tool_service.get_available_tools.return_value = []

    result = await conversation_service._call_llm_chat_completion(
        messages=[{'role': 'user', 'content': 'Test'}],
        temperature=0.7,
        max_tokens=512,
    )

    assert result.error is not None
    assert (
        'tool arguments must be a json object' in result.error.message.lower()
    )
    assert 'list' in result.error.message.lower()


@pytest.mark.asyncio
async def test_call_llm_chat_completion_tool_arguments_string(
    conversation_service,
    mock_llm_service,
    mock_tool_service,
):
    """It returns error result when tool arguments are JSON string instead of object."""
    # Tool call with JSON string instead of object
    string_tool_call = ChatCompletionMessageToolCall(
        id='call_string',
        type='function',
        function=ChatCompletionMessageToolCallFunction(
            name='string_tool',
            arguments='"just a string"',  # Valid JSON but not an object
        ),
    )

    tool_response = LLMCompletionResult(
        content='I will execute the tool.',
        model='llama3.2',
        prompt_tokens=10,
        completion_tokens=12,
        total_tokens=22,
        tool_calls=[string_tool_call],
        finish_reason='tool_calls',
    )

    mock_llm_service.complete_messages.return_value = tool_response
    mock_tool_service.get_available_tools.return_value = []

    result = await conversation_service._call_llm_chat_completion(
        messages=[{'role': 'user', 'content': 'Test'}],
        temperature=0.7,
        max_tokens=512,
    )

    assert result.error is not None
    assert (
        'tool arguments must be a json object' in result.error.message.lower()
    )
    assert 'str' in result.error.message.lower()


@pytest.mark.asyncio
async def test_call_llm_chat_completion_tool_arguments_number(
    conversation_service,
    mock_llm_service,
    mock_tool_service,
):
    """It returns error result when tool arguments are JSON number instead of object."""
    # Tool call with JSON number instead of object
    number_tool_call = ChatCompletionMessageToolCall(
        id='call_number',
        type='function',
        function=ChatCompletionMessageToolCallFunction(
            name='number_tool',
            arguments='42',  # Valid JSON but not an object
        ),
    )

    tool_response = LLMCompletionResult(
        content='I will execute the tool.',
        model='llama3.2',
        prompt_tokens=10,
        completion_tokens=12,
        total_tokens=22,
        tool_calls=[number_tool_call],
        finish_reason='tool_calls',
    )

    mock_llm_service.complete_messages.return_value = tool_response
    mock_tool_service.get_available_tools.return_value = []

    result = await conversation_service._call_llm_chat_completion(
        messages=[{'role': 'user', 'content': 'Test'}],
        temperature=0.7,
        max_tokens=512,
    )

    assert result.error is not None
    assert (
        'tool arguments must be a json object' in result.error.message.lower()
    )
    assert 'int' in result.error.message.lower()
