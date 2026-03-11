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
