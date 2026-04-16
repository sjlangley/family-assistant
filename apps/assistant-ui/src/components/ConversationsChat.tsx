import { useState, useEffect, useCallback, useRef } from "react";
import type {
  ConversationSummary,
  Message,
  ConversationWithMessagesResponse,
  AssistantAnnotations,
  ToolAnnotation,
} from "../types/api";
import {
  listConversations,
  getConversationMessages,
  createConversationWithMessage,
  addMessageToConversation,
} from "../lib/api";
import { useAuth } from "../lib/auth";
import { MarkdownContent } from "./MarkdownContent";

interface ConversationsChatProps {
  onLogout: () => void;
}

// UUID for pending assistant placeholder message
const PENDING_MESSAGE_ID = "pending-assistant-placeholder";

// Create a pending assistant placeholder message
function createPendingAssistantMessage(): Message {
  return {
    id: PENDING_MESSAGE_ID,
    role: "assistant",
    content: "Thinking...",
    sequence_number: -1, // Placeholder sequence
    created_at: new Date().toISOString(),
    error: null,
    annotations: null,
  };
}

// TrustPill: Compact metadata item from annotations
interface TrustPillProps {
  label: string;
  value?: string | number;
}

function TrustPill({ label, value }: TrustPillProps) {
  return (
    <div className="trust-pill">
      <span className="trust-pill-label">{label}</span>
      {value !== undefined && <span className="trust-pill-value">{value}</span>}
    </div>
  );
}

// TrustRow: Renders compact trust metadata under assistant messages
interface TrustRowProps {
  annotations: AssistantAnnotations;
}

function TrustRow({ annotations }: TrustRowProps) {
  return (
    <div className="trust-row">
      {/* Tools used */}
      {annotations.tools && annotations.tools.length > 0 && (
        <TrustPill
          label="Tools"
          value={annotations.tools.map((t) => t.name).join(", ")}
        />
      )}

      {/* Source count */}
      {annotations.sources && annotations.sources.length > 0 && (
        <TrustPill label="Sources" value={annotations.sources.length} />
      )}

      {/* Memory hits */}
      {annotations.memory_hits && annotations.memory_hits.length > 0 && (
        <TrustPill label="Memory" value={annotations.memory_hits.length} />
      )}

      {/* Memory saved */}
      {annotations.memory_saved && annotations.memory_saved.length > 0 && (
        <TrustPill label="Saved" value={annotations.memory_saved.length} />
      )}
    </div>
  );
}

// FailureRow: Renders failure annotations distinctly
interface FailureRowProps {
  detail: string | null | undefined;
  stage: string;
  retryable: boolean;
}

function FailureRow({ detail, stage, retryable }: FailureRowProps) {
  let stageLabel = "Unknown error";
  if (stage === "llm") stageLabel = "LLM error";
  if (stage === "tool") stageLabel = "Tool error";
  if (stage === "annotation") stageLabel = "Processing error";

  return (
    <div className="failure-row">
      <span className="failure-icon">⚠</span>
      <div className="flex-1">
        <div className="failure-text font-medium">{stageLabel}</div>
        {detail && <div className="failure-text text-xs mt-1">{detail}</div>}
        {retryable && (
          <div className="failure-text text-xs mt-1">(May be retryable)</div>
        )}
      </div>
    </div>
  );
}

export function ConversationsChat({ onLogout }: ConversationsChatProps) {
  const { authState } = useAuth();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<
    string | null
  >(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState("");
  const [transcriptLoading, setTranscriptLoading] = useState(false);
  const [sendingMessage, setSendingMessage] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversationsLoading, setConversationsLoading] = useState(true);
  const [conversationsError, setConversationsError] = useState<string | null>(
    null,
  );

  // Track conversations for which we've just set messages to skip redundant fetches
  const skipFetchForConversation = useRef<string | null>(null);

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

    // Skip fetch if we just set messages for this conversation
    if (skipFetchForConversation.current === activeConversationId) {
      skipFetchForConversation.current = null;
      return;
    }

    const controller = new AbortController();
    const loadMessages = async () => {
      try {
        setTranscriptLoading(true);
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
        setTranscriptLoading(false);
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
        const updatedConversation = {
          id: conversation.id,
          title: conversation.title,
          created_at: conversation.created_at,
          updated_at: conversation.updated_at,
        };

        if (existing) {
          // Update existing conversation and re-sort by updated_at desc
          return [
            updatedConversation,
            ...prev.filter((c) => c.id !== conversation.id),
          ];
        } else {
          // Add new conversation at the beginning
          return [updatedConversation, ...prev];
        }
      });
    },
    [],
  );

  // Handle sending a message
  const handleSendMessage = async () => {
    const trimmedMessage = inputMessage.trim();
    if (!trimmedMessage) return;

    setSendingMessage(true);
    setError(null);

    try {
      let response: ConversationWithMessagesResponse;

      if (activeConversationId) {
        // Add message to existing conversation
        // Immediately show user message and pending assistant placeholder
        const userMessage: Message = {
          id: `temp-user-${Date.now()}`,
          role: "user",
          content: trimmedMessage,
          sequence_number: -1,
          created_at: new Date().toISOString(),
          error: null,
          annotations: null,
        };
        const pendingMessage = createPendingAssistantMessage();
        setMessages((prev) => [...prev, userMessage, pendingMessage]);
        setInputMessage("");

        try {
          response = await addMessageToConversation(activeConversationId, {
            content: trimmedMessage,
          });

          // Replace pending placeholder with real assistant message
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === PENDING_MESSAGE_ID ? response.assistant_message : msg,
            ),
          );

          // Update conversations list
          updateConversationsList(response);
        } catch (err) {
          // Remove pending message on error
          setMessages((prev) =>
            prev.filter((msg) => msg.id !== PENDING_MESSAGE_ID),
          );
          throw err;
        }
      } else {
        // Create new conversation with message
        // Immediately show user message and pending placeholder
        const userMessage: Message = {
          id: `temp-user-${Date.now()}`,
          role: "user",
          content: trimmedMessage,
          sequence_number: 1,
          created_at: new Date().toISOString(),
          error: null,
          annotations: null,
        };
        const pendingMessage = createPendingAssistantMessage();
        setMessages([userMessage, pendingMessage]);
        setInputMessage("");

        response = await createConversationWithMessage({
          content: trimmedMessage,
        });

        // Update conversations list
        updateConversationsList(response);

        // Mark this conversation to skip the initial fetch
        skipFetchForConversation.current = response.conversation.id;

        // Set messages with real user and assistant messages, removing placeholder
        setMessages([response.user_message, response.assistant_message]);

        // Set active conversation to the new one (this will trigger useEffect but it will skip fetch)
        setActiveConversationId(response.conversation.id);
      }
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
      setSendingMessage(false);
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
                    className={`w-full text-left px-4 py-3 hover:bg-[#f6f2ea] transition-colors ${
                      activeConversationId === conv.id
                        ? "bg-[#f0e8da] border-r-2 border-[#24453a]"
                        : ""
                    }`}
                  >
                    <div className="type-body-sm font-medium truncate">
                      {conv.title}
                    </div>
                    <div className="type-meta mt-1">
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
            Logged in as: {user?.email ?? user?.name ?? user?.userid}
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
              {transcriptLoading && messages.length === 0 ? (
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
                        className={
                          msg.role === "user" ? "max-w-md" : "max-w-md"
                        }
                      >
                        {/* Message bubble */}
                        <div
                          className={`px-4 py-2 rounded-lg ${
                            msg.role === "user"
                              ? "message-user-bubble"
                              : msg.error
                                ? "message-error-bubble"
                                : msg.id === PENDING_MESSAGE_ID
                                  ? "message-pending-bubble"
                                  : "message-assistant-bubble"
                          }`}
                        >
                          {msg.role === "assistant" ? (
                            <MarkdownContent content={msg.content} />
                          ) : (
                            <div className="whitespace-pre-wrap">
                              {msg.content}
                            </div>
                          )}
                          {msg.error && !msg.annotations?.failure && (
                            <div className="text-xs mt-2 font-medium">
                              Error: {msg.error}
                            </div>
                          )}
                        </div>

                        {/* Trust row for assistant messages with annotations */}
                        {msg.role === "assistant" && msg.annotations && (
                          <>
                            {msg.annotations.failure ? (
                              <FailureRow
                                detail={msg.annotations.failure.detail}
                                stage={msg.annotations.failure.stage}
                                retryable={msg.annotations.failure.retryable}
                              />
                            ) : (
                              <TrustRow annotations={msg.annotations} />
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <div className="text-6xl mb-4" aria-hidden="true">
                  💬
                </div>
                <div className="type-heading-md text-[#24453a] mb-2">
                  Welcome to Family Assistant
                </div>
                <div className="type-body-sm text-[#6e675d]">
                  Select a conversation or start a new chat below
                </div>
              </div>
            </div>
          )}

          {error && (
            <div className="max-w-3xl mx-auto mt-4 p-4 bg-[#f8e9e6] text-[#a54034] rounded border border-[#e0b5ad]">
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
              disabled={sendingMessage}
              className="flex-1 border border-[#ded6c7] rounded px-4 py-2 focus:outline-none focus:ring-2 focus:ring-[#24453a] disabled:bg-[#f6f2ea]"
            />
            <button
              onClick={handleSendMessage}
              disabled={sendingMessage || !inputMessage.trim()}
              className="bg-[#24453a] text-white px-6 py-2 rounded hover:bg-[#1a3428] transition-colors disabled:bg-[#d6cebd] disabled:cursor-not-allowed"
            >
              {sendingMessage ? "Sending..." : "Send"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
