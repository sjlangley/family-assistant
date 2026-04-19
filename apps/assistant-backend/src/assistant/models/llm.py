from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, confloat, conint


class ChatCompletionFunction(BaseModel):
    name: str = Field(..., title='Name')
    description: str | None = Field(None, title='Description')
    parameters: dict[
        str, int | str | bool | list[Any] | dict[str, Any] | None
    ] = Field(..., title='Parameters')


class ChatCompletionMessageToolCallFunction(BaseModel):
    name: str = Field(..., title='Name')
    arguments: str = Field(..., title='Arguments')


class ChatCompletionNamedToolChoiceFunction(BaseModel):
    name: str = Field(..., title='Name')


class ChatCompletionRequestAssistantMessageFunctionCall(BaseModel):
    name: str = Field(..., title='Name')
    arguments: str = Field(..., title='Arguments')


class ChatCompletionRequestFunctionCallOption(BaseModel):
    name: str = Field(..., title='Name')


class ChatCompletionRequestFunctionMessage(BaseModel):
    role: Literal['function'] = Field(..., title='Role')
    content: str | None = Field(..., title='Content')
    name: str = Field(..., title='Name')


class Detail(StrEnum):
    auto = 'auto'
    low = 'low'
    high = 'high'


class ChatCompletionRequestMessageContentPartImageImageUrl(BaseModel):
    url: str = Field(..., title='Url')
    detail: Detail | None = Field(None, title='Detail')


class ChatCompletionRequestMessageContentPartText(BaseModel):
    type: Literal['text'] = Field(..., title='Type')
    text: str = Field(..., title='Text')


class Type(StrEnum):
    text = 'text'
    json_object = 'json_object'


class ChatCompletionRequestResponseFormat(BaseModel):
    type: Type = Field(..., title='Type')
    schema_: int | str | bool | list[Any] | dict[str, Any] | None = Field(
        None, alias='schema', title='Schema'
    )


class ChatCompletionRequestSystemMessage(BaseModel):
    role: Literal['system'] = Field(..., title='Role')
    content: str | None = Field(..., title='Content')


class ChatCompletionRequestToolMessage(BaseModel):
    role: Literal['tool'] = Field(..., title='Role')
    content: str | None = Field(..., title='Content')
    tool_call_id: str = Field(..., title='Tool Call Id')


class ChatCompletionResponseFunctionCall(BaseModel):
    name: str = Field(..., title='Name')
    arguments: str = Field(..., title='Arguments')


class Role(StrEnum):
    assistant = 'assistant'
    function = 'function'


class ChatCompletionToolFunction(BaseModel):
    name: str = Field(..., title='Name')
    description: str | None = Field(None, title='Description')
    parameters: dict[
        str, int | str | bool | list[Any] | dict[str, Any] | None
    ] = Field(..., title='Parameters')


class ChatCompletionTopLogprobToken(BaseModel):
    token: str = Field(..., title='Token')
    logprob: float = Field(..., title='Logprob')
    bytes: list[int] | None = Field(..., title='Bytes')


class FinishReason(StrEnum):
    stop = 'stop'
    length = 'length'


class CompletionLogprobs(BaseModel):
    text_offset: list[int] = Field(..., title='Text Offset')
    token_logprobs: list[float | None] = Field(..., title='Token Logprobs')
    tokens: list[str] = Field(..., title='Tokens')
    top_logprobs: list[dict[str, float] | None] = Field(
        ..., title='Top Logprobs'
    )


class CompletionUsage(BaseModel):
    prompt_tokens: int = Field(..., title='Prompt Tokens')
    completion_tokens: int = Field(..., title='Completion Tokens')
    total_tokens: int = Field(..., title='Total Tokens')


class FunctionCall(StrEnum):
    none = 'none'
    auto = 'auto'


class ToolChoice(StrEnum):
    none = 'none'
    auto = 'auto'
    required = 'required'


class LogitBiasType(StrEnum):
    input_ids = 'input_ids'
    tokens = 'tokens'


class CreateCompletionRequest(BaseModel):
    prompt: str | list[str] | None = Field(
        '',
        description='The prompt to generate completions for.',
        title='Prompt',
    )
    suffix: str | None = Field(
        None,
        description='A suffix to append to the generated text. If None, no suffix is appended. Useful for chatbots.',
        title='Suffix',
    )
    max_tokens: conint(ge=0) | None = Field(
        16,
        description='The maximum number of tokens to generate.',
        title='Max Tokens',
    )
    min_tokens: conint(ge=0) | None = Field(
        0,
        description='The minimum number of tokens to generate. It may return fewer tokens if another condition is met (e.g. max_tokens, stop).',
        title='Min Tokens',
    )
    temperature: float | None = Field(
        0.8,
        description="Adjust the randomness of the generated text.\n\nTemperature is a hyperparameter that controls the randomness of the generated text. It affects the probability distribution of the model's output tokens. A higher temperature (e.g., 1.5) makes the output more random and creative, while a lower temperature (e.g., 0.5) makes the output more focused, deterministic, and conservative. The default value is 0.8, which provides a balance between randomness and determinism. At the extreme, a temperature of 0 will always pick the most likely next token, leading to identical outputs in each run.",
        title='Temperature',
    )
    top_p: confloat(ge=0.0, le=1.0) | None = Field(
        0.95,
        description='Limit the next token selection to a subset of tokens with a cumulative probability above a threshold P.\n\nTop-p sampling, also known as nucleus sampling, is another text generation method that selects the next token from a subset of tokens that together have a cumulative probability of at least p. This method provides a balance between diversity and quality by considering both the probabilities of tokens and the number of tokens to sample from. A higher value for top_p (e.g., 0.95) will lead to more diverse text, while a lower value (e.g., 0.5) will generate more focused and conservative text.',
        title='Top P',
    )
    min_p: confloat(ge=0.0, le=1.0) | None = Field(
        0.05,
        description='Sets a minimum base probability threshold for token selection.\n\nThe Min-P sampling method was designed as an alternative to Top-P, and aims to ensure a balance of quality and variety. The parameter min_p represents the minimum probability for a token to be considered, relative to the probability of the most likely token. For example, with min_p=0.05 and the most likely token having a probability of 0.9, logits with a value less than 0.045 are filtered out.',
        title='Min P',
    )
    echo: bool | None = Field(
        False,
        description='Whether to echo the prompt in the generated text. Useful for chatbots.',
        title='Echo',
    )
    stop: str | list[str] | None = Field(
        None,
        description='A list of tokens at which to stop generation. If None, no stop tokens are used.',
        title='Stop',
    )
    stream: bool | None = Field(
        False,
        description='Whether to stream the results as they are generated. Useful for chatbots.',
        title='Stream',
    )
    logprobs: conint(ge=0) | None = Field(
        None,
        description='The number of logprobs to generate. If None, no logprobs are generated.',
        title='Logprobs',
    )
    presence_penalty: confloat(ge=-2.0, le=2.0) | None = Field(
        0.0,
        description="Positive values penalize new tokens based on whether they appear in the text so far, increasing the model's likelihood to talk about new topics.",
        title='Presence Penalty',
    )
    frequency_penalty: confloat(ge=-2.0, le=2.0) | None = Field(
        0.0,
        description="Positive values penalize new tokens based on their existing frequency in the text so far, decreasing the model's likelihood to repeat the same line verbatim.",
        title='Frequency Penalty',
    )
    logit_bias: dict[str, float] | None = Field(None, title='Logit Bias')
    seed: int | None = Field(None, title='Seed')
    model: str | None = Field(
        None,
        description='The model to use for generating completions.',
        title='Model',
    )
    n: int | None = Field(1, title='N')
    best_of: int | None = Field(1, title='Best Of')
    user: str | None = Field(None, title='User')
    top_k: conint(ge=0) | None = Field(
        40,
        description='Limit the next token selection to the K most probable tokens.\n\nTop-k sampling is a text generation method that selects the next token only from the top k most likely tokens predicted by the model. It helps reduce the risk of generating low-probability or nonsensical tokens, but it may also limit the diversity of the output. A higher value for top_k (e.g., 100) will consider more tokens and lead to more diverse text, while a lower value (e.g., 10) will focus on the most probable tokens and generate more conservative text.',
        title='Top K',
    )
    repeat_penalty: confloat(ge=0.0) | None = Field(
        1.1,
        description='A penalty applied to each token that is already generated. This helps prevent the model from repeating itself.\n\nRepeat penalty is a hyperparameter used to penalize the repetition of token sequences during text generation. It helps prevent the model from generating repetitive or monotonous text. A higher value (e.g., 1.5) will penalize repetitions more strongly, while a lower value (e.g., 0.9) will be more lenient.',
        title='Repeat Penalty',
    )
    logit_bias_type: LogitBiasType | None = Field(None, title='Logit Bias Type')
    mirostat_mode: conint(ge=0, le=2) | None = Field(
        0,
        description='Enable Mirostat constant-perplexity algorithm of the specified version (1 or 2; 0 = disabled)',
        title='Mirostat Mode',
    )
    mirostat_tau: confloat(ge=0.0, le=10.0) | None = Field(
        5.0,
        description='Mirostat target entropy, i.e. the target perplexity - lower values produce focused and coherent text, larger values produce more diverse and less coherent text',
        title='Mirostat Tau',
    )
    mirostat_eta: confloat(ge=0.001, le=1.0) | None = Field(
        0.1, description='Mirostat learning rate', title='Mirostat Eta'
    )
    grammar: str | None = Field(None, title='Grammar')


class CreateEmbeddingRequest(BaseModel):
    model: str | None = Field(
        None,
        description='The model to use for generating completions.',
        title='Model',
    )
    input: str | list[str] = Field(
        ..., description='The input to embed.', title='Input'
    )
    user: str | None = Field(None, title='User')


class DetokenizeInputRequest(BaseModel):
    model: str | None = Field(
        None,
        description='The model to use for generating completions.',
        title='Model',
    )
    tokens: list[int] = Field(
        ..., description='A list of toekns to detokenize.', title='Tokens'
    )


class DetokenizeInputResponse(BaseModel):
    text: str = Field(..., description='The detokenized text.', title='Text')


class ModelData(BaseModel):
    id: str = Field(..., title='Id')
    object: Literal['model'] = Field(..., title='Object')
    owned_by: str = Field(..., title='Owned By')
    permissions: list[str] = Field(..., title='Permissions')


class ModelList(BaseModel):
    object: Literal['list'] = Field(..., title='Object')
    data: list[ModelData] = Field(..., title='Data')


class TokenizeInputCountResponse(BaseModel):
    count: int = Field(
        ..., description='The number of tokens in the input.', title='Count'
    )


class TokenizeInputRequest(BaseModel):
    model: str | None = Field(
        None,
        description='The model to use for generating completions.',
        title='Model',
    )
    input: str = Field(..., description='The input to tokenize.', title='Input')


class TokenizeInputResponse(BaseModel):
    tokens: list[int] = Field(
        ..., description='A list of tokens.', title='Tokens'
    )


class ValidationError(BaseModel):
    loc: list[str | int] = Field(..., title='Location')
    msg: str = Field(..., title='Message')
    type: str = Field(..., title='Error Type')
    input: Any | None = Field(None, title='Input')
    ctx: dict[str, Any] | None = Field(None, title='Context')


class ChatCompletionLogprobToken(BaseModel):
    token: str = Field(..., title='Token')
    logprob: float = Field(..., title='Logprob')
    bytes: list[int] | None = Field(..., title='Bytes')
    top_logprobs: list[ChatCompletionTopLogprobToken] = Field(
        ..., title='Top Logprobs'
    )


class ChatCompletionLogprobs(BaseModel):
    content: list[ChatCompletionLogprobToken] | None = Field(
        ..., title='Content'
    )
    refusal: list[ChatCompletionLogprobToken] | None = Field(
        ..., title='Refusal'
    )


class ChatCompletionMessageToolCall(BaseModel):
    id: str = Field(..., title='Id')
    type: Literal['function'] = Field(..., title='Type')
    function: ChatCompletionMessageToolCallFunction


class ChatCompletionNamedToolChoice(BaseModel):
    type: Literal['function'] = Field(..., title='Type')
    function: ChatCompletionNamedToolChoiceFunction


class ChatCompletionRequestAssistantMessage(BaseModel):
    role: Literal['assistant'] = Field(..., title='Role')
    content: str | None = Field(None, title='Content')
    tool_calls: list[ChatCompletionMessageToolCall] | None = Field(
        None, title='Tool Calls'
    )
    function_call: ChatCompletionRequestAssistantMessageFunctionCall | None = (
        None
    )


class ChatCompletionRequestMessageContentPartImage(BaseModel):
    type: Literal['image_url'] = Field(..., title='Type')
    image_url: str | ChatCompletionRequestMessageContentPartImageImageUrl = (
        Field(..., title='Image Url')
    )


class ChatCompletionRequestUserMessage(BaseModel):
    role: Literal['user'] = Field(..., title='Role')
    content: (
        str
        | list[
            ChatCompletionRequestMessageContentPartText
            | ChatCompletionRequestMessageContentPartImage
        ]
        | None
    ) = Field(..., title='Content')


class ChatCompletionResponseMessage(BaseModel):
    content: str | None = Field(..., title='Content')
    tool_calls: list[ChatCompletionMessageToolCall] | None = Field(
        None, title='Tool Calls'
    )
    role: Role = Field(..., title='Role')
    function_call: ChatCompletionResponseFunctionCall | None = None


class ChatCompletionTool(BaseModel):
    type: Literal['function'] = Field(..., title='Type')
    function: ChatCompletionToolFunction


class CompletionChoice(BaseModel):
    text: str = Field(..., title='Text')
    index: int = Field(..., title='Index')
    logprobs: CompletionLogprobs | None
    finish_reason: FinishReason | None = Field(..., title='Finish Reason')


class CreateChatCompletionRequest(BaseModel):
    messages: (
        list[
            ChatCompletionRequestSystemMessage
            | ChatCompletionRequestUserMessage
            | ChatCompletionRequestAssistantMessage
            | ChatCompletionRequestToolMessage
            | ChatCompletionRequestFunctionMessage
        ]
        | None
    ) = Field(
        [],
        description='A list of messages to generate completions for.',
        title='Messages',
    )
    functions: list[ChatCompletionFunction] | None = Field(
        None,
        description='A list of functions to apply to the generated completions.',
        title='Functions',
    )
    function_call: (
        FunctionCall | ChatCompletionRequestFunctionCallOption | None
    ) = Field(
        None,
        description='A function to apply to the generated completions.',
        title='Function Call',
    )
    tools: list[ChatCompletionTool] | None = Field(
        None,
        description='A list of tools to apply to the generated completions.',
        title='Tools',
    )
    tool_choice: ToolChoice | ChatCompletionNamedToolChoice | None = Field(
        None,
        description='A tool to apply to the generated completions.',
        title='Tool Choice',
    )
    max_tokens: int | None = Field(
        None,
        description='The maximum number of tokens to generate. Defaults to inf',
        title='Max Tokens',
    )
    min_tokens: conint(ge=0) | None = Field(
        0,
        description='The minimum number of tokens to generate. It may return fewer tokens if another condition is met (e.g. max_tokens, stop).',
        title='Min Tokens',
    )
    logprobs: bool | None = Field(
        False,
        description='Whether to output the logprobs or not. Default is True',
        title='Logprobs',
    )
    top_logprobs: conint(ge=0) | None = Field(
        None,
        description='The number of logprobs to generate. If None, no logprobs are generated. logprobs need to set to True.',
        title='Top Logprobs',
    )
    temperature: float | None = Field(
        0.8,
        description="Adjust the randomness of the generated text.\n\nTemperature is a hyperparameter that controls the randomness of the generated text. It affects the probability distribution of the model's output tokens. A higher temperature (e.g., 1.5) makes the output more random and creative, while a lower temperature (e.g., 0.5) makes the output more focused, deterministic, and conservative. The default value is 0.8, which provides a balance between randomness and determinism. At the extreme, a temperature of 0 will always pick the most likely next token, leading to identical outputs in each run.",
        title='Temperature',
    )
    top_p: confloat(ge=0.0, le=1.0) | None = Field(
        0.95,
        description='Limit the next token selection to a subset of tokens with a cumulative probability above a threshold P.\n\nTop-p sampling, also known as nucleus sampling, is another text generation method that selects the next token from a subset of tokens that together have a cumulative probability of at least p. This method provides a balance between diversity and quality by considering both the probabilities of tokens and the number of tokens to sample from. A higher value for top_p (e.g., 0.95) will lead to more diverse text, while a lower value (e.g., 0.5) will generate more focused and conservative text.',
        title='Top P',
    )
    min_p: confloat(ge=0.0, le=1.0) | None = Field(
        0.05,
        description='Sets a minimum base probability threshold for token selection.\n\nThe Min-P sampling method was designed as an alternative to Top-P, and aims to ensure a balance of quality and variety. The parameter min_p represents the minimum probability for a token to be considered, relative to the probability of the most likely token. For example, with min_p=0.05 and the most likely token having a probability of 0.9, logits with a value less than 0.045 are filtered out.',
        title='Min P',
    )
    stop: str | list[str] | None = Field(
        None,
        description='A list of tokens at which to stop generation. If None, no stop tokens are used.',
        title='Stop',
    )
    stream: bool | None = Field(
        False,
        description='Whether to stream the results as they are generated. Useful for chatbots.',
        title='Stream',
    )
    presence_penalty: confloat(ge=-2.0, le=2.0) | None = Field(
        0.0,
        description="Positive values penalize new tokens based on whether they appear in the text so far, increasing the model's likelihood to talk about new topics.",
        title='Presence Penalty',
    )
    frequency_penalty: confloat(ge=-2.0, le=2.0) | None = Field(
        0.0,
        description="Positive values penalize new tokens based on their existing frequency in the text so far, decreasing the model's likelihood to repeat the same line verbatim.",
        title='Frequency Penalty',
    )
    logit_bias: dict[str, float] | None = Field(None, title='Logit Bias')
    seed: int | None = Field(None, title='Seed')
    response_format: ChatCompletionRequestResponseFormat | None = None
    model: str | None = Field(
        None,
        description='The model to use for generating completions.',
        title='Model',
    )
    n: int | None = Field(1, title='N')
    user: str | None = Field(None, title='User')
    top_k: conint(ge=0) | None = Field(
        40,
        description='Limit the next token selection to the K most probable tokens.\n\nTop-k sampling is a text generation method that selects the next token only from the top k most likely tokens predicted by the model. It helps reduce the risk of generating low-probability or nonsensical tokens, but it may also limit the diversity of the output. A higher value for top_k (e.g., 100) will consider more tokens and lead to more diverse text, while a lower value (e.g., 10) will focus on the most probable tokens and generate more conservative text.',
        title='Top K',
    )
    repeat_penalty: confloat(ge=0.0) | None = Field(
        1.1,
        description='A penalty applied to each token that is already generated. This helps prevent the model from repeating itself.\n\nRepeat penalty is a hyperparameter used to penalize the repetition of token sequences during text generation. It helps prevent the model from generating repetitive or monotonous text. A higher value (e.g., 1.5) will penalize repetitions more strongly, while a lower value (e.g., 0.9) will be more lenient.',
        title='Repeat Penalty',
    )
    logit_bias_type: LogitBiasType | None = Field(None, title='Logit Bias Type')
    mirostat_mode: conint(ge=0, le=2) | None = Field(
        0,
        description='Enable Mirostat constant-perplexity algorithm of the specified version (1 or 2; 0 = disabled)',
        title='Mirostat Mode',
    )
    mirostat_tau: confloat(ge=0.0, le=10.0) | None = Field(
        5.0,
        description='Mirostat target entropy, i.e. the target perplexity - lower values produce focused and coherent text, larger values produce more diverse and less coherent text',
        title='Mirostat Tau',
    )
    mirostat_eta: confloat(ge=0.001, le=1.0) | None = Field(
        0.1, description='Mirostat learning rate', title='Mirostat Eta'
    )
    grammar: str | None = Field(None, title='Grammar')


class CreateCompletionResponse(BaseModel):
    id: str = Field(..., title='Id')
    object: Literal['text_completion'] = Field(..., title='Object')
    created: int = Field(..., title='Created')
    model: str = Field(..., title='Model')
    choices: list[CompletionChoice] = Field(..., title='Choices')
    usage: CompletionUsage | None = None


class HTTPValidationError(BaseModel):
    detail: list[ValidationError] | None = Field(None, title='Detail')


class ChatCompletionResponseChoice(BaseModel):
    index: int = Field(..., title='Index')
    message: ChatCompletionResponseMessage
    logprobs: ChatCompletionLogprobs | None = None
    finish_reason: str | None = Field(..., title='Finish Reason')


class CreateChatCompletionResponse(BaseModel):
    id: str = Field(..., title='Id')
    object: Literal['chat.completion'] = Field(..., title='Object')
    created: int = Field(..., title='Created')
    model: str = Field(..., title='Model')
    choices: list[ChatCompletionResponseChoice] = Field(..., title='Choices')
    usage: CompletionUsage


# Streaming-specific models


class ChatCompletionStreamResponseDeltaToolCallFunction(BaseModel):
    """Function object in a streaming tool call delta.

    In streaming responses, this may be partial:
    - First chunk: has name and empty arguments
    - Subsequent chunks: may only have argument deltas, name may be omitted
    """

    name: str | None = Field(
        None,
        description='Function name (typically only in first chunk of tool call)',
    )
    arguments: str | None = Field(
        None, description='Incremental JSON arguments string'
    )


class ChatCompletionStreamResponseDeltaToolCall(BaseModel):
    """Tool call in a streaming response delta.

    Streaming tool calls are sent incrementally:
    - First chunk: has id, type, and function with name
    - Subsequent chunks: have index and function with argument deltas
    """

    index: int | None = Field(
        None,
        description='Index of the tool call (optional; some providers omit it in deltas)',
    )
    id: str | None = Field(
        None, description='Tool call ID (typically only in first chunk)'
    )
    type: Literal['function'] | None = Field(
        None, description="Type is 'function' (typically only in first chunk)"
    )
    function: ChatCompletionStreamResponseDeltaToolCallFunction | None = Field(
        None, description='Function information (progressive updates)'
    )


class ChatCompletionStreamResponseDelta(BaseModel):
    """Incremental content in a streaming chunk.

    In streaming mode, the 'delta' object contains only the fields that have
    changed since the previous chunk, allowing for efficient transmission.
    """

    content: str | None = Field(
        None, description='Partial content token for user-visible output'
    )
    tool_calls: list[ChatCompletionStreamResponseDeltaToolCall] | None = Field(
        None,
        description='Tool call deltas (index always present, other fields progressive)',
    )
    role: str | None = Field(
        None, description='Role (typically only in first delta)'
    )
    reasoning_content: str | None = Field(
        None, description='Native reasoning/thinking token (if model emits it)'
    )


class ChatCompletionStreamResponseChoice(BaseModel):
    """Single choice from a streaming response chunk."""

    index: int = Field(..., description='Choice index')
    delta: ChatCompletionStreamResponseDelta = Field(
        ..., description='Incremental content for this chunk'
    )
    finish_reason: str | None = Field(
        None, description='Completion reason if stream has ended (e.g. "stop")'
    )
    logprobs: ChatCompletionLogprobs | None = None


class ChatCompletionStreamResponse(BaseModel):
    """OpenAI-compatible streaming response chunk.

    As per OpenAI spec, streaming responses are sent as NDJSON with
    incremental deltas rather than cumulative content.
    """

    id: str = Field(..., description='Unique completion ID')
    object: Literal['chat.completion.chunk'] = Field(
        ..., description='Object type identifier'
    )
    created: int = Field(..., description='Unix timestamp')
    model: str = Field(..., description='Model identifier')
    choices: list[ChatCompletionStreamResponseChoice] = Field(
        ..., description='List of streaming choices (typically one)'
    )
    usage: CompletionUsage | None = Field(
        None, description='Token usage (usually only in final chunk)'
    )


# Shared LLM completion seam types


class StreamParserOutput(BaseModel):
    """Typed output from stream chunk parsing.

    The parser distinguishes between reasoning content (thought) and user-visible
    content (token), handling both native reasoning fields and tag-based parsing.
    """

    thought: str | None = Field(
        None,
        description='Incremental reasoning/thinking content for this chunk',
    )
    token: str | None = Field(None, description='User-visible content token')
    tool_calls: list[ChatCompletionMessageToolCall] | None = Field(
        None, description='Tool call metadata if present'
    )
    finish_reason: str | None = Field(
        None, description='Completion signal (e.g. "stop") in final chunk'
    )
    usage: CompletionUsage | None = Field(
        None, description='Token usage in final chunk (if provided)'
    )
    model: str | None = Field(None, description='Model identifier from chunk')


class LLMCompletionResult(BaseModel):
    """Result from a successful LLM completion.

    Preserves assistant message metadata including tool_calls and finish_reason
    for future tool-calling and streaming implementations.
    """

    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    tool_calls: list[ChatCompletionMessageToolCall] | None = None
    finish_reason: str | None = None


class LLMCompletionErrorKind(StrEnum):
    """Classification of LLM completion errors."""

    timeout = 'timeout'
    unreachable = 'unreachable'
    backend_error = 'backend_error'
    invalid_response = 'invalid_response'


class LLMCompletionError(Exception):
    """Service-level error for LLM completion failures."""

    def __init__(
        self,
        kind: LLMCompletionErrorKind,
        message: str,
        backend_status_code: int | None = None,
    ):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.backend_status_code = backend_status_code
