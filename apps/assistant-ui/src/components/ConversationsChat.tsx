import { useState, useEffect, useCallback } from "react";
import type {
  ConversationSummary,
  Message,
  ConversationWithMessagesResponse,
} from "../types/api";
import {
  listConversations,
  getConversationMessages,
  createConversationWithMessage,
  addMessageToConversation,
} from "../lib/api";
import { useAuth } from "../lib/auth";

interface ConversationsChatProps {
  onLogout: () => void;
}

export function ConversationsChat({ onLogout }: ConversationsChatProps) {
  const { authState } = useAuth();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<
    string | null
  >(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversationsLoading, setConversationsLoading] = useState(true);
  const [conversationsError, setConversationsError] = useState<string | null>(
    null,
  );

  // Get user from authState (it should always be present when component is mounted)
  const user = authState.status === "authenticated" ? authState.user : null;

  // Load conversations on mount
  useEffect(() => {
    const controller = new AbortController();
    const loadConversations = async () => {
      try {
        setConversationsLoading(true);
        setConversationsError(null);
        const response = await listConversations(controller.signal);
        setConversations(response.items);
      } catch (err) {
        if (err instanceof Error) {
          if (err.name === "AbortError") return;
          if (err.message === "UNAUTHORIZED") {
            onLogout();
            return;
          }
          setConversationsError(err.message);
        } else {
          setConversationsError("Failed to load conversations");
        }
      } finally {
        setConversationsLoading(false);
      }
    };

    loadConversations();

    return () => {
      controller.abort();
    };
  }, [onLogout]);

  // Load messages when active conversation changes
  useEffect(() => {
    if (!activeConversationId) {
      setMessages([]);
      return;
    }

    const controller = new AbortController();
    const loadMessages = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const response = await getConversationMessages(
          activeConversationId,
          controller.signal,
        );
        setMessages(response.items);
      } catch (err) {
        if (err instanceof Error) {
          if (err.name === "AbortError") return;
          if (err.message === "UNAUTHORIZED") {
            onLogout();
            return;
          }
          setError(err.message);
        } else {
          setError("Failed to load messages");
        }
      } finally {
        setIsLoading(false);
      }
    };

    loadMessages();

    return () => {
      controller.abort();
    };
  }, [activeConversationId, onLogout]);

  // Handle new chat button
  const handleNewChat = useCallback(() => {
    setActiveConversationId(null);
    setMessages([]);
    setError(null);
  }, []);

  // Handle conversation selection
  const handleSelectConversation = useCallback((conversationId: string) => {
    setActiveConversationId(conversationId);
    setError(null);
  }, []);

  // Update conversations list with new or updated conversation
  const updateConversationsList = useCallback(
    (conversationResponse: ConversationWithMessagesResponse) => {
      const { conversation } = conversationResponse;
      setConversations((prev) => {
        const existing = prev.find((c) => c.id === conversation.id);
        if (existing) {
          // Update existing conversation
          return prev.map((c) =>
            c.id === conversation.id
              ? {
                  id: conversation.id,
                  title: conversation.title,
                  created_at: conversation.created_at,
                  updated_at: conversation.updated_at,
                }
              : c,
          );
        } else {
          // Add new conversation at the beginning
          return [
            {
              id: conversation.id,
              title: conversation.title,
              created_at: conversation.created_at,
              updated_at: conversation.updated_at,
            },
            ...prev,
          ];
        }
      });
    },
    [],
  );

  // Handle sending a message
  const handleSendMessage = async () => {
    const trimmedMessage = inputMessage.trim();
    if (!trimmedMessage) return;

    setIsLoading(true);
    setError(null);

    try {
      let response: ConversationWithMessagesResponse;

      if (activeConversationId) {
        // Add message to existing conversation
        response = await addMessageToConversation(activeConversationId, {
          content: trimmedMessage,
        });
      } else {
        // Create new conversation with message
        response = await createConversationWithMessage({
          content: trimmedMessage,
        });
        // Set active conversation to the new one
        setActiveConversationId(response.conversation.id);
      }

      // Update conversations list
      updateConversationsList(response);

      // Update messages with the response (append the new messages)
      setMessages((prev) => [
        ...prev,
        response.user_message,
        response.assistant_message,
      ]);

      // Clear input
      setInputMessage("");
    } catch (err) {
      if (err instanceof Error) {
        if (err.message === "UNAUTHORIZED") {
          onLogout();
          return;
        }
        setError(err.message);
      } else {
        setError("Failed to send message");
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className="flex h-screen bg-gray-100">
      {/* Left sidebar: Conversations list */}
      <div className="w-64 bg-white border-r border-gray-200 flex flex-col">
        <div className="p-4 border-b border-gray-200">
          <button
            type="button"
            onClick={handleNewChat}
            className="w-full bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600 transition-colors"
          >
            + New Chat
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {conversationsLoading && (
            <div className="p-4 text-gray-500 text-sm">
              Loading conversations...
            </div>
          )}

          {conversationsError && (
            <div className="p-4 text-red-500 text-sm">
              Error: {conversationsError}
            </div>
          )}

          {!conversationsLoading && !conversationsError && (
            <div className="space-y-1">
              {conversations.length === 0 ? (
                <div className="p-4 text-gray-400 text-sm text-center">
                  No conversations yet
                </div>
              ) : (
                conversations.map((conv) => (
                  <button
                    key={conv.id}
                    onClick={() => handleSelectConversation(conv.id)}
                    className={`w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors ${
                      activeConversationId === conv.id
                        ? "bg-blue-50 border-r-2 border-blue-500"
                        : ""
                    }`}
                  >
                    <div className="font-medium text-sm truncate">
                      {conv.title}
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      {new Date(conv.updated_at).toLocaleDateString()}
                    </div>
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        <div className="p-4 border-t border-gray-200">
          <div className="text-sm text-gray-600 mb-2">
            Logged in as: {user?.email}
          </div>
          <button
            onClick={onLogout}
            className="w-full bg-gray-200 text-gray-700 px-4 py-2 rounded hover:bg-gray-300 transition-colors"
          >
            Logout
          </button>
        </div>
      </div>

      {/* Main panel: Messages and composer */}
      <div className="flex-1 flex flex-col">
        {/* Messages area */}
        <div className="flex-1 overflow-y-auto p-4">
          {activeConversationId ? (
            <>
              {isLoading && messages.length === 0 ? (
                <div className="text-gray-500">Loading messages...</div>
              ) : (
                <div className="space-y-4 max-w-3xl mx-auto">
                  {messages.map((msg) => (
                    <div
                      key={msg.id}
                      className={`flex ${
                        msg.role === "user" ? "justify-end" : "justify-start"
                      }`}
                    >
                      <div
                        className={`max-w-md px-4 py-2 rounded-lg ${
                          msg.role === "user"
                            ? "bg-blue-500 text-white"
                            : msg.error
                              ? "bg-red-100 text-red-900 border border-red-300"
                              : "bg-white text-gray-900 border border-gray-200"
                        }`}
                      >
                        <div className="whitespace-pre-wrap">{msg.content}</div>
                        {msg.error && (
                          <div className="text-xs mt-2 font-medium">
                            Error: {msg.error}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="flex items-center justify-center h-full text-gray-400">
              <div className="text-center">
                <div className="text-6xl mb-4">💬</div>
                <div className="text-xl mb-2">Welcome to Family Assistant</div>
                <div className="text-sm">
                  Select a conversation or start a new chat below
                </div>
              </div>
            </div>
          )}

          {error && (
            <div className="max-w-3xl mx-auto mt-4 p-4 bg-red-100 text-red-700 rounded">
              Error: {error}
            </div>
          )}
        </div>

        {/* Message composer - always visible */}
        <div className="border-t border-gray-200 bg-white p-4">
          <div className="max-w-3xl mx-auto flex gap-2">
            <input
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                activeConversationId
                  ? "Type your message..."
                  : "Type a message to start a new conversation..."
              }
              disabled={isLoading}
              className="flex-1 border border-gray-300 rounded px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            />
            <button
              onClick={handleSendMessage}
              disabled={isLoading || !inputMessage.trim()}
              className="bg-blue-500 text-white px-6 py-2 rounded hover:bg-blue-600 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
            >
              {isLoading ? "Sending..." : "Send"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
