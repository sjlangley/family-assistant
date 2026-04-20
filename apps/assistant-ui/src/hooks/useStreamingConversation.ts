import { useState, useCallback, useRef, useEffect } from "react";
import {
  Message,
  SSEEvent,
  StreamDoneData,
  AssistantAnnotations,
  ToolAnnotation,
} from "../types/api";
import { streamConversation } from "../lib/api";

export interface UseStreamingConversationOptions {
  onDone?: (data: StreamDoneData) => void;
  onError?: (error: Error) => void;
}

export interface UseStreamingConversationResult {
  isStreaming: boolean;
  currentMessage: Message | null;
  error: Error | null;
  stream: (
    conversationId: string | null,
    content: string,
    options?: { temperature?: number; max_tokens?: number },
  ) => Promise<void>;
  stop: () => void;
  reset: () => void;
}

/**
 * Hook to handle streaming conversation responses.
 * Encapsulates SSE consumption and transient state management for the message being streamed.
 */
export function useStreamingConversation(
  options?: UseStreamingConversationOptions,
): UseStreamingConversationResult {
  const [isStreaming, setIsStreaming] = useState(false);
  const [currentMessage, setCurrentMessage] = useState<Message | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Store options in a ref to stabilize the stream callback
  const optionsRef = useRef(options);
  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

  const reset = useCallback(() => {
    setCurrentMessage(null);
    setError(null);
    setIsStreaming(false);
  }, []);

  const stop = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);
  }, []);

  const stream = useCallback(
    async (
      conversationId: string | null,
      content: string,
      streamOptions?: { temperature?: number; max_tokens?: number },
    ) => {
      // Cancel any existing stream
      stop();

      const controller = new AbortController();
      abortControllerRef.current = controller;

      setIsStreaming(true);
      setError(null);

      // Initialize empty assistant message placeholder
      const initialMessage: Message = {
        id: `streaming-${crypto.randomUUID()}`,
        role: "assistant",
        content: "",
        sequence_number: -1,
        created_at: new Date().toISOString(),
        error: null,
        annotations: {
          thought: null,
          sources: [],
          tools: [],
          memory_hits: [],
          memory_saved: [],
          failure: null,
        },
      };
      setCurrentMessage(initialMessage);

      let accumulatedContent = "";
      let accumulatedThought = "";
      let currentAnnotations: AssistantAnnotations = {
        ...initialMessage.annotations!,
      };

      try {
        const eventGenerator = streamConversation(conversationId, content, {
          ...streamOptions,
          signal: controller.signal,
        });

        for await (const event of eventGenerator) {
          switch (event.event) {
            case "thought":
              accumulatedThought += event.data;
              currentAnnotations = {
                ...currentAnnotations,
                thought: accumulatedThought,
              };
              setCurrentMessage((prev) =>
                prev ? { ...prev, annotations: { ...currentAnnotations } } : null,
              );
              break;

            case "token":
              accumulatedContent += event.data;
              setCurrentMessage((prev) =>
                prev ? { ...prev, content: accumulatedContent } : null,
              );
              break;

            case "tool_call":
              // Transient tool call updates. data might be a single ToolAnnotation or an array.
              if (event.data) {
                const incomingTools: ToolAnnotation[] = Array.isArray(event.data)
                  ? event.data
                  : [event.data];

                // De-duplicate by ID (falling back to name): new updates for the same tool replace existing ones.
                const toolMap = new Map<string, ToolAnnotation>();
                currentAnnotations.tools.forEach((t) =>
                  toolMap.set(t.id || t.name, t),
                );
                incomingTools.forEach((t) => toolMap.set(t.id || t.name, t));

                currentAnnotations = {
                  ...currentAnnotations,
                  tools: Array.from(toolMap.values()),
                };
                setCurrentMessage((prev) =>
                  prev
                    ? { ...prev, annotations: { ...currentAnnotations } }
                    : null,
                );
              }
              break;

            case "done":
              const doneData = event.data as StreamDoneData;
              const finalMessage: Message = {
                id: doneData.message_id,
                role: "assistant",
                content: doneData.content,
                annotations: doneData.annotations,
                created_at: new Date().toISOString(),
                sequence_number: 0, // Backend sequence number would be ideal here
                error: null,
              };
              setCurrentMessage(finalMessage);
              setIsStreaming(false);
              optionsRef.current?.onDone?.(doneData);
              return; // End of stream

            case "error":
              throw new Error(event.data.detail || "Streaming error");

            default:
              console.warn(`Unknown SSE event type: ${event.event}`);
          }
        }
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          return;
        }

        const streamError =
          err instanceof Error ? err : new Error(String(err));
        setError(streamError);

        setCurrentMessage((prev) =>
          prev ? { ...prev, error: streamError.message } : null,
        );

        optionsRef.current?.onError?.(streamError);
      } finally {
        setIsStreaming(false);
        if (abortControllerRef.current === controller) {
          abortControllerRef.current = null;
        }
      }
    },
    [stop],
  );

  return {
    isStreaming,
    currentMessage,
    error,
    stream,
    stop,
    reset,
  };
}
