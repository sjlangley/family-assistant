import { useState, useEffect, useCallback, useRef } from "react";
import type {
  ConversationSummary,
  Message,
  AssistantAnnotations,
  FailureAnnotation,
  StreamDoneData,
} from "../types/api";
import {
  listConversations,
  getConversationMessages,
  createConversationWithMessage,
  addMessageToConversation,
} from "../lib/api";
import { useAuth } from "../lib/auth";
import { MarkdownContent } from "./MarkdownContent";
import { useStreamingConversation } from "../hooks/useStreamingConversation";

interface ConversationsChatProps {
  onLogout: () => void;
}

function compareMessages(a: Message, b: Message): number {
  const aPersisted = a.sequence_number >= 0;
  const bPersisted = b.sequence_number >= 0;

  if (aPersisted !== bPersisted) {
    return aPersisted ? -1 : 1;
  }

  if (aPersisted && bPersisted && a.sequence_number !== b.sequence_number) {
    return a.sequence_number - b.sequence_number;
  }

  return a.created_at.localeCompare(b.created_at);
}

function mergeTranscriptMessages(
  transcriptMessages: Message[],
  currentMessages: Message[],
): Message[] {
  const merged = [...transcriptMessages];
  const seenIds = new Set(merged.map((message) => message.id));

  for (const message of currentMessages) {
    const isTempMessage = message.id.startsWith("temp-");
    const hasPersistedEquivalent =
      isTempMessage &&
      transcriptMessages.some(
        (transcriptMessage) =>
          transcriptMessage.role === message.role &&
          transcriptMessage.content === message.content,
      );

    if (hasPersistedEquivalent) {
      continue;
    }

    if (!seenIds.has(message.id)) {
      merged.push(message);
      seenIds.add(message.id);
    }
  }

  merged.sort(compareMessages);
  return merged;
}

// Check if annotations have displayable content
function hasAnnotationContent(annotations: AssistantAnnotations): boolean {
  return (
    (annotations.sources?.length ?? 0) > 0 ||
    (annotations.tools?.length ?? 0) > 0 ||
    (annotations.memory_hits?.length ?? 0) > 0 ||
    (annotations.memory_saved?.length ?? 0) > 0 ||
    !!annotations.failure
  );
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
  messageId: string;
  isSelected: boolean;
  onOpenDetails: (messageId: string, triggerElement: HTMLElement) => void;
}

function TrustRow({
  annotations,
  messageId,
  isSelected,
  onOpenDetails,
}: TrustRowProps) {
  const buttonRef = useRef<HTMLButtonElement>(null);

  return (
    <button
      ref={buttonRef}
      onClick={() => {
        if (buttonRef.current) {
          onOpenDetails(messageId, buttonRef.current);
        }
      }}
      className={`trust-row ${isSelected ? "trust-row-active" : ""}`}
      aria-pressed={isSelected}
      aria-label="Open evidence and details"
    >
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
    </button>
  );
}

// FailureRow: Renders failure annotations distinctly
interface FailureRowProps {
  detail: string | null | undefined;
  stage: FailureAnnotation["stage"];
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

// SourceDetail: Renders a single source with title, snippet, and link
interface SourceDetailProps {
  title: string;
  url: string;
  snippet: string;
  rationale: string;
}

function SourceDetail({ title, url, snippet, rationale }: SourceDetailProps) {
  return (
    <div className="evidence-source-item">
      <h4 className="type-body-sm font-medium text-[#1f1c18] mb-1">{title}</h4>
      <p className="type-meta text-[#6e675d] mb-2">{rationale}</p>
      <p className="type-body-sm text-[#1f1c18] mb-2">{snippet}</p>
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="type-meta text-[#24453a] hover:underline focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-[#24453a]"
      >
        View source
      </a>
    </div>
  );
}

// ToolDetail: Renders tool usage information
interface ToolDetailProps {
  name: string;
  status: "requested" | "running" | "completed" | "failed";
}

function ToolDetail({ name, status }: ToolDetailProps) {
  const statusColor =
    status === "completed"
      ? "#2f6b53"
      : status === "failed"
        ? "#a54034"
        : "#315c85";
  const statusLabel =
    status === "completed"
      ? "Completed"
      : status === "failed"
        ? "Failed"
        : status === "running"
          ? "Running"
          : "Requested";

  return (
    <div className="evidence-tool-item">
      <div className="flex items-center gap-2">
        <span
          className="inline-block w-2 h-2 rounded-full"
          style={{ backgroundColor: statusColor }}
          aria-hidden="true"
        />
        <span className="type-meta font-medium" style={{ color: statusColor }}>
          {name}
        </span>
      </div>
      <p className="type-meta text-[#6e675d] mt-1">{statusLabel}</p>
    </div>
  );
}

function StreamingToolStatusRow({
  tools,
}: {
  tools: AssistantAnnotations["tools"];
}) {
  if (tools.length === 0) return null;

  const statusCopy = (tool: AssistantAnnotations["tools"][number]) => {
    if (tool.status === "failed") return `${tool.name} failed`;
    if (tool.status === "completed") return `Used ${tool.name}`;
    return `Using ${tool.name}`;
  };

  return (
    <div className="streaming-tool-status-row" aria-live="polite">
      {tools.map((tool, idx) => (
        <div
          key={tool.id || tool.name + "-" + idx}
          className={`streaming-tool-status streaming-tool-status-${tool.status}`}
        >
          {statusCopy(tool)}
        </div>
      ))}
    </div>
  );
}

// MemoryDetail: Renders memory evidence
interface MemoryDetailProps {
  label: string;
  summary: string;
  type: "hit" | "saved";
}

function MemoryDetail({ label, summary, type }: MemoryDetailProps) {
  return (
    <div className="evidence-memory-item">
      <span className="inline-block px-2 py-1 bg-[#2f6b53] text-white rounded text-xs font-medium mb-2">
        {type === "hit" ? "Memory Hit" : "Memory Saved"}
      </span>
      <h4 className="type-body-sm font-medium text-[#1f1c18] mb-1">{label}</h4>
      <p className="type-meta text-[#6e675d]">{summary}</p>
    </div>
  );
}

// EvidencePanel: Desktop detail surface for evidence display with WCAG modal semantics
interface EvidencePanelProps {
  message: Message;
  onClose: () => void;
  triggerElement?: HTMLElement;
}

function EvidencePanel({
  message,
  onClose,
  triggerElement,
}: EvidencePanelProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  // Manage focus: move to dialog on open, restore to trigger on close
  // Must be called before early returns (React Hooks rule)
  useEffect(() => {
    if (dialogRef.current) {
      // Move focus to close button for keyboard navigation
      closeButtonRef.current?.focus();
    }

    return () => {
      // Restore focus to the trigger element that opened this modal
      if (triggerElement && triggerElement instanceof HTMLElement) {
        triggerElement.focus();
      }
    };
  }, [triggerElement]);

  if (!message.annotations) return null;

  const { annotations } = message;
  const hasContent = hasAnnotationContent(annotations);

  if (!hasContent) return null;

  const content = (
    <div className="evidence-panel-content">
      <div className="evidence-panel-header">
        <h3 className="evidence-panel-title" id="evidence-panel-title">
          Evidence & Details
        </h3>
        <button
          ref={closeButtonRef}
          onClick={onClose}
          className="evidence-panel-close"
          aria-label="Close evidence details"
        >
          ✕
        </button>
      </div>
      <div className="evidence-panel-body">
        {/* Sources */}
        {annotations.sources.length > 0 && (
          <div className="evidence-section">
            <h4 className="evidence-section-title">Sources</h4>
            <div className="evidence-section-content">
              {annotations.sources.map((source, idx) => (
                <SourceDetail
                  key={idx}
                  title={source.title}
                  url={source.url}
                  snippet={source.snippet}
                  rationale={source.rationale}
                />
              ))}
            </div>
          </div>
        )}

        {/* Tools */}
        {annotations.tools.length > 0 && (
          <div className="evidence-section">
            <h4 className="evidence-section-title">Tools Used</h4>
            <div className="evidence-section-content">
              {annotations.tools.map((tool, idx) => (
                <ToolDetail key={idx} name={tool.name} status={tool.status} />
              ))}
            </div>
          </div>
        )}

        {/* Memory Hits */}
        {annotations.memory_hits.length > 0 && (
          <div className="evidence-section">
            <h4 className="evidence-section-title">Memory Hits</h4>
            <div className="evidence-section-content">
              {annotations.memory_hits.map((hit, idx) => (
                <MemoryDetail
                  key={idx}
                  label={hit.label}
                  summary={hit.summary}
                  type="hit"
                />
              ))}
            </div>
          </div>
        )}

        {/* Memory Saved */}
        {annotations.memory_saved.length > 0 && (
          <div className="evidence-section">
            <h4 className="evidence-section-title">Memory Saved</h4>
            <div className="evidence-section-content">
              {annotations.memory_saved.map((saved, idx) => (
                <MemoryDetail
                  key={idx}
                  label={saved.label}
                  summary={saved.summary}
                  type="saved"
                />
              ))}
            </div>
          </div>
        )}

        {/* Failure Details */}
        {annotations.failure && (
          <div className="evidence-section">
            <h4 className="evidence-section-title">Failure Information</h4>
            <div className="evidence-section-content">
              <div className="evidence-failure-item">
                <p className="type-body-sm font-medium text-[#a54034] mb-1">
                  {annotations.failure.stage === "llm"
                    ? "LLM Phase Error"
                    : annotations.failure.stage === "tool"
                      ? "Tool Phase Error"
                      : annotations.failure.stage === "annotation"
                        ? "Processing Error"
                        : "Unknown Error"}
                </p>
                {annotations.failure.detail && (
                  <p className="type-body-sm text-[#1f1c18] mb-2">
                    {annotations.failure.detail}
                  </p>
                )}
                {annotations.failure.retryable && (
                  <p className="type-meta text-[#2f6b53]">
                    This error may be retryable.
                  </p>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div
      className="evidence-panel"
      role="presentation"
      onClick={(e) => {
        // Close when clicking on the overlay background
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-panel-title"
        className="evidence-panel-content"
      >
        {content}
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

  // Evidence panel state
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(
    null,
  );
  const focusTriggerRef = useRef<HTMLElement | null>(null);

  // Track conversations for which we've just set messages to skip redundant fetches
  const skipFetchForConversation = useRef<string | null>(null);
  const pendingStreamMetaRef = useRef<{
    startedWithoutActiveConversation: boolean;
  } | null>(null);
  const streamFailedRef = useRef(false);
  const streamSucceededRef = useRef(false);
  const reconcileRequestIdRef = useRef(0);

  // Get user from authState (it should always be present when component is mounted)
  const user = authState.status === "authenticated" ? authState.user : null;

  // Get the currently selected message for evidence panel
  const selectedMessage = selectedMessageId
    ? messages.find((m) => m.id === selectedMessageId)
    : null;

  // Handle opening evidence details
  const handleOpenDetails = useCallback(
    (messageId: string, triggerElement: HTMLElement) => {
      focusTriggerRef.current = triggerElement;
      setSelectedMessageId(messageId);
    },
    [],
  );

  // Handle closing evidence details
  const handleCloseDetails = useCallback(() => {
    setSelectedMessageId(null);
  }, []);

  // Ref for aria-live announcements
  const statusAnnouncementRef = useRef<HTMLDivElement>(null);
  const prevSendingMessageRef = useRef(false);

  // Announce pending/response status changes for accessibility
  // Only announce "Response received" when sendingMessage transitions from true to false,
  // ensuring we don't announce for historical messages when loading conversations
  useEffect(() => {
    if (!statusAnnouncementRef.current) return;

    if (sendingMessage) {
      statusAnnouncementRef.current.textContent =
        "Thinking... Your question is being processed.";
    } else if (!sendingMessage && prevSendingMessageRef.current) {
      // Just transitioned from sending to not sending - response received
      statusAnnouncementRef.current.textContent = "Response received.";
    }

    prevSendingMessageRef.current = sendingMessage;
  }, [sendingMessage]);

  // Handle Escape key to close evidence panel
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && selectedMessageId) {
        handleCloseDetails();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedMessageId, handleCloseDetails]);

  const refreshConversations = useCallback(async () => {
    try {
      const response = await listConversations();
      setConversations(response.items);
    } catch (err) {
      if (err instanceof Error && err.message === "UNAUTHORIZED") {
        onLogout();
      }
    }
  }, [onLogout]);

  const handleStreamDone = useCallback(
    (doneData: StreamDoneData) => {
      setMessages((prev) => {
        const nextSequence =
          prev.length > 0
            ? Math.max(...prev.map((msg) => msg.sequence_number)) + 1
            : 0;
        return [
          ...prev,
          {
            id: doneData.message_id,
            role: "assistant",
            content: doneData.content,
            sequence_number: nextSequence,
            created_at: new Date().toISOString(),
            error: null,
            annotations: doneData.annotations,
          },
        ];
      });

      const startedWithoutActiveConversation =
        pendingStreamMetaRef.current?.startedWithoutActiveConversation ?? false;

      if (startedWithoutActiveConversation) {
        streamSucceededRef.current = true;
        setInputMessage("");
        setActiveConversationId(doneData.conversation_id);
      } else {
        const reconcileRequestId = ++reconcileRequestIdRef.current;
        void (async () => {
          try {
            const transcript = await getConversationMessages(
              doneData.conversation_id,
            );
            if (reconcileRequestIdRef.current !== reconcileRequestId) {
              return;
            }

            streamSucceededRef.current = true;
            setMessages((prev) =>
              mergeTranscriptMessages(transcript.items, prev),
            );
            setInputMessage("");
          } catch (err) {
            if (err instanceof Error && err.message === "UNAUTHORIZED") {
              onLogout();
            }
          }
        })();
      }
      pendingStreamMetaRef.current = null;
      void refreshConversations();
    },
    [onLogout, refreshConversations],
  );

  const { isStreaming, currentMessage, stream, stop, reset } =
    useStreamingConversation({
      onDone: handleStreamDone,
      onError: (streamError) => {
        streamFailedRef.current = true;
        streamSucceededRef.current = false;
        pendingStreamMetaRef.current = null;
        if (streamError.message === "UNAUTHORIZED") {
          onLogout();
          return;
        }
        setError(streamError.message);
      },
    });

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
    stop();
    reset();
    reconcileRequestIdRef.current += 1;
    streamSucceededRef.current = false;
    setActiveConversationId(null);
    setMessages([]);
    setError(null);
  }, [reset, stop]);

  // Handle conversation selection
  const handleSelectConversation = useCallback(
    (conversationId: string) => {
      stop();
      reset();
      reconcileRequestIdRef.current += 1;
      streamSucceededRef.current = false;
      setActiveConversationId(conversationId);
      setError(null);
    },
    [reset, stop],
  );

  // Update conversations list with new or updated conversation
  const updateConversationsList = useCallback(
    (conversationResponse: {
      conversation: ConversationSummary;
      user_message: Message;
      assistant_message: Message;
    }) => {
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

    // Guard against concurrent sends while request is in flight
    if (sendingMessage || isStreaming) return;

    setSendingMessage(true);
    setError(null);
    streamFailedRef.current = false;
    streamSucceededRef.current = false;

    try {
      const userMessage: Message = {
        id: `temp-user-${Date.now()}`,
        role: "user",
        content: trimmedMessage,
        sequence_number: activeConversationId ? -1 : 1,
        created_at: new Date().toISOString(),
        error: null,
        annotations: null,
      };
      if (activeConversationId) {
        setMessages((prev) => [...prev, userMessage]);
      } else {
        setMessages([userMessage]);
      }

      pendingStreamMetaRef.current = {
        startedWithoutActiveConversation: !activeConversationId,
      };

      // Primary path: stream incremental assistant output.
      await stream(activeConversationId, trimmedMessage, {});
      if (!streamFailedRef.current && streamSucceededRef.current) {
        setInputMessage("");
      }

      // Fallback path for environments or flows where streaming fails.
      if (streamFailedRef.current) {
        setError(null);
        if (activeConversationId) {
          const response = await addMessageToConversation(
            activeConversationId,
            {
              content: trimmedMessage,
            },
          );

          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === userMessage.id ? response.user_message : msg,
            ),
          );
          setMessages((prev) => [...prev, response.assistant_message]);
          updateConversationsList(response);
        } else {
          const response = await createConversationWithMessage({
            content: trimmedMessage,
          });

          updateConversationsList(response);
          skipFetchForConversation.current = response.conversation.id;
          setMessages([response.user_message, response.assistant_message]);
          setActiveConversationId(response.conversation.id);
        }

        setInputMessage("");
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

  const messagesToRender =
    isStreaming && currentMessage ? [...messages, currentMessage] : messages;

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

      {/* Main panel: Messages and composer with optional evidence panel */}
      <div className="flex-1 flex flex-col">
        {/* Accessibility: Announcements for screen readers */}
        <div
          ref={statusAnnouncementRef}
          aria-live="polite"
          aria-atomic="true"
          className="sr-only"
        />

        {/* Messages and evidence container */}
        <div className="flex-1 flex overflow-hidden">
          {/* Messages area */}
          <div className="flex-1 overflow-y-auto p-4">
            {activeConversationId || messagesToRender.length > 0 ? (
              <>
                {transcriptLoading && messages.length === 0 ? (
                  <div className="text-gray-500">Loading messages...</div>
                ) : (
                  <div className="space-y-4 max-w-3xl mx-auto">
                    {messagesToRender.map((msg) => (
                      <div
                        key={msg.id}
                        className={`flex ${
                          msg.role === "user" ? "justify-end" : "justify-start"
                        }`}
                      >
                        <div className="max-w-md">
                          {/* Message bubble */}
                          <div
                            className={`px-4 py-2 rounded-lg ${
                              msg.role === "user"
                                ? "message-user-bubble"
                                : msg.error
                                  ? "message-error-bubble"
                                  : msg.id.startsWith("streaming-")
                                    ? "message-streaming-bubble"
                                    : "message-assistant-bubble"
                            }`}
                          >
                            {msg.role === "assistant" ? (
                              <>
                                {msg.annotations?.thought && (
                                  <div className="thought-trace">
                                    <div className="thought-trace-label">
                                      Thought trace
                                    </div>
                                    <div className="thought-trace-content">
                                      {msg.annotations.thought}
                                    </div>
                                  </div>
                                )}
                                {msg.annotations &&
                                  msg.annotations.tools.length > 0 &&
                                  msg.id.startsWith("streaming-") && (
                                    <StreamingToolStatusRow
                                      tools={msg.annotations.tools}
                                    />
                                  )}
                                <MarkdownContent content={msg.content} />
                              </>
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
                          {msg.role === "assistant" &&
                            msg.annotations &&
                            hasAnnotationContent(msg.annotations) && (
                              <>
                                {msg.annotations.failure ? (
                                  <FailureRow
                                    detail={msg.annotations.failure.detail}
                                    stage={msg.annotations.failure.stage}
                                    retryable={
                                      msg.annotations.failure.retryable
                                    }
                                  />
                                ) : (
                                  <TrustRow
                                    annotations={msg.annotations}
                                    messageId={msg.id}
                                    isSelected={selectedMessageId === msg.id}
                                    onOpenDetails={handleOpenDetails}
                                  />
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

          {/* Evidence panel - desktop right side */}
          {selectedMessage && (
            <EvidencePanel
              message={selectedMessage}
              onClose={handleCloseDetails}
              triggerElement={focusTriggerRef.current ?? undefined}
            />
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
