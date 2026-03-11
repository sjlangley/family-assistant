import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { AuthProvider } from "./lib/auth";
import * as api from "./lib/api";

// Mock the API module
vi.mock("./lib/api");

// Mock Google Identity Services
beforeEach(() => {
  // Mock VITE_GOOGLE_CLIENT_ID environment variable
  vi.stubEnv("VITE_GOOGLE_CLIENT_ID", "mock-google-client-id");

  window.google = {
    accounts: {
      id: {
        initialize: vi.fn(),
        renderButton: vi.fn(),
        prompt: vi.fn(),
        disableAutoSelect: vi.fn(),
      },
    },
  };
  vi.clearAllMocks();

  // Setup default mock for listConversations (used by ConversationsChat)
  vi.mocked(api.listConversations).mockResolvedValue({ items: [] });
});

afterEach(() => {
  vi.unstubAllEnvs();
  cleanup();
});

describe("App", () => {
  it("renders loading state initially", () => {
    // Mock getCurrentUser to never resolve
    vi.mocked(api.getCurrentUser).mockImplementation(
      () => new Promise(() => {}),
    );

    render(
      <AuthProvider>
        <App />
      </AuthProvider>,
    );

    expect(screen.getByTestId("loading-state")).toBeInTheDocument();
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders logged-out view when user is not authenticated", async () => {
    vi.mocked(api.getCurrentUser).mockResolvedValue(null);

    render(
      <AuthProvider>
        <App />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("login-section")).toBeInTheDocument();
    });

    expect(screen.getByText("Family Assistant")).toBeInTheDocument();
    expect(screen.getByTestId("google-signin-button")).toBeInTheDocument();
  });

  it("renders authenticated view when user is logged in", async () => {
    const mockUser = {
      email: "test@example.com",
      userid: "user-123",
      name: "Test User",
    };

    vi.mocked(api.getCurrentUser).mockResolvedValue(mockUser);
    vi.mocked(api.listConversations).mockResolvedValue({ items: [] });

    render(
      <AuthProvider>
        <App />
      </AuthProvider>,
    );

    // Should show ConversationsChat component with welcome message
    await waitFor(() => {
      expect(
        screen.getByText(/welcome to family assistant/i),
      ).toBeInTheDocument();
    });

    expect(
      screen.getByRole("button", { name: /new chat/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/logged in as:.*test@example\.com/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /logout/i })).toBeInTheDocument();
  });

  it("handles logout button click", async () => {
    const user = userEvent.setup();
    const mockUser = {
      email: "test@example.com",
      userid: "user-123",
      name: "Test User",
    };

    vi.mocked(api.getCurrentUser).mockResolvedValue(mockUser);
    vi.mocked(api.listConversations).mockResolvedValue({ items: [] });
    vi.mocked(api.logout).mockResolvedValue(undefined);

    render(
      <AuthProvider>
        <App />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /logout/i }),
      ).toBeInTheDocument();
    });

    const logoutButton = screen.getByRole("button", { name: /logout/i });
    await user.click(logoutButton);

    expect(api.logout).toHaveBeenCalledTimes(1);

    // After logout, should show login view
    await waitFor(() => {
      expect(screen.getByTestId("login-section")).toBeInTheDocument();
    });
  });

  it("displays N/A for missing user fields", async () => {
    const mockUser = {
      email: null,
      userid: "user-789",
      name: null,
    };

    vi.mocked(api.getCurrentUser).mockResolvedValue(mockUser);
    vi.mocked(api.listConversations).mockResolvedValue({ items: [] });

    render(
      <AuthProvider>
        <App />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(
        screen.getByText(/welcome to family assistant/i),
      ).toBeInTheDocument();
    });

    // Should display userid as fallback when email and name are missing
    expect(screen.getByText(/logged in as:/i)).toBeInTheDocument();
    expect(screen.getByText(/user-789/i)).toBeInTheDocument();
  });

  it("handles API errors gracefully", async () => {
    vi.mocked(api.getCurrentUser).mockRejectedValue(new Error("Network error"));

    render(
      <AuthProvider>
        <App />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("login-section")).toBeInTheDocument();
    });

    // Should show logged-out state on error
    expect(screen.getByText("Family Assistant")).toBeInTheDocument();
  });

  it("successfully logs in with Google", async () => {
    const mockUser = {
      email: "newuser@example.com",
      userid: "user-999",
      name: "New User",
    };

    // Start unauthenticated
    vi.mocked(api.getCurrentUser).mockResolvedValue(null);
    vi.mocked(api.login).mockResolvedValue(mockUser);
    vi.mocked(api.listConversations).mockResolvedValue({ items: [] });

    render(
      <AuthProvider>
        <App />
      </AuthProvider>,
    );

    // Wait for logged-out view
    await waitFor(() => {
      expect(screen.getByTestId("login-section")).toBeInTheDocument();
    });

    // Simulate Google sign-in callback
    const initializeCall = vi.mocked(window.google!.accounts.id.initialize).mock
      .calls[0];
    expect(initializeCall).toBeDefined();

    if (initializeCall) {
      const config = initializeCall[0];
      // Trigger the callback
      await config.callback({
        credential: "fake-google-token",
        select_by: "btn",
      });

      // After successful login, should show conversations chat interface
      await waitFor(() => {
        expect(
          screen.getByText(/welcome to family assistant/i),
        ).toBeInTheDocument();
      });
    }
  });

  it("shows chat interface for authenticated users", async () => {
    const mockUser = {
      email: "chat@example.com",
      userid: "user-456",
      name: "Chat User",
    };

    vi.mocked(api.getCurrentUser).mockResolvedValue(mockUser);
    vi.mocked(api.listConversations).mockResolvedValue({ items: [] });

    render(
      <AuthProvider>
        <App />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(
        screen.getByText(/welcome to family assistant/i),
      ).toBeInTheDocument();
    });

    // Should have conversation chat interface elements
    expect(
      screen.getByRole("button", { name: /new chat/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText(
        /type a message to start a new conversation/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/logged in as:.*chat@example\.com/i),
    ).toBeInTheDocument();
  });
});
