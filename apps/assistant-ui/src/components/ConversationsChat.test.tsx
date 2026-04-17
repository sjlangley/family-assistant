import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConversationsChat } from "./ConversationsChat";
import * as api from "../lib/api";
import { AuthContext } from "../lib/auth";
import type { AuthState } from "../lib/auth";

// Mock API functions
vi.mock("../lib/api", () => ({
  listConversations: vi.fn(),
  getConversationMessages: vi.fn(),
  createConversationWithMessage: vi.fn(),
  addMessageToConversation: vi.fn(),
}));

const mockListConversations = vi.mocked(api.listConversations);
const mockGetConversationMessages = vi.mocked(api.getConversationMessages);
const mockCreateConversationWithMessage = vi.mocked(
  api.createConversationWithMessage,
);
const mockAddMessageToConversation = vi.mocked(api.addMessageToConversation);

// Helper to render component with auth context
function renderWithAuth(
  onLogout: () => void = vi.fn(),
  authState: AuthState = {
    status: "authenticated",
    user: { email: "test@example.com", userid: "user-123", name: "Test User" },
  },
) {
  const authContextValue = {
    authState,
    loginWithGoogle: vi.fn(),
    logout: vi.fn(),
  };

  return render(
    <AuthContext.Provider value={authContextValue}>
      <ConversationsChat onLogout={onLogout} />
    </AuthContext.Provider>,
  );
}

describe("ConversationsChat", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  describe("Initial load", () => {
    it("loads and displays conversations on mount", async () => {
      const mockConversations = {
        items: [
          {
            id: "conv-1",
            title: "First Conversation",
            created_at: "2024-01-01T00:00:00Z",
            updated_at: "2024-01-01T00:00:00Z",
          },
          {
            id: "conv-2",
            title: "Second Conversation",
            created_at: "2024-01-02T00:00:00Z",
            updated_at: "2024-01-02T00:00:00Z",
          },
        ],
      };

      mockListConversations.mockResolvedValueOnce(mockConversations);

      renderWithAuth();

      // Should show loading state initially
      expect(screen.getByText(/loading conversations/i)).toBeInTheDocument();

      // Wait for conversations to load
      await waitFor(() => {
        expect(screen.getByText("First Conversation")).toBeInTheDocument();
      });

      expect(screen.getByText("Second Conversation")).toBeInTheDocument();
      expect(mockListConversations).toHaveBeenCalledOnce();
    });

    it("displays error when conversations fail to load", async () => {
      mockListConversations.mockRejectedValueOnce(
        new Error("Failed to load conversations"),
      );

      renderWithAuth();

      await waitFor(() => {
        expect(
          screen.getByText(/error:.*failed to load conversations/i),
        ).toBeInTheDocument();
      });
    });

    it("displays empty state when no conversations exist", async () => {
      mockListConversations.mockResolvedValueOnce({ items: [] });

      renderWithAuth();

      await waitFor(() => {
        expect(screen.getByText(/no conversations yet/i)).toBeInTheDocument();
      });
    });

    it("calls onLogout when UNAUTHORIZED error occurs", async () => {
      const onLogout = vi.fn();
      mockListConversations.mockRejectedValueOnce(new Error("UNAUTHORIZED"));

      renderWithAuth(onLogout);

      await waitFor(() => {
        expect(onLogout).toHaveBeenCalledOnce();
      });
    });
  });

  describe("New chat flow", () => {
    it("shows welcome message when no conversation is selected", async () => {
      mockListConversations.mockResolvedValueOnce({ items: [] });

      renderWithAuth();

      await waitFor(() => {
        expect(
          screen.getByText(/welcome to family assistant/i),
        ).toBeInTheDocument();
      });

      expect(
        screen.getByText(/select a conversation or start a new chat/i),
      ).toBeInTheDocument();
    });

    it("creates new conversation when sending first message", async () => {
      const user = userEvent.setup();
      mockListConversations.mockResolvedValueOnce({ items: [] });

      const mockResponse = {
        conversation: {
          id: "new-conv",
          title: "New Conversation",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        user_message: {
          id: "msg-1",
          role: "user" as const,
          content: "Hello",
          sequence_number: 1,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: null,
        },
        assistant_message: {
          id: "msg-2",
          role: "assistant" as const,
          content: "Hi there!",
          sequence_number: 2,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: null,
        },
      };

      mockCreateConversationWithMessage.mockResolvedValueOnce(mockResponse);

      renderWithAuth();

      // Wait for initial load
      await waitFor(() => {
        expect(
          screen.getByPlaceholderText(
            /type a message to start a new conversation/i,
          ),
        ).toBeInTheDocument();
      });

      // Type and send message
      const input = screen.getByPlaceholderText(
        /type a message to start a new conversation/i,
      );
      await user.type(input, "Hello");
      await user.click(screen.getByRole("button", { name: /send/i }));

      // Should create new conversation
      await waitFor(() => {
        expect(mockCreateConversationWithMessage).toHaveBeenCalledWith({
          content: "Hello",
        });
      });

      // Should display messages
      expect(screen.getByText("Hello")).toBeInTheDocument();
      expect(screen.getByText("Hi there!")).toBeInTheDocument();

      // Should add conversation to list
      expect(screen.getByText("New Conversation")).toBeInTheDocument();
    });

    it("clears input after sending message", async () => {
      const user = userEvent.setup();
      mockListConversations.mockResolvedValueOnce({ items: [] });

      const mockResponse = {
        conversation: {
          id: "new-conv",
          title: "New Conversation",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        user_message: {
          id: "msg-1",
          role: "user" as const,
          content: "Hello",
          sequence_number: 1,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: null,
        },
        assistant_message: {
          id: "msg-2",
          role: "assistant" as const,
          content: "Hi there!",
          sequence_number: 2,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: null,
        },
      };

      mockCreateConversationWithMessage.mockResolvedValueOnce(mockResponse);

      renderWithAuth();

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText(
            /type a message to start a new conversation/i,
          ),
        ).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText(
        /type a message to start a new conversation/i,
      ) as HTMLInputElement;
      await user.type(input, "Hello");
      await user.click(screen.getByRole("button", { name: /send/i }));

      await waitFor(() => {
        expect(input.value).toBe("");
      });
    });

    it("does not send empty messages", async () => {
      const user = userEvent.setup();
      mockListConversations.mockResolvedValueOnce({ items: [] });

      renderWithAuth();

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText(
            /type a message to start a new conversation/i,
          ),
        ).toBeInTheDocument();
      });

      // Try to send empty message
      const sendButton = screen.getByRole("button", { name: /send/i });
      expect(sendButton).toBeDisabled();

      // Type spaces only
      const input = screen.getByPlaceholderText(
        /type a message to start a new conversation/i,
      );
      await user.type(input, "   ");

      // Button should still be disabled (trimmed message is empty)
      await user.click(sendButton);

      expect(mockCreateConversationWithMessage).not.toHaveBeenCalled();
    });

    it("allows sending message by pressing Enter", async () => {
      const user = userEvent.setup();
      mockListConversations.mockResolvedValueOnce({ items: [] });

      const mockResponse = {
        conversation: {
          id: "new-conv",
          title: "New Conversation",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        user_message: {
          id: "msg-1",
          role: "user" as const,
          content: "Hello via Enter",
          sequence_number: 1,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: null,
        },
        assistant_message: {
          id: "msg-2",
          role: "assistant" as const,
          content: "Response",
          sequence_number: 2,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: null,
        },
      };

      mockCreateConversationWithMessage.mockResolvedValueOnce(mockResponse);

      renderWithAuth();

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText(
            /type a message to start a new conversation/i,
          ),
        ).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText(
        /type a message to start a new conversation/i,
      );
      await user.type(input, "Hello via Enter{Enter}");

      await waitFor(() => {
        expect(mockCreateConversationWithMessage).toHaveBeenCalledWith({
          content: "Hello via Enter",
        });
      });
    });
  });

  describe("Existing conversation flow", () => {
    it("loads and displays messages when conversation is selected", async () => {
      const user = userEvent.setup();

      const mockConversations = {
        items: [
          {
            id: "conv-1",
            title: "Existing Conversation",
            created_at: "2024-01-01T00:00:00Z",
            updated_at: "2024-01-01T00:00:00Z",
          },
        ],
      };

      const mockMessages = {
        conversation: {
          id: "conv-1",
          title: "Existing Conversation",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        items: [
          {
            id: "msg-1",
            role: "user" as const,
            content: "Previous question",
            sequence_number: 1,
            created_at: "2024-01-01T00:00:00Z",
            error: null,
            annotations: null,
          },
          {
            id: "msg-2",
            role: "assistant" as const,
            content: "Previous answer",
            sequence_number: 2,
            created_at: "2024-01-01T00:00:00Z",
            error: null,
            annotations: null,
          },
        ],
      };

      mockListConversations.mockResolvedValueOnce(mockConversations);
      mockGetConversationMessages.mockResolvedValueOnce(mockMessages);

      renderWithAuth();

      // Wait for conversations to load
      await waitFor(() => {
        expect(screen.getByText("Existing Conversation")).toBeInTheDocument();
      });

      // Click on conversation
      await user.click(screen.getByText("Existing Conversation"));

      // Should load and display messages
      await waitFor(() => {
        expect(screen.getByText("Previous question")).toBeInTheDocument();
      });

      expect(screen.getByText("Previous answer")).toBeInTheDocument();
      expect(mockGetConversationMessages).toHaveBeenCalledWith(
        "conv-1",
        expect.any(AbortSignal),
      );
    });

    it("adds message to existing conversation", async () => {
      const user = userEvent.setup();

      const mockConversations = {
        items: [
          {
            id: "conv-1",
            title: "Existing Conversation",
            created_at: "2024-01-01T00:00:00Z",
            updated_at: "2024-01-01T00:00:00Z",
          },
        ],
      };

      const mockMessages = {
        conversation: {
          id: "conv-1",
          title: "Existing Conversation",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        items: [
          {
            id: "msg-1",
            role: "user" as const,
            content: "Previous question",
            sequence_number: 1,
            created_at: "2024-01-01T00:00:00Z",
            error: null,
            annotations: null,
          },
          {
            id: "msg-2",
            role: "assistant" as const,
            content: "Previous answer",
            sequence_number: 2,
            created_at: "2024-01-01T00:00:00Z",
            error: null,
            annotations: null,
          },
        ],
      };

      const mockNewMessageResponse = {
        conversation: {
          id: "conv-1",
          title: "Existing Conversation",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:01:00Z",
        },
        user_message: {
          id: "msg-3",
          role: "user" as const,
          content: "Follow-up question",
          sequence_number: 3,
          created_at: "2024-01-01T00:01:00Z",
          error: null,
          annotations: null,
        },
        assistant_message: {
          id: "msg-4",
          role: "assistant" as const,
          content: "Follow-up answer",
          sequence_number: 4,
          created_at: "2024-01-01T00:01:00Z",
          error: null,
          annotations: null,
        },
      };

      mockListConversations.mockResolvedValueOnce(mockConversations);
      mockGetConversationMessages.mockResolvedValueOnce(mockMessages);
      mockAddMessageToConversation.mockResolvedValueOnce(
        mockNewMessageResponse,
      );

      renderWithAuth();

      // Wait and select conversation
      await waitFor(() => {
        expect(screen.getByText("Existing Conversation")).toBeInTheDocument();
      });
      await user.click(screen.getByText("Existing Conversation"));

      // Wait for messages to load
      await waitFor(() => {
        expect(screen.getByText("Previous question")).toBeInTheDocument();
      });

      // Type and send new message
      const input = screen.getByPlaceholderText(/type your message/i);
      await user.type(input, "Follow-up question");
      await user.click(screen.getByRole("button", { name: /send/i }));

      // Should add message to existing conversation
      await waitFor(() => {
        expect(mockAddMessageToConversation).toHaveBeenCalledWith("conv-1", {
          content: "Follow-up question",
        });
      });

      // Should display new messages
      expect(screen.getByText("Follow-up question")).toBeInTheDocument();
      expect(screen.getByText("Follow-up answer")).toBeInTheDocument();
    });

    it("highlights selected conversation", async () => {
      const user = userEvent.setup();

      const mockConversations = {
        items: [
          {
            id: "conv-1",
            title: "First Conversation",
            created_at: "2024-01-01T00:00:00Z",
            updated_at: "2024-01-01T00:00:00Z",
          },
          {
            id: "conv-2",
            title: "Second Conversation",
            created_at: "2024-01-02T00:00:00Z",
            updated_at: "2024-01-02T00:00:00Z",
          },
        ],
      };

      mockListConversations.mockResolvedValueOnce(mockConversations);
      mockGetConversationMessages.mockResolvedValue({
        conversation: mockConversations.items[0],
        items: [],
      });

      renderWithAuth();

      // Wait for conversations to load
      await waitFor(() => {
        expect(screen.getByText("First Conversation")).toBeInTheDocument();
      });

      // Click on first conversation
      const firstConv = screen
        .getByText("First Conversation")
        .closest("button");
      await user.click(firstConv!);

      // Should have selected styling (raised surface with moss border)
      await waitFor(() => {
        expect(firstConv).toHaveClass("border-r-2");
        expect(firstConv).toHaveClass("border-[#24453a]");
      });
    });
  });

  describe("New Chat button", () => {
    it("clears active conversation when clicked", async () => {
      const user = userEvent.setup();

      const mockConversations = {
        items: [
          {
            id: "conv-1",
            title: "Existing Conversation",
            created_at: "2024-01-01T00:00:00Z",
            updated_at: "2024-01-01T00:00:00Z",
          },
        ],
      };

      const mockMessages = {
        conversation: mockConversations.items[0],
        items: [
          {
            id: "msg-1",
            role: "user" as const,
            content: "Previous question",
            sequence_number: 1,
            created_at: "2024-01-01T00:00:00Z",
            error: null,
            annotations: null,
          },
        ],
      };

      mockListConversations.mockResolvedValueOnce(mockConversations);
      mockGetConversationMessages.mockResolvedValueOnce(mockMessages);

      renderWithAuth();

      // Wait and select conversation
      await waitFor(() => {
        expect(screen.getByText("Existing Conversation")).toBeInTheDocument();
      });
      await user.click(screen.getByText("Existing Conversation"));

      // Wait for messages to load
      await waitFor(() => {
        expect(screen.getByText("Previous question")).toBeInTheDocument();
      });

      // Click New Chat button
      await user.click(screen.getByRole("button", { name: /new chat/i }));

      // Should show welcome message again
      await waitFor(() => {
        expect(
          screen.getByText(/welcome to family assistant/i),
        ).toBeInTheDocument();
      });

      // Previous messages should be cleared
      expect(screen.queryByText("Previous question")).not.toBeInTheDocument();
    });
  });

  describe("Error handling", () => {
    it("displays error message when sending message fails", async () => {
      const user = userEvent.setup();
      mockListConversations.mockResolvedValueOnce({ items: [] });
      mockCreateConversationWithMessage.mockRejectedValueOnce(
        new Error("Network error"),
      );

      renderWithAuth();

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText(
            /type a message to start a new conversation/i,
          ),
        ).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText(
        /type a message to start a new conversation/i,
      );
      await user.type(input, "Hello");
      await user.click(screen.getByRole("button", { name: /send/i }));

      await waitFor(() => {
        expect(screen.getByText(/error:.*network error/i)).toBeInTheDocument();
      });
    });

    it("calls onLogout when message sending returns UNAUTHORIZED", async () => {
      const user = userEvent.setup();
      const onLogout = vi.fn();

      mockListConversations.mockResolvedValueOnce({ items: [] });
      mockCreateConversationWithMessage.mockRejectedValueOnce(
        new Error("UNAUTHORIZED"),
      );

      renderWithAuth(onLogout);

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText(
            /type a message to start a new conversation/i,
          ),
        ).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText(
        /type a message to start a new conversation/i,
      );
      await user.type(input, "Hello");
      await user.click(screen.getByRole("button", { name: /send/i }));

      await waitFor(() => {
        expect(onLogout).toHaveBeenCalledOnce();
      });
    });

    it("displays message with error indicator when LLM fails", async () => {
      const user = userEvent.setup();
      mockListConversations.mockResolvedValueOnce({ items: [] });

      const mockResponse = {
        conversation: {
          id: "new-conv",
          title: "New Conversation",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        user_message: {
          id: "msg-1",
          role: "user" as const,
          content: "Hello",
          sequence_number: 1,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: null,
        },
        assistant_message: {
          id: "msg-2",
          role: "assistant" as const,
          content: "",
          sequence_number: 2,
          created_at: "2024-01-01T00:00:00Z",
          error: "LLM service unavailable",
          annotations: null,
        },
      };

      mockCreateConversationWithMessage.mockResolvedValueOnce(mockResponse);

      // Mock getConversationMessages to return the messages
      mockGetConversationMessages.mockResolvedValueOnce({
        conversation: mockResponse.conversation,
        items: [mockResponse.user_message, mockResponse.assistant_message],
      });

      renderWithAuth();

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText(
            /type a message to start a new conversation/i,
          ),
        ).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText(
        /type a message to start a new conversation/i,
      );
      await user.type(input, "Hello");
      await user.click(screen.getByRole("button", { name: /send/i }));

      // Wait for API call to complete
      await waitFor(() => {
        expect(mockCreateConversationWithMessage).toHaveBeenCalledWith({
          content: "Hello",
        });
      });

      // Should display messages
      await waitFor(() => {
        expect(screen.getByText("Hello")).toBeInTheDocument();
      });
      expect(
        screen.getByText(/error:.*llm service unavailable/i),
      ).toBeInTheDocument();
    });
  });

  describe("Logout", () => {
    it("displays user email and logout button", async () => {
      mockListConversations.mockResolvedValueOnce({ items: [] });

      renderWithAuth();

      await waitFor(() => {
        expect(
          screen.getByText(/logged in as:.*test@example\.com/i),
        ).toBeInTheDocument();
      });

      expect(
        screen.getByRole("button", { name: /logout/i }),
      ).toBeInTheDocument();
    });

    it("calls onLogout when logout button is clicked", async () => {
      const user = userEvent.setup();
      const onLogout = vi.fn();
      mockListConversations.mockResolvedValueOnce({ items: [] });

      renderWithAuth(onLogout);

      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /logout/i }),
        ).toBeInTheDocument();
      });

      await user.click(screen.getByRole("button", { name: /logout/i }));

      expect(onLogout).toHaveBeenCalledOnce();
    });
  });

  describe("Pending assistant placeholder", () => {
    it("sends message and displays user and assistant messages", async () => {
      const user = userEvent.setup({ delay: null });
      mockListConversations.mockResolvedValueOnce({ items: [] });

      const mockResponse = {
        conversation: {
          id: "new-conv",
          title: "New Conversation",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        user_message: {
          id: "msg-1",
          role: "user" as const,
          content: "Hello",
          sequence_number: 1,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: null,
        },
        assistant_message: {
          id: "msg-2",
          role: "assistant" as const,
          content: "Hi there!",
          sequence_number: 2,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: null,
        },
      };

      mockCreateConversationWithMessage.mockResolvedValueOnce(mockResponse);

      renderWithAuth();

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText(
            /type a message to start a new conversation/i,
          ),
        ).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText(
        /type a message to start a new conversation/i,
      );
      await user.type(input, "Hello");
      await user.click(screen.getByRole("button", { name: /send/i }));

      // Should display both messages (pending placeholder handled internally)
      await waitFor(() => {
        expect(screen.getByText("Hello")).toBeInTheDocument();
        expect(screen.getByText("Hi there!")).toBeInTheDocument();
      });

      // Verify the API was called correctly
      expect(mockCreateConversationWithMessage).toHaveBeenCalledWith({
        content: "Hello",
      });
    });
  });

  describe("Trust metadata rendering", () => {
    it("renders trust metadata when assistant message has annotations", async () => {
      const user = userEvent.setup({ delay: null });
      mockListConversations.mockResolvedValueOnce({ items: [] });

      const mockResponse = {
        conversation: {
          id: "new-conv",
          title: "New Conversation",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        user_message: {
          id: "msg-1",
          role: "user" as const,
          content: "What does the web say",
          sequence_number: 1,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: null,
        },
        assistant_message: {
          id: "msg-2",
          role: "assistant" as const,
          content: "Here is what I found...",
          sequence_number: 2,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: {
            sources: [
              {
                title: "Example.com",
                url: "https://example.com",
                snippet: "Sample snippet",
                rationale: "Relevant to query",
              },
            ],
            tools: [{ name: "web_search", status: "completed" as const }],
            memory_hits: [
              { label: "Saved fact", summary: "Previous knowledge" },
            ],
            memory_saved: [],
            failure: null,
          },
        },
      };

      mockCreateConversationWithMessage.mockResolvedValueOnce(mockResponse);

      renderWithAuth();

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText(
            /type a message to start a new conversation/i,
          ),
        ).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText(
        /type a message to start a new conversation/i,
      );
      await user.type(input, "What does the web say");
      await user.click(screen.getByRole("button", { name: /send/i }));

      // Should display trust metadata
      await waitFor(() => {
        expect(screen.getByText(/web_search/)).toBeInTheDocument();
        expect(screen.getByText(/Here is what I found/)).toBeInTheDocument();
        // Check for the trust pills by finding text pattern that's unique
        const trustPills = screen.getAllByText(/Tools|Sources|Memory/);
        expect(trustPills.length).toBeGreaterThan(0);
      });
    });

    it("does not render trust row when annotations are null", async () => {
      const user = userEvent.setup({ delay: null });
      mockListConversations.mockResolvedValueOnce({ items: [] });

      const mockResponse = {
        conversation: {
          id: "new-conv",
          title: "New Conversation",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        user_message: {
          id: "msg-1",
          role: "user" as const,
          content: "Hello",
          sequence_number: 1,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: null,
        },
        assistant_message: {
          id: "msg-2",
          role: "assistant" as const,
          content: "Hi there!",
          sequence_number: 2,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: null,
        },
      };

      mockCreateConversationWithMessage.mockResolvedValueOnce(mockResponse);

      renderWithAuth();

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText(
            /type a message to start a new conversation/i,
          ),
        ).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText(
        /type a message to start a new conversation/i,
      );
      await user.type(input, "Hello");
      await user.click(screen.getByRole("button", { name: /send/i }));

      await waitFor(() => {
        expect(screen.getByText("Hi there!")).toBeInTheDocument();
      });

      // Should not render trust metadata when annotations is null
      expect(screen.queryByText(/Tools/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Sources/)).not.toBeInTheDocument();
    });

    it("renders partial annotations safely", async () => {
      const user = userEvent.setup({ delay: null });
      mockListConversations.mockResolvedValueOnce({ items: [] });

      const mockResponse = {
        conversation: {
          id: "new-conv",
          title: "New Conversation",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        user_message: {
          id: "msg-1",
          role: "user" as const,
          content: "What time is it",
          sequence_number: 1,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: null,
        },
        assistant_message: {
          id: "msg-2",
          role: "assistant" as const,
          content: "The current time is...",
          sequence_number: 2,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: {
            sources: [],
            tools: [{ name: "get_current_time", status: "completed" as const }],
            memory_hits: [],
            memory_saved: [],
            failure: null,
          },
        },
      };

      mockCreateConversationWithMessage.mockResolvedValueOnce(mockResponse);

      renderWithAuth();

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText(
            /type a message to start a new conversation/i,
          ),
        ).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText(
        /type a message to start a new conversation/i,
      );
      await user.type(input, "What time is it");
      await user.click(screen.getByRole("button", { name: /send/i }));

      // Should render only available annotations (tools, not sources/memory)
      await waitFor(() => {
        expect(screen.getByText(/Tools/)).toBeInTheDocument();
        expect(screen.getByText(/get_current_time/)).toBeInTheDocument();
        expect(screen.queryByText(/Sources/)).not.toBeInTheDocument();
        expect(screen.queryByText(/Memory/)).not.toBeInTheDocument();
      });
    });

    it("renders failure annotations distinctly", async () => {
      const user = userEvent.setup({ delay: null });
      mockListConversations.mockResolvedValueOnce({ items: [] });

      const failureAnnotation = {
        sources: [] as never[],
        tools: [] as never[],
        memory_hits: [] as never[],
        memory_saved: [] as never[],
        failure: {
          stage: "tool" as const,
          retryable: true,
          detail: "Web search service timeout",
        },
      };

      const mockResponse = {
        conversation: {
          id: "new-conv",
          title: "New Conversation",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        user_message: {
          id: "msg-1",
          role: "user" as const,
          content: "Search the web",
          sequence_number: 1,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: null,
        },
        assistant_message: {
          id: "msg-2",
          role: "assistant" as const,
          content: "I encountered an error",
          sequence_number: 2,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: failureAnnotation,
        },
      };

      mockCreateConversationWithMessage.mockResolvedValueOnce(mockResponse);

      renderWithAuth();

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText(
            /type a message to start a new conversation/i,
          ),
        ).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText(
        /type a message to start a new conversation/i,
      );
      await user.type(input, "Search the web");
      await user.click(screen.getByRole("button", { name: /send/i }));

      // Should render failure row with error icon and details
      await waitFor(() => {
        expect(screen.getByText(/Tool error/)).toBeInTheDocument();
        expect(
          screen.getByText(/Web search service timeout/),
        ).toBeInTheDocument();
        expect(screen.getByText(/retryable/i)).toBeInTheDocument();
      });
    });
  });

  describe("Detail components - SourceDetail", () => {
    it("renders source detail with title, snippet, rationale, and link", async () => {
      const user = userEvent.setup({ delay: null });
      mockListConversations.mockResolvedValueOnce({ items: [] });

      const mockResponse = {
        conversation: {
          id: "new-conv",
          title: "New Conversation",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        user_message: {
          id: "msg-1",
          role: "user" as const,
          content: "Tell me about React",
          sequence_number: 1,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: null,
        },
        assistant_message: {
          id: "msg-2",
          role: "assistant" as const,
          content: "React is a JavaScript library...",
          sequence_number: 2,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: {
            sources: [
              {
                title: "React Official Docs",
                url: "https://react.dev",
                snippet: "A JavaScript library for building UIs",
                rationale: "Official documentation provides accurate information",
              },
            ],
            tools: [],
            memory_hits: [],
            memory_saved: [],
            failure: null,
          },
        },
      };

      mockCreateConversationWithMessage.mockResolvedValueOnce(mockResponse);

      renderWithAuth();

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText(
            /type a message to start a new conversation/i,
          ),
        ).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText(
        /type a message to start a new conversation/i,
      );
      await user.type(input, "Tell me about React");
      await user.click(screen.getByRole("button", { name: /send/i }));

      // Open evidence panel
      await waitFor(() => {
        const trustRowButton = screen.queryByRole("button", {
          name: /open evidence/i,
        });
        if (trustRowButton) {
          userEvent.click(trustRowButton);
        }
      });

      // Should render source details
      await waitFor(() => {
        expect(screen.getByText(/React Official Docs/)).toBeInTheDocument();
        expect(
          screen.getByText(/A JavaScript library for building UIs/),
        ).toBeInTheDocument();
        expect(
          screen.getByText(
            /Official documentation provides accurate information/,
          ),
        ).toBeInTheDocument();
      });

      // Should have a link to the source
      const sourceLink = screen.getByRole("link", { name: /view source/i });
      expect(sourceLink).toHaveAttribute("href", "https://react.dev");
      expect(sourceLink).toHaveAttribute("target", "_blank");
      expect(sourceLink).toHaveAttribute("rel", "noopener noreferrer");
    });
  });

  describe("Detail components - ToolDetail", () => {
    it("renders tool in trust metadata with completed status", async () => {
      const user = userEvent.setup({ delay: null });
      mockListConversations.mockResolvedValueOnce({ items: [] });

      const mockResponse = {
        conversation: {
          id: "new-conv",
          title: "New Conversation",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        user_message: {
          id: "msg-1",
          role: "user" as const,
          content: "What is the weather",
          sequence_number: 1,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: null,
        },
        assistant_message: {
          id: "msg-2",
          role: "assistant" as const,
          content: "The weather is clear",
          sequence_number: 2,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: {
            sources: [],
            tools: [{ name: "weather_api", status: "completed" as const }],
            memory_hits: [],
            memory_saved: [],
            failure: null,
          },
        },
      };

      mockCreateConversationWithMessage.mockResolvedValueOnce(mockResponse);

      renderWithAuth();

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText(
            /type a message to start a new conversation/i,
          ),
        ).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText(
        /type a message to start a new conversation/i,
      );
      await user.type(input, "What is the weather");
      await user.click(screen.getByRole("button", { name: /send/i }));

      // Should render tool metadata pill in trust row
      await waitFor(() => {
        expect(screen.getByText(/weather_api/)).toBeInTheDocument();
        expect(screen.getByText(/Tools/)).toBeInTheDocument();
      });
    });

    it("renders failed tool in trust metadata", async () => {
      const user = userEvent.setup({ delay: null });
      mockListConversations.mockResolvedValueOnce({ items: [] });

      const mockResponse = {
        conversation: {
          id: "new-conv",
          title: "New Conversation",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        user_message: {
          id: "msg-1",
          role: "user" as const,
          content: "Search for something",
          sequence_number: 1,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: null,
        },
        assistant_message: {
          id: "msg-2",
          role: "assistant" as const,
          content: "Tool failed",
          sequence_number: 2,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: {
            sources: [],
            tools: [{ name: "web_search", status: "failed" as const }],
            memory_hits: [],
            memory_saved: [],
            failure: null,
          },
        },
      };

      mockCreateConversationWithMessage.mockResolvedValueOnce(mockResponse);

      renderWithAuth();

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText(
            /type a message to start a new conversation/i,
          ),
        ).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText(
        /type a message to start a new conversation/i,
      );
      await user.type(input, "Search for something");
      await user.click(screen.getByRole("button", { name: /send/i }));

      // Should render tool metadata in trust row (including failed tool)
      await waitFor(() => {
        expect(screen.getByText(/web_search/)).toBeInTheDocument();
        expect(screen.getByText(/Tools/)).toBeInTheDocument();
      });
    });
  });

  describe("Detail components - MemoryDetail", () => {
    it("renders memory in trust metadata as memory hit", async () => {
      const user = userEvent.setup({ delay: null });
      mockListConversations.mockResolvedValueOnce({ items: [] });

      const mockResponse = {
        conversation: {
          id: "new-conv",
          title: "New Conversation",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        user_message: {
          id: "msg-1",
          role: "user" as const,
          content: "Remind me of the plan",
          sequence_number: 1,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: null,
        },
        assistant_message: {
          id: "msg-2",
          role: "assistant" as const,
          content: "Here is the plan we discussed",
          sequence_number: 2,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: {
            sources: [],
            tools: [],
            memory_hits: [
              {
                label: "Team meeting schedule",
                summary: "Weekly meetings on Mondays at 10 AM",
              },
            ],
            memory_saved: [],
            failure: null,
          },
        },
      };

      mockCreateConversationWithMessage.mockResolvedValueOnce(mockResponse);

      renderWithAuth();

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText(
            /type a message to start a new conversation/i,
          ),
        ).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText(
        /type a message to start a new conversation/i,
      );
      await user.type(input, "Remind me of the plan");
      await user.click(screen.getByRole("button", { name: /send/i }));

      // Should render memory in trust metadata
      await waitFor(() => {
        expect(screen.getByText(/Memory/)).toBeInTheDocument();
        expect(screen.getByText("1")).toBeInTheDocument(); // memory count
      });
    });

    it("renders memory in trust metadata as memory saved", async () => {
      const user = userEvent.setup({ delay: null });
      mockListConversations.mockResolvedValueOnce({ items: [] });

      const mockResponse = {
        conversation: {
          id: "new-conv",
          title: "New Conversation",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        user_message: {
          id: "msg-1",
          role: "user" as const,
          content: "Remember this for later",
          sequence_number: 1,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: null,
        },
        assistant_message: {
          id: "msg-2",
          role: "assistant" as const,
          content: "Got it, I saved that",
          sequence_number: 2,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: {
            sources: [],
            tools: [],
            memory_hits: [],
            memory_saved: [
              {
                label: "User preference",
                summary: "Prefers evening meetings",
              },
            ],
            failure: null,
          },
        },
      };

      mockCreateConversationWithMessage.mockResolvedValueOnce(mockResponse);

      renderWithAuth();

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText(
            /type a message to start a new conversation/i,
          ),
        ).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText(
        /type a message to start a new conversation/i,
      );
      await user.type(input, "Remember this for later");
      await user.click(screen.getByRole("button", { name: /send/i }));

      // Should render saved memory in trust metadata
      await waitFor(() => {
        expect(screen.getByText(/Saved/)).toBeInTheDocument();
        expect(screen.getByText("1")).toBeInTheDocument(); // saved memory count
      });
    });
  });

  describe("Detail components - Complex annotations", () => {
    it("renders all annotation types together in evidence panel", async () => {
      const user = userEvent.setup({ delay: null });
      mockListConversations.mockResolvedValueOnce({ items: [] });

      const mockResponse = {
        conversation: {
          id: "new-conv",
          title: "New Conversation",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        user_message: {
          id: "msg-1",
          role: "user" as const,
          content: "Complex query",
          sequence_number: 1,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: null,
        },
        assistant_message: {
          id: "msg-2",
          role: "assistant" as const,
          content: "Complex response",
          sequence_number: 2,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: {
            sources: [
              {
                title: "Page A",
                url: "https://example.com/a",
                snippet: "Content A",
                rationale: "Relevant",
              },
              {
                title: "Page B",
                url: "https://example.com/b",
                snippet: "Content B",
                rationale: "Related",
              },
            ],
            tools: [
              { name: "web_search", status: "completed" as const },
              { name: "memory_lookup", status: "completed" as const },
            ],
            memory_hits: [
              { label: "Fact 1", summary: "Summary 1" },
              { label: "Fact 2", summary: "Summary 2" },
            ],
            memory_saved: [
              { label: "New fact", summary: "New summary" },
            ],
            failure: null,
          },
        },
      };

      mockCreateConversationWithMessage.mockResolvedValueOnce(mockResponse);

      renderWithAuth();

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText(
            /type a message to start a new conversation/i,
          ),
        ).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText(
        /type a message to start a new conversation/i,
      );
      await user.type(input, "Complex query");
      await user.click(screen.getByRole("button", { name: /send/i }));

      // Should show compact trust metadata
      await waitFor(() => {
        expect(screen.getByText(/Tools/)).toBeInTheDocument();
        expect(screen.getByText(/Sources/)).toBeInTheDocument();
        expect(screen.getByText(/Memory/)).toBeInTheDocument();
        expect(screen.getByText(/Saved/)).toBeInTheDocument();
      });
    });

    it("does not render trust row when all annotations are empty", async () => {
      const user = userEvent.setup({ delay: null });
      mockListConversations.mockResolvedValueOnce({ items: [] });

      const mockResponse = {
        conversation: {
          id: "new-conv",
          title: "New Conversation",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        user_message: {
          id: "msg-1",
          role: "user" as const,
          content: "Simple question",
          sequence_number: 1,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: null,
        },
        assistant_message: {
          id: "msg-2",
          role: "assistant" as const,
          content: "Simple answer",
          sequence_number: 2,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: {
            sources: [],
            tools: [],
            memory_hits: [],
            memory_saved: [],
            failure: null,
          },
        },
      };

      mockCreateConversationWithMessage.mockResolvedValueOnce(mockResponse);

      renderWithAuth();

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText(
            /type a message to start a new conversation/i,
          ),
        ).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText(
        /type a message to start a new conversation/i,
      );
      await user.type(input, "Simple question");
      await user.click(screen.getByRole("button", { name: /send/i }));

      await waitFor(() => {
        expect(screen.getByText("Simple answer")).toBeInTheDocument();
      });

      // Should not render any trust metadata
      expect(screen.queryByText(/Tools/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Sources/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Memory/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Saved/)).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /open evidence/i }),
      ).not.toBeInTheDocument();
    });
  });

  describe("Failure scenarios", () => {
    it("handles LLM stage failure", async () => {
      const user = userEvent.setup({ delay: null });
      mockListConversations.mockResolvedValueOnce({ items: [] });

      const mockResponse = {
        conversation: {
          id: "new-conv",
          title: "New Conversation",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        user_message: {
          id: "msg-1",
          role: "user" as const,
          content: "Ask question",
          sequence_number: 1,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: null,
        },
        assistant_message: {
          id: "msg-2",
          role: "assistant" as const,
          content: "LLM error occurred",
          sequence_number: 2,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: {
            sources: [],
            tools: [],
            memory_hits: [],
            memory_saved: [],
            failure: {
              stage: "llm" as const,
              retryable: false,
              detail: "Model overloaded",
            },
          },
        },
      };

      mockCreateConversationWithMessage.mockResolvedValueOnce(mockResponse);

      renderWithAuth();

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText(
            /type a message to start a new conversation/i,
          ),
        ).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText(
        /type a message to start a new conversation/i,
      );
      await user.type(input, "Ask question");
      await user.click(screen.getByRole("button", { name: /send/i }));

      // Should render failure information - search for detail text which is unique
      await waitFor(() => {
        expect(screen.getByText(/Model overloaded/)).toBeInTheDocument();
      });
    });

    it("handles annotation stage failure", async () => {
      const user = userEvent.setup({ delay: null });
      mockListConversations.mockResolvedValueOnce({ items: [] });

      const mockResponse = {
        conversation: {
          id: "new-conv",
          title: "New Conversation",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        user_message: {
          id: "msg-1",
          role: "user" as const,
          content: "Another question",
          sequence_number: 1,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: null,
        },
        assistant_message: {
          id: "msg-2",
          role: "assistant" as const,
          content: "Response with annotation error",
          sequence_number: 2,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: {
            sources: [],
            tools: [],
            memory_hits: [],
            memory_saved: [],
            failure: {
              stage: "annotation" as const,
              retryable: true,
              detail: "Memory service temporary failure",
            },
          },
        },
      };

      mockCreateConversationWithMessage.mockResolvedValueOnce(mockResponse);

      renderWithAuth();

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText(
            /type a message to start a new conversation/i,
          ),
        ).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText(
        /type a message to start a new conversation/i,
      );
      await user.type(input, "Another question");
      await user.click(screen.getByRole("button", { name: /send/i }));

      await waitFor(() => {
        expect(
          screen.getByText(/Memory service temporary failure/),
        ).toBeInTheDocument();
        expect(screen.getByText(/retryable/i)).toBeInTheDocument();
      });
    });
  });

  describe("Accessibility features", () => {
    it("renders aria-live region for screen reader announcements", () => {
      mockListConversations.mockResolvedValueOnce({ items: [] });

      const { container } = renderWithAuth();

      // Verify aria-live region exists with correct attributes
      const statusAnnouncement = container.querySelector(
        '[aria-live="polite"]',
      );
      expect(statusAnnouncement).toBeInTheDocument();
      expect(statusAnnouncement).toHaveAttribute("aria-atomic", "true");
      expect(statusAnnouncement).toHaveClass("sr-only");
    });

    it("renders trust row button with proper accessibility attributes", async () => {
      const user = userEvent.setup({ delay: null });
      mockListConversations.mockResolvedValueOnce({ items: [] });

      const mockResponse = {
        conversation: {
          id: "new-conv",
          title: "New Conversation",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        user_message: {
          id: "msg-1",
          role: "user" as const,
          content: "Test",
          sequence_number: 1,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: null,
        },
        assistant_message: {
          id: "msg-2",
          role: "assistant" as const,
          content: "Response",
          sequence_number: 2,
          created_at: "2024-01-01T00:00:00Z",
          error: null,
          annotations: {
            sources: [
              {
                title: "Source",
                url: "https://example.com",
                snippet: "Text",
                rationale: "Reason",
              },
            ],
            tools: [],
            memory_hits: [],
            memory_saved: [],
            failure: null,
          },
        },
      };

      mockCreateConversationWithMessage.mockResolvedValueOnce(mockResponse);

      renderWithAuth();

      await waitFor(() => {
        expect(
          screen.getByPlaceholderText(
            /type a message to start a new conversation/i,
          ),
        ).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText(
        /type a message to start a new conversation/i,
      );
      await user.type(input, "Test");
      await user.click(screen.getByRole("button", { name: /send/i }));

      // Check for trust row button with proper ARIA attributes
      await waitFor(() => {
        const trustButton = screen.getByRole("button", {
          name: /open evidence/i,
        });
        expect(trustButton).toHaveAttribute("aria-pressed", "false");
      });
    });
  });
});
