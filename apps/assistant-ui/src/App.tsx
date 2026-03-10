import { useAuth } from "./lib/auth";
import { GoogleSignInButton } from "./components/GoogleSignInButton";
import { Chat } from "./components/Chat";
import { useCallback } from "react";

export default function App() {
  const { authState, logout } = useAuth();

  // Handle auth errors from chat component
  const handleAuthError = useCallback(() => {
    logout();
  }, [logout]);

  // Loading state
  if (authState.status === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-xl" data-testid="loading-state">
          Loading...
        </div>
      </div>
    );
  }

  // Unauthenticated state
  if (authState.status === "unauthenticated") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="max-w-md w-full space-y-8 p-8">
          <div className="text-center">
            <h1
              className="text-4xl font-bold text-gray-900 mb-8"
              data-testid="app-title"
            >
              Family Assistant
            </h1>
            <div className="flex justify-center" data-testid="login-section">
              <GoogleSignInButton />
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Authenticated state - Show chat interface
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-4xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <h1
              className="text-2xl font-bold text-gray-900"
              data-testid="app-title"
            >
              Family Assistant
            </h1>
            <div className="flex items-center gap-4">
              <div className="text-sm text-gray-600" data-testid="user-display">
                {authState.user.name || authState.user.email || "User"}
              </div>
              <button
                onClick={logout}
                className="px-3 py-1 text-sm bg-gray-600 text-white rounded hover:bg-gray-700 transition-colors"
                data-testid="logout-button"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Chat interface */}
      <main className="flex-1 flex flex-col max-w-4xl w-full mx-auto p-4">
        <div className="flex-1 bg-white rounded-lg shadow-sm border p-6 flex flex-col min-h-0">
          <Chat onAuthError={handleAuthError} />
        </div>
      </main>
    </div>
  );
}
