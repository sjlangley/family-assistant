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
