/**
 * API types matching the backend User model
 */
export interface User {
  email: string | null;
  userid: string;
  name: string | null;
}

/**
 * Chat message types matching the backend ChatMessage model
 */
export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

/**
 * Chat request payload matching the backend ChatRequest model
 */
export interface ChatRequest {
  messages: ChatMessage[];
  temperature?: number;
  max_tokens?: number;
}

/**
 * Chat response matching the backend ChatResponse model
 */
export interface ChatResponse {
  content: string;
  model: string;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  total_tokens?: number | null;
}

/**
 * Annotations for message responses.
 */

export interface SourceAnnotation {
  title: string;
  url: string;
  snippet: string;
  rationale: string;
}

export interface ToolAnnotation {
  id?: string | null;
  name: string;
  status: "requested" | "running" | "completed" | "failed";
}

export interface MemoryHitAnnotation {
  label: string;
  summary: string;
}

export interface MemorySavedAnnotation {
  label: string;
  summary: string;
}

export interface FailureAnnotation {
  stage: "llm" | "tool" | "annotation" | "unknown";
  retryable: boolean;
  detail: string | null;
}

export interface AssistantAnnotations {
  thought: string | null;
  sources: SourceAnnotation[];
  tools: ToolAnnotation[];
  memory_hits: MemoryHitAnnotation[];
  memory_saved: MemorySavedAnnotation[];
  failure: FailureAnnotation | null;
  finish_reason?: string | null;
}

/**
 * SSE Event types for streaming responses
 */
export type SSEEventType = "thought" | "token" | "tool_call" | "done" | "error";

export interface SSEEvent {
  event: SSEEventType;
  data: unknown;
}

export interface StreamDoneData {
  conversation_id: string;
  message_id: string;
  content: string;
  annotations: AssistantAnnotations;
}

/**
 * Conversation types matching the backend Conversation models
 */
export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sequence_number: number;
  created_at: string;
  error: string | null;
  annotations: AssistantAnnotations | null;
}

export interface CreateConversationRequest {
  content: string;
  temperature?: number;
  max_tokens?: number;
}

export interface CreateMessageRequest {
  content: string;
  temperature?: number;
  max_tokens?: number;
}

export interface ConversationWithMessagesResponse {
  conversation: ConversationSummary;
  user_message: Message;
  assistant_message: Message;
}

export interface ListConversationsResponse {
  items: ConversationSummary[];
}

export interface GetConversationMessagesResponse {
  conversation: ConversationSummary;
  items: Message[];
}
