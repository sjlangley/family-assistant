import { describe, it, expect, vi, beforeEach } from "vitest";
import * as api from "./api";

// Mock fetch globally
const mockFetch = vi.fn();
globalThis.fetch = mockFetch as typeof fetch;

const populatedAssistantAnnotations = {
  sources: [
    {
      title: "Example Source",
      url: "https://example.com",
      snippet: "Example supporting snippet",
      rationale: "Explains why the source matters",
    },
  ],
  tools: [{ name: "web_fetch", status: "completed" as const }],
  memory_hits: [
    {
      label: "Saved family detail",
      summary: "Matched a previously saved fact",
    },
  ],
  memory_saved: [],
  failure: null,
};

describe("API client", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("login", () => {
    it("sends POST request with Bearer token", async () => {
      const mockUser = {
        email: "test@example.com",
        userid: "user-123",
        name: "Test User",
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockUser,
      });

      const result = await api.login("fake-google-token");

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/auth\/login$/),
        expect.objectContaining({
          method: "POST",
          headers: {
            Authorization: "Bearer fake-google-token",
          },
          credentials: "include",
        }),
      );

      expect(result).toEqual(mockUser);
    });

    it("throws error on failed login", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
      });

      await expect(api.login("invalid-token")).rejects.toThrow("Login failed");
    });
  });

  describe("getCurrentUser", () => {
    it("returns user on successful request", async () => {
      const mockUser = {
        email: "test@example.com",
        userid: "user-123",
        name: "Test User",
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockUser,
      });

      const result = await api.getCurrentUser();

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/user\/current$/),
        expect.objectContaining({
          credentials: "include",
          signal: undefined,
        }),
      );

      expect(result).toEqual(mockUser);
    });

    it("returns null on 401 response", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
      });

      const result = await api.getCurrentUser();

      expect(result).toBeNull();
    });

    it("throws error on non-401 failure", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      await expect(api.getCurrentUser()).rejects.toThrow(
        "Failed to fetch current user",
      );
    });
  });

  describe("logout", () => {
    it("sends POST request to logout endpoint", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
      });

      await api.logout();

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/auth\/logout$/),
        expect.objectContaining({
          method: "POST",
          credentials: "include",
        }),
      );
    });

    it("throws error on failed logout", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      await expect(api.logout()).rejects.toThrow("Logout failed");
    });
  });

  describe("listConversations", () => {
    it("returns conversations list on success", async () => {
      const mockResponse = {
        items: [
          {
            id: "conv-1",
            title: "Test Conversation",
            created_at: "2024-01-01T00:00:00Z",
            updated_at: "2024-01-01T00:00:00Z",
          },
        ],
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const result = await api.listConversations();

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/api\/v1\/conversations$/),
        expect.objectContaining({
          credentials: "include",
          signal: undefined,
        }),
      );

      expect(result).toEqual(mockResponse);
    });

    it("throws UNAUTHORIZED error on 401 response", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
      });

      await expect(api.listConversations()).rejects.toThrow("UNAUTHORIZED");
    });

    it("throws error on non-401 failure", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      await expect(api.listConversations()).rejects.toThrow(
        "Failed to fetch conversations",
      );
    });
  });

  describe("getConversationMessages", () => {
    it("returns conversation messages on success", async () => {
      const mockResponse = {
        conversation: {
          id: "conv-1",
          title: "Test Conversation",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        items: [
          {
            id: "msg-1",
            role: "user" as const,
            content: "Hello",
            sequence_number: 1,
            created_at: "2024-01-01T00:00:00Z",
            error: null,
            annotations: null,
          },
          {
            id: "msg-2",
            role: "assistant" as const,
            content: "Hi there!",
            sequence_number: 2,
            created_at: "2024-01-01T00:00:01Z",
            error: null,
            annotations: populatedAssistantAnnotations,
          },
        ],
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const result = await api.getConversationMessages("conv-1");

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/api\/v1\/conversations\/conv-1\/messages$/),
        expect.objectContaining({
          credentials: "include",
          signal: undefined,
        }),
      );

      expect(result).toEqual(mockResponse);
      expect(result.items[0].annotations).toBeNull();
      expect(result.items[1].annotations).toEqual(
        populatedAssistantAnnotations,
      );
    });

    it("throws UNAUTHORIZED error on 401 response", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
      });

      await expect(api.getConversationMessages("conv-1")).rejects.toThrow(
        "UNAUTHORIZED",
      );
    });

    it("throws Conversation not found error on 404 response", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
      });

      await expect(api.getConversationMessages("conv-1")).rejects.toThrow(
        "Conversation not found",
      );
    });

    it("throws error on other failures", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      await expect(api.getConversationMessages("conv-1")).rejects.toThrow(
        "Failed to fetch conversation messages",
      );
    });
  });

  describe("createConversationWithMessage", () => {
    it("creates new conversation with message on success", async () => {
      const mockRequest = { content: "Hello" };
      const mockResponse = {
        conversation: {
          id: "conv-1",
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
          annotations: populatedAssistantAnnotations,
        },
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const result = await api.createConversationWithMessage(mockRequest);

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/api\/v1\/conversations\/with-message$/),
        expect.objectContaining({
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          credentials: "include",
          body: JSON.stringify(mockRequest),
        }),
      );

      expect(result).toEqual(mockResponse);
      expect(result.user_message.annotations).toBeNull();
      expect(result.assistant_message.annotations).toEqual(
        populatedAssistantAnnotations,
      );
    });

    it("throws UNAUTHORIZED error on 401 response", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
      });

      await expect(
        api.createConversationWithMessage({ content: "Hello" }),
      ).rejects.toThrow("UNAUTHORIZED");
    });

    it("throws error on failure", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      await expect(
        api.createConversationWithMessage({ content: "Hello" }),
      ).rejects.toThrow("Failed to create conversation");
    });
  });

  describe("addMessageToConversation", () => {
    it("adds message to existing conversation on success", async () => {
      const mockRequest = { content: "Follow-up question" };
      const mockResponse = {
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
          content: "Here is the answer",
          sequence_number: 4,
          created_at: "2024-01-01T00:01:00Z",
          error: null,
          annotations: null,
        },
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const result = await api.addMessageToConversation("conv-1", mockRequest);

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/api\/v1\/conversations\/conv-1\/messages$/),
        expect.objectContaining({
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          credentials: "include",
          body: JSON.stringify(mockRequest),
        }),
      );

      expect(result).toEqual(mockResponse);
    });

    it("throws UNAUTHORIZED error on 401 response", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
      });

      await expect(
        api.addMessageToConversation("conv-1", { content: "Hello" }),
      ).rejects.toThrow("UNAUTHORIZED");
    });

    it("throws Conversation not found error on 404 response", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
      });

      await expect(
        api.addMessageToConversation("conv-1", { content: "Hello" }),
      ).rejects.toThrow("Conversation not found");
    });

    it("throws error on other failures", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      await expect(
        api.addMessageToConversation("conv-1", { content: "Hello" }),
      ).rejects.toThrow("Failed to add message");
    });
  });

  describe("streamConversation", () => {
    it("yields SSE events from a stream", async () => {
      const mockStream = new ReadableStream({
        start(controller) {
          controller.enqueue(
            new TextEncoder().encode('event: thought\ndata: "Thinking..."\n\n'),
          );
          controller.enqueue(
            new TextEncoder().encode('event: token\ndata: "Hello"\n\n'),
          );
          controller.enqueue(
            new TextEncoder().encode(
              'event: done\ndata: {"message_id": "123", "content": "Hello"}\n\n',
            ),
          );
          controller.close();
        },
      });

      mockFetch.mockResolvedValueOnce({
        ok: true,
        body: mockStream,
      });

      const events = [];
      const generator = api.streamConversation("conv-1", "Hi");
      for await (const event of generator) {
        events.push(event);
      }

      expect(events).toHaveLength(3);
      expect(events[0]).toEqual({ event: "thought", data: "Thinking..." });
      expect(events[1]).toEqual({ event: "token", data: "Hello" });
      expect(events[2].event).toBe("done");
      expect(events[2].data.message_id).toBe("123");
    });

    it("handles fragmented SSE data", async () => {
      const mockStream = new ReadableStream({
        start(controller) {
          controller.enqueue(new TextEncoder().encode("event: thought\n"));
          controller.enqueue(new TextEncoder().encode('data: "Thinking..."\n\n'));
          controller.close();
        },
      });

      mockFetch.mockResolvedValueOnce({
        ok: true,
        body: mockStream,
      });

      const events = [];
      for await (const event of api.streamConversation("conv-1", "Hi")) {
        events.push(event);
      }

      expect(events).toHaveLength(1);
      expect(events[0]).toEqual({ event: "thought", data: "Thinking..." });
    });

    it("handles multi-line SSE data fields", async () => {
      const mockStream = new ReadableStream({
        start(controller) {
          controller.enqueue(
            new TextEncoder().encode('event: token\ndata: {"content":\ndata: " multiline"}\n\n'),
          );
          controller.close();
        },
      });

      mockFetch.mockResolvedValueOnce({
        ok: true,
        body: mockStream,
      });

      const events = [];
      for await (const event of api.streamConversation("conv-1", "Hi")) {
        events.push(event);
      }

      expect(events).toHaveLength(1);
      expect(events[0]).toEqual({
        event: "token",
        data: { content: " multiline" },
      });
    });

    it("throws error when response is not ok", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ detail: "Something went wrong" }),
      });

      const generator = api.streamConversation("conv-1", "Hi");
      await expect(generator.next()).rejects.toThrow("Something went wrong");
    });
  });
});
