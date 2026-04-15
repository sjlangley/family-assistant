/**
 * Chat component for authenticated conversations
 * Displays message history and handles user input
 */

import {
  useState,
  useCallback,
  useRef,
  useEffect,
  type FormEvent,
} from "react";
import type { ChatMessage } from "../types/api";
import * as api from "../lib/api";
import { MarkdownContent } from "./MarkdownContent";

interface Message extends ChatMessage {
  id: string;
  status?: "sending" | "sent" | "error";
}

interface ChatProps {
  onAuthError: () => void;
}

export function Chat({ onAuthError }: ChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();

      // Prevent empty submissions
      const trimmedInput = input.trim();
      if (!trimmedInput || isSubmitting) {
        return;
      }

      // Clear any previous errors
      setError(null);

      // Create user message
      const userMessage: Message = {
        id: `user-${crypto.randomUUID()}`,
        role: "user",
        content: trimmedInput,
        status: "sent",
      };

      // Add user message to UI
      setMessages((prev) => [...prev, userMessage]);
      setInput("");
      setIsSubmitting(true);

      try {
        // Send to backend (exclude failed messages from history)
        const response = await api.sendChatCompletion({
          messages: [
            ...messages
              .filter((m) => m.status !== "error")
              .map((m) => ({ role: m.role, content: m.content })),
            { role: "user", content: trimmedInput },
          ],
        });

        // Add assistant response
        const assistantMessage: Message = {
          id: `assistant-${crypto.randomUUID()}`,
          role: "assistant",
          content: response.content,
          status: "sent",
        };

        setMessages((prev) => [...prev, assistantMessage]);
      } catch (err) {
        // Handle auth errors
        if (err instanceof Error && err.message === "UNAUTHORIZED") {
          onAuthError();
          return;
        }

        // Handle other errors gracefully
        const errorMessage =
          err instanceof Error ? err.message : "Something went wrong";
        setError(`Failed to send message: ${errorMessage}. Please try again.`);

        // Mark user message as error
        setMessages((prev) =>
          prev.map((m) =>
            m.id === userMessage.id ? { ...m, status: "error" } : m,
          ),
        );
      } finally {
        setIsSubmitting(false);
      }
    },
    [input, isSubmitting, messages, onAuthError],
  );

  return (
    <div className="flex flex-col h-full" data-testid="chat-container">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto mb-4 space-y-4">
        {messages.length === 0 ? (
          <div
            className="text-center text-gray-500 mt-8"
            data-testid="empty-state"
          >
            Start a conversation by typing a message below.
          </div>
        ) : (
          messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
              data-testid={`message-${message.role}`}
            >
              <div
                className={`max-w-[80%] rounded-lg px-4 py-2 ${
                  message.role === "user"
                    ? "bg-blue-600 text-white"
                    : "bg-gray-200 text-gray-900"
                } ${message.status === "error" ? "opacity-50" : ""}`}
              >
                {message.role === "assistant" ? (
                  <MarkdownContent
                    content={message.content}
                    className="text-sm break-words"
                  />
                ) : (
                  <div className="text-sm whitespace-pre-wrap break-words">
                    {message.content}
                  </div>
                )}
                {message.status === "error" && (
                  <div className="text-xs mt-1 text-red-200">
                    Failed to send
                  </div>
                )}
              </div>
            </div>
          ))
        )}
        {isSubmitting && (
          <div className="flex justify-start" data-testid="loading-message">
            <div className="bg-gray-200 text-gray-900 rounded-lg px-4 py-2">
              <div className="text-sm">Thinking...</div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Error display */}
      {error && (
        <div
          className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm"
          data-testid="error-message"
        >
          {error}
        </div>
      )}

      {/* Input area */}
      <form onSubmit={handleSubmit} data-testid="chat-form">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type your message..."
            disabled={isSubmitting}
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
            data-testid="chat-input"
            autoComplete="off"
          />
          <button
            type="submit"
            disabled={isSubmitting || !input.trim()}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
            data-testid="chat-submit"
          >
            {isSubmitting ? "Sending..." : "Send"}
          </button>
        </div>
      </form>
    </div>
  );
}
