import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useStreamingConversation } from "./useStreamingConversation";
import * as api from "../lib/api";

// Mock api
vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    streamConversation: vi.fn(),
  };
});

describe("useStreamingConversation hook", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("handles a complete streaming sequence", async () => {
    const mockEvents = [
      { event: "thought" as const, data: "Thinking..." },
      { event: "token" as const, data: "Hello" },
      { event: "token" as const, data: " world" },
      {
        event: "done" as const,
        data: {
          message_id: "msg-123",
          content: "Hello world",
          annotations: {
            thought: "Thinking...",
            sources: [],
            tools: [],
            memory_hits: [],
            memory_saved: [],
            failure: null,
          },
        },
      },
    ];

    async function* mockGenerator() {
      for (const event of mockEvents) {
        yield event;
      }
    }

    vi.mocked(api.streamConversation).mockReturnValue(mockGenerator() as any);

    const onDone = vi.fn();
    const { result } = renderHook(() => useStreamingConversation({ onDone }));

    expect(result.current.isStreaming).toBe(false);
    expect(result.current.currentMessage).toBeNull();

    let streamPromise: Promise<void> | undefined;
    await act(async () => {
      streamPromise = result.current.stream("conv-1", "Hi");
    });

    await act(async () => {
      await streamPromise;
    });

    expect(result.current.isStreaming).toBe(false);
    expect(result.current.currentMessage?.content).toBe("Hello world");
    expect(result.current.currentMessage?.annotations?.thought).toBe(
      "Thinking...",
    );
    expect(onDone).toHaveBeenCalledWith(mockEvents[3].data);
  });

  it("handles errors during streaming", async () => {
    // eslint-disable-next-line require-yield
    async function* mockGenerator() {
      yield { event: "token" as const, data: "Partial" };
      throw new Error("Stream failed");
    }

    vi.mocked(api.streamConversation).mockReturnValue(mockGenerator() as any);

    const onError = vi.fn();
    const { result } = renderHook(() => useStreamingConversation({ onError }));

    await act(async () => {
      try {
        await result.current.stream("conv-1", "Hi");
      } catch (e) {
        // expected
      }
    });

    expect(result.current.currentMessage?.error).toBe("Stream failed");
    expect(onError).toHaveBeenCalled();
  });

  it("de-duplicates tool call updates by id (falling back to name)", async () => {
    const mockEvents = [
      {
        event: "tool_call" as const,
        data: { id: "call-1", name: "web_search", status: "completed" as const },
      },
      {
        event: "tool_call" as const,
        data: { id: "call-1", name: "web_search", status: "completed" as const }, // Duplicate ID
      },
      {
        event: "tool_call" as const,
        data: { name: "other_tool", status: "completed" as const },
      },
      {
        event: "tool_call" as const,
        data: { name: "other_tool", status: "completed" as const }, // Duplicate name (no ID)
      },
    ];

    async function* mockGenerator() {
      for (const event of mockEvents) {
        yield event;
      }
    }

    vi.mocked(api.streamConversation).mockReturnValue(mockGenerator() as any);

    const { result } = renderHook(() => useStreamingConversation());

    await act(async () => {
      await result.current.stream("conv-1", "Hi");
    });

    expect(result.current.currentMessage?.annotations?.tools).toHaveLength(2);
    expect(result.current.currentMessage?.annotations?.tools).toContainEqual(
      mockEvents[0].data,
    );
    expect(result.current.currentMessage?.annotations?.tools).toContainEqual(
      mockEvents[2].data,
    );
  });

  it("can stop an active stream", async () => {
    const abortSpy = vi.spyOn(AbortController.prototype, "abort");

    // eslint-disable-next-line require-yield
    async function* mockGenerator() {
      yield { event: "token" as const, data: "Never finished" };
      // Simulate long delay
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }

    vi.mocked(api.streamConversation).mockImplementation(
      (_cid, _c, _options) => {
        return mockGenerator() as any;
      },
    );

    const { result } = renderHook(() => useStreamingConversation());

    act(() => {
      // Don't await because it will take 1s
      result.current.stream("conv-1", "Hi");
    });

    expect(result.current.isStreaming).toBe(true);

    act(() => {
      result.current.stop();
    });

    expect(result.current.isStreaming).toBe(false);
    expect(abortSpy).toHaveBeenCalled();
  });
});
