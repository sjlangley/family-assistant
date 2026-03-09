/**
 * Authentication state management
 * Provides auth state and actions throughout the app
 */

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";
import type { User } from "../types/api";
import * as api from "./api";

type AuthState =
  | { status: "loading" }
  | { status: "unauthenticated" }
  | { status: "authenticated"; user: User };

interface AuthContextValue {
  authState: AuthState;
  loginWithGoogle: (googleIdToken: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [authState, setAuthState] = useState<AuthState>({ status: "loading" });

  // Check authentication status on mount
  useEffect(() => {
    const abortController = new AbortController();

    async function checkAuth() {
      try {
        const user = await api.getCurrentUser(abortController.signal);
        if (user) {
          setAuthState({ status: "authenticated", user });
        } else {
          setAuthState({ status: "unauthenticated" });
        }
      } catch (error) {
        // Ignore abort errors - component unmounted
        if (error instanceof Error && error.name === "AbortError") {
          return;
        }
        console.error("Auth check failed:", error);
        setAuthState({ status: "unauthenticated" });
      }
    }

    checkAuth();

    return () => {
      abortController.abort();
    };
  }, []);

  const loginWithGoogle = useCallback(async (googleIdToken: string) => {
    try {
      const user = await api.login(googleIdToken);
      setAuthState({ status: "authenticated", user });
    } catch (error) {
      console.error("Login failed:", error);
      throw error;
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
      setAuthState({ status: "unauthenticated" });
    } catch (error) {
      console.error("Logout failed:", error);
      // Even if logout fails, clear local state
      setAuthState({ status: "unauthenticated" });
    }
  }, []);

  return (
    <AuthContext.Provider value={{ authState, loginWithGoogle, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
