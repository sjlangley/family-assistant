/**
 * Tests for Chat component
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Chat } from "./Chat";
import * as api from "../lib/api";
import type { ChatResponse } from "../types/api";

// Mock the API module
vi.mock("../lib/api");

describe("Chat", () => {
  const mockOnAuthError = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders empty state initially", () => {
    render(<Chat onAuthError={mockOnAuthError} />);

    expect(
      screen.getByText(/Start a conversation by typing a message below/i),
    ).toBeInTheDocument();
    expect(screen.getByTestId("chat-input")).toBeInTheDocument();
    expect(screen.getByTestId("chat-submit")).toBeInTheDocument();
  });

  it("accepts text input", async () => {
    const user = userEvent.setup();
    render(<Chat onAuthError={mockOnAuthError} />);

    const input = screen.getByTestId("chat-input");
    await user.type(input, "Hello");

    expect(input).toHaveValue("Hello");
  });

  it("does not submit blank prompts", async () => {
    const user = userEvent.setup();
    const sendSpy = vi.spyOn(api, "sendChatCompletion");

    render(<Chat onAuthError={mockOnAuthError} />);

    const input = screen.getByTestId("chat-input");
    const submitButton = screen.getByTestId("chat-submit");

    // Submit button should be disabled when input is empty
    expect(submitButton).toBeDisabled();

    // Try submitting whitespace-only
    await user.type(input, "   ");
    expect(submitButton).toBeDisabled();

    expect(sendSpy).not.toHaveBeenCalled();
  });

  it("does not submit whitespace-only prompts on form submit", async () => {
    const user = userEvent.setup();
    const sendSpy = vi.spyOn(api, "sendChatCompletion");

    render(<Chat onAuthError={mockOnAuthError} />);

    const input = screen.getByTestId("chat-input");
    await user.type(input, "   ");

    // Force form submission
    const form = screen.getByTestId("chat-form");
    form.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );

    expect(sendSpy).not.toHaveBeenCalled();
  });

  it("displays user message and assistant response on successful request", async () => {
    const user = userEvent.setup();
    const mockResponse = {
      content: "Hello! How can I help you?",
      model: "test-model",
    };

    vi.mocked(api.sendChatCompletion).mockResolvedValue(mockResponse);

    render(<Chat onAuthError={mockOnAuthError} />);

    const input = screen.getByTestId("chat-input");
    await user.type(input, "Hello");
    await user.click(screen.getByTestId("chat-submit"));

    // User message should appear
    await waitFor(() => {
      const userMessages = screen.getAllByTestId("message-user");
      expect(userMessages[0]).toHaveTextContent("Hello");
    });

    // Assistant response should appear
    await waitFor(() => {
      const assistantMessages = screen.getAllByTestId("message-assistant");
      expect(assistantMessages[0]).toHaveTextContent(
        "Hello! How can I help you?",
      );
    });

    // Input should be cleared
    expect(input).toHaveValue("");
  });

  it("shows loading state during request", async () => {
    const user = userEvent.setup();
    let resolveRequest: (value: ChatResponse) => void;
    const requestPromise = new Promise<ChatResponse>((resolve) => {
      resolveRequest = resolve;
    });

    vi.mocked(api.sendChatCompletion).mockReturnValue(requestPromise);

    render(<Chat onAuthError={mockOnAuthError} />);

    const input = screen.getByTestId("chat-input");
    await user.type(input, "Hello");
    await user.click(screen.getByTestId("chat-submit"));

    // Loading message should appear
    await waitFor(() => {
      expect(screen.getByTestId("loading-message")).toBeInTheDocument();
    });

    // Submit button should show "Sending..."
    expect(screen.getByTestId("chat-submit")).toHaveTextContent("Sending...");

    // Resolve the request
    resolveRequest!({
      content: "Response",
      model: "test-model",
    });

    // Loading should disappear
    await waitFor(() => {
      expect(screen.queryByTestId("loading-message")).not.toBeInTheDocument();
    });
  });

  it("handles multiple sequential prompts", async () => {
    const user = userEvent.setup();

    vi.mocked(api.sendChatCompletion)
      .mockResolvedValueOnce({
        content: "First response",
        model: "test-model",
      })
      .mockResolvedValueOnce({
        content: "Second response",
        model: "test-model",
      });

    render(<Chat onAuthError={mockOnAuthError} />);

    const input = screen.getByTestId("chat-input");

    // First message
    await user.type(input, "First message");
    await user.click(screen.getByTestId("chat-submit"));

    await waitFor(() => {
      expect(screen.getByText("First response")).toBeInTheDocument();
    });

    // Second message
    await user.type(input, "Second message");
    await user.click(screen.getByTestId("chat-submit"));

    await waitFor(() => {
      expect(screen.getByText("Second response")).toBeInTheDocument();
    });

    // Should have 2 user messages and 2 assistant messages
    expect(screen.getAllByTestId("message-user")).toHaveLength(2);
    expect(screen.getAllByTestId("message-assistant")).toHaveLength(2);
  });

  it("shows error message on backend failure", async () => {
    const user = userEvent.setup();

    vi.mocked(api.sendChatCompletion).mockRejectedValue(
      new Error("Network error"),
    );

    render(<Chat onAuthError={mockOnAuthError} />);

    const input = screen.getByTestId("chat-input");
    await user.type(input, "Hello");
    await user.click(screen.getByTestId("chat-submit"));

    // Error message should appear
    await waitFor(() => {
      expect(screen.getByTestId("error-message")).toBeInTheDocument();
      expect(screen.getByTestId("error-message")).toHaveTextContent(
        /Failed to send message/i,
      );
    });

    // User message should still be visible and show "Failed to send"
    const userMessage = screen.getByTestId("message-user");
    expect(userMessage).toHaveTextContent("Hello");
    expect(userMessage).toHaveTextContent("Failed to send");
  });

  it("calls onAuthError when 401 is returned", async () => {
    const user = userEvent.setup();

    vi.mocked(api.sendChatCompletion).mockRejectedValue(
      new Error("UNAUTHORIZED"),
    );

    render(<Chat onAuthError={mockOnAuthError} />);

    const input = screen.getByTestId("chat-input");
    await user.type(input, "Hello");
    await user.click(screen.getByTestId("chat-submit"));

    await waitFor(() => {
      expect(mockOnAuthError).toHaveBeenCalledOnce();
    });
  });

  it("sends conversation history with each request", async () => {
    const user = userEvent.setup();
    const sendSpy = vi.mocked(api.sendChatCompletion);

    sendSpy
      .mockResolvedValueOnce({
        content: "First response",
        model: "test-model",
      })
      .mockResolvedValueOnce({
        content: "Second response",
        model: "test-model",
      });

    render(<Chat onAuthError={mockOnAuthError} />);

    const input = screen.getByTestId("chat-input");

    // First message
    await user.type(input, "First message");
    await user.click(screen.getByTestId("chat-submit"));

    await waitFor(() => {
      expect(screen.getByText("First response")).toBeInTheDocument();
    });

    // First call should have 1 message
    expect(sendSpy).toHaveBeenCalledTimes(1);
    expect(sendSpy.mock.calls[0][0].messages).toHaveLength(1);
    expect(sendSpy.mock.calls[0][0].messages[0]).toEqual({
      role: "user",
      content: "First message",
    });

    // Second message
    await user.type(input, "Second message");
    await user.click(screen.getByTestId("chat-submit"));

    await waitFor(() => {
      expect(screen.getByText("Second response")).toBeInTheDocument();
    });

    // Second call should have 3 messages (user, assistant, user)
    expect(sendSpy).toHaveBeenCalledTimes(2);
    expect(sendSpy.mock.calls[1][0].messages).toHaveLength(3);
    expect(sendSpy.mock.calls[1][0].messages[0]).toEqual({
      role: "user",
      content: "First message",
    });
    expect(sendSpy.mock.calls[1][0].messages[1]).toEqual({
      role: "assistant",
      content: "First response",
    });
    expect(sendSpy.mock.calls[1][0].messages[2]).toEqual({
      role: "user",
      content: "Second message",
    });
  });

  it("excludes failed messages from conversation history", async () => {
    const user = userEvent.setup();
    const sendSpy = vi.mocked(api.sendChatCompletion);

    // First message succeeds
    sendSpy.mockResolvedValueOnce({
      content: "First response",
      model: "test-model",
    });

    render(<Chat onAuthError={mockOnAuthError} />);

    const input = screen.getByTestId("chat-input");

    // First message - succeeds
    await user.type(input, "First message");
    await user.click(screen.getByTestId("chat-submit"));

    await waitFor(() => {
      expect(screen.getByText("First response")).toBeInTheDocument();
    });

    // Second message - fails
    sendSpy.mockRejectedValueOnce(new Error("Network error"));
    await user.type(input, "Second message that fails");
    await user.click(screen.getByTestId("chat-submit"));

    await waitFor(() => {
      expect(screen.getByTestId("error-message")).toBeInTheDocument();
    });

    // Third message - succeeds
    sendSpy.mockResolvedValueOnce({
      content: "Third response",
      model: "test-model",
    });
    await user.type(input, "Third message");
    await user.click(screen.getByTestId("chat-submit"));

    await waitFor(() => {
      expect(screen.getByText("Third response")).toBeInTheDocument();
    });

    // Third call should have 3 messages: first user, first assistant, third user
    // Should NOT include the failed second message
    expect(sendSpy).toHaveBeenCalledTimes(3);
    expect(sendSpy.mock.calls[2][0].messages).toHaveLength(3);
    expect(sendSpy.mock.calls[2][0].messages[0]).toEqual({
      role: "user",
      content: "First message",
    });
    expect(sendSpy.mock.calls[2][0].messages[1]).toEqual({
      role: "assistant",
      content: "First response",
    });
    expect(sendSpy.mock.calls[2][0].messages[2]).toEqual({
      role: "user",
      content: "Third message",
    });
    // Verify the failed message is not in the history
    expect(sendSpy.mock.calls[2][0].messages).not.toContainEqual(
      expect.objectContaining({
        content: "Second message that fails",
      }),
    );
  });

  it("clears error message on subsequent successful request", async () => {
    const user = userEvent.setup();
    const sendSpy = vi.mocked(api.sendChatCompletion);

    // First request fails
    sendSpy.mockRejectedValueOnce(new Error("Network error"));

    render(<Chat onAuthError={mockOnAuthError} />);

    const input = screen.getByTestId("chat-input");
    await user.type(input, "Hello");
    await user.click(screen.getByTestId("chat-submit"));

    // Error should appear
    await waitFor(() => {
      expect(screen.getByTestId("error-message")).toBeInTheDocument();
    });

    // Second request succeeds
    sendSpy.mockResolvedValueOnce({
      content: "Success",
      model: "test-model",
    });

    await user.type(input, "Try again");
    await user.click(screen.getByTestId("chat-submit"));

    // Error should disappear
    await waitFor(() => {
      expect(screen.queryByTestId("error-message")).not.toBeInTheDocument();
    });
  });

  it("disables input and button while submitting", async () => {
    const user = userEvent.setup();
    let resolveRequest: (value: ChatResponse) => void;
    const requestPromise = new Promise<ChatResponse>((resolve) => {
      resolveRequest = resolve;
    });

    vi.mocked(api.sendChatCompletion).mockReturnValue(requestPromise);

    render(<Chat onAuthError={mockOnAuthError} />);

    const input = screen.getByTestId("chat-input");
    const submitButton = screen.getByTestId("chat-submit");

    await user.type(input, "Hello");
    await user.click(submitButton);

    // Both should be disabled during submission
    await waitFor(() => {
      expect(input).toBeDisabled();
      expect(submitButton).toBeDisabled();
    });

    // Resolve the request
    resolveRequest!({
      content: "Response",
      model: "test-model",
    });

    // Should be enabled again
    await waitFor(() => {
      expect(input).not.toBeDisabled();
    });
  });
});
