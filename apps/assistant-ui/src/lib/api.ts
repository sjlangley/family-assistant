/**
 * API client for backend communication
 * All requests include credentials to send session cookies
 */

import type {
  User,
  ChatRequest,
  ChatResponse,
  ListConversationsResponse,
  GetConversationMessagesResponse,
  ConversationWithMessagesResponse,
  CreateConversationRequest,
  CreateMessageRequest,
  SSEEvent,
  SSEEventType,
} from "../types/api";

function getApiBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL || "";
}

/**
 * Stream a conversation with SSE
 */
export async function* streamConversation(
  conversationId: string | null,
  content: string,
  options?: {
    temperature?: number;
    max_tokens?: number;
    signal?: AbortSignal;
  },
): AsyncGenerator<SSEEvent, void, unknown> {
  const url = conversationId
    ? `${getApiBaseUrl()}/api/v1/conversations/${conversationId}/messages`
    : `${getApiBaseUrl()}/api/v1/conversations/with-message`;

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "include",
    body: JSON.stringify({
      content,
      temperature: options?.temperature,
      max_tokens: options?.max_tokens,
      stream: true,
    }),
    signal: options?.signal,
  });

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("UNAUTHORIZED");
    }
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || "Streaming request failed");
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("Response body is not readable");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  const processSegments = function* (
    segments: string[],
  ): Generator<SSEEvent, void, unknown> {
    for (const segment of segments) {
      if (!segment.trim()) continue;

      const lines = segment.split("\n");
      let event: SSEEventType | undefined;
      let dataBuffer = "";

      for (const line of lines) {
        if (line.startsWith("event: ")) {
          event = line.substring(7).trim() as SSEEventType;
        } else if (line.startsWith("data: ")) {
          dataBuffer += (dataBuffer ? "\n" : "") + line.substring(6);
        }
      }

      if (event && dataBuffer) {
        try {
          const data = JSON.parse(dataBuffer);
          yield { event, data };
        } catch (e) {
          console.error("Failed to parse SSE data", e, dataBuffer);
        }
      }
    }
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const segments = buffer.split("\n\n");
      // Keep the last segment in the buffer if it's incomplete
      buffer = segments.pop() || "";
      yield* processSegments(segments);
    }

    // Flush decoder and process any remaining buffer content
    buffer += decoder.decode();
    if (buffer.trim()) {
      yield* processSegments(buffer.split("\n\n"));
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * Login with Google ID token
 */
export async function login(googleIdToken: string): Promise<User> {
  const response = await fetch(`${getApiBaseUrl()}/auth/login`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${googleIdToken}`,
    },
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error("Login failed");
  }

  return response.json();
}

/**
 * Get current authenticated user
 * Returns null if not authenticated (401 response)
 */
export async function getCurrentUser(
  signal?: AbortSignal,
): Promise<User | null> {
  const response = await fetch(`${getApiBaseUrl()}/user/current`, {
    credentials: "include",
    signal,
  });

  if (response.status === 401) {
    return null;
  }

  if (!response.ok) {
    throw new Error("Failed to fetch current user");
  }

  return response.json();
}

/**
 * Logout current user
 */
export async function logout(): Promise<void> {
  const response = await fetch(`${getApiBaseUrl()}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error("Logout failed");
  }
}

/**
 * Send chat completion request
 * Throws error if request fails or user is not authenticated (401)
 */
export async function sendChatCompletion(
  request: ChatRequest,
): Promise<ChatResponse> {
  const response = await fetch(`${getApiBaseUrl()}/api/v1/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "include",
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("UNAUTHORIZED");
    }
    throw new Error("Chat request failed");
  }

  return response.json();
}

/**
 * List all conversations for the current user
 */
export async function listConversations(
  signal?: AbortSignal,
): Promise<ListConversationsResponse> {
  const response = await fetch(`${getApiBaseUrl()}/api/v1/conversations`, {
    credentials: "include",
    signal,
  });

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("UNAUTHORIZED");
    }
    throw new Error("Failed to fetch conversations");
  }

  return response.json();
}

/**
 * Get messages for a specific conversation
 */
export async function getConversationMessages(
  conversationId: string,
  signal?: AbortSignal,
): Promise<GetConversationMessagesResponse> {
  const response = await fetch(
    `${getApiBaseUrl()}/api/v1/conversations/${conversationId}/messages`,
    {
      credentials: "include",
      signal,
    },
  );

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("UNAUTHORIZED");
    }
    if (response.status === 404) {
      throw new Error("Conversation not found");
    }
    throw new Error("Failed to fetch conversation messages");
  }

  return response.json();
}

/**
 * Create a new conversation with an initial message
 */
export async function createConversationWithMessage(
  request: CreateConversationRequest,
): Promise<ConversationWithMessagesResponse> {
  const response = await fetch(
    `${getApiBaseUrl()}/api/v1/conversations/with-message`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify(request),
    },
  );

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("UNAUTHORIZED");
    }
    throw new Error("Failed to create conversation");
  }

  return response.json();
}

/**
 * Add a message to an existing conversation
 */
export async function addMessageToConversation(
  conversationId: string,
  request: CreateMessageRequest,
): Promise<ConversationWithMessagesResponse> {
  const response = await fetch(
    `${getApiBaseUrl()}/api/v1/conversations/${conversationId}/messages`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify(request),
    },
  );

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("UNAUTHORIZED");
    }
    if (response.status === 404) {
      throw new Error("Conversation not found");
    }
    throw new Error("Failed to add message");
  }

  return response.json();
}
