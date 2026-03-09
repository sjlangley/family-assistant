import { useAuth } from "./lib/auth";
import { GoogleSignInButton } from "./components/GoogleSignInButton";

export default function App() {
  const { authState, logout } = useAuth();

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

  // Authenticated state
  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-2xl mx-auto">
        <div className="bg-white shadow rounded-lg p-8">
          <h1
            className="text-3xl font-bold text-gray-900 mb-8"
            data-testid="app-title"
          >
            Family Assistant
          </h1>

          <div className="space-y-4" data-testid="user-info">
            <div className="border-b pb-4">
              <h2 className="text-lg font-semibold text-gray-700 mb-4">
                User Information
              </h2>
              <dl className="space-y-2">
                <div>
                  <dt className="text-sm font-medium text-gray-500">Email</dt>
                  <dd
                    className="text-base text-gray-900"
                    data-testid="user-email"
                  >
                    {authState.user.email || "N/A"}
                  </dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-gray-500">Name</dt>
                  <dd
                    className="text-base text-gray-900"
                    data-testid="user-name"
                  >
                    {authState.user.name || "N/A"}
                  </dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-gray-500">User ID</dt>
                  <dd
                    className="text-base text-gray-900 font-mono text-sm"
                    data-testid="user-id"
                  >
                    {authState.user.userid}
                  </dd>
                </div>
              </dl>
            </div>

            <div className="pt-4">
              <button
                onClick={logout}
                className="px-4 py-2 bg-gray-600 text-white rounded hover:bg-gray-700 transition-colors"
                data-testid="logout-button"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
