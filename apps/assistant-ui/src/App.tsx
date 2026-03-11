import { useAuth } from "./lib/auth";
import { GoogleSignInButton } from "./components/GoogleSignInButton";
import { ConversationsChat } from "./components/ConversationsChat";
import { useCallback } from "react";

export default function App() {
  const { authState, logout } = useAuth();

  // Handle logout from chat component
  const handleLogout = useCallback(() => {
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

  // Authenticated state - Show conversations chat interface
  return <ConversationsChat onLogout={handleLogout} />;
}
