/**
 * API client for backend communication
 * All requests include credentials to send session cookies
 */

import type { User } from "../types/api";

function getApiBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL || "";
}

/**
 * Login with Google ID token
 */
export async function login(googleIdToken: string): Promise<User> {
  const response = await fetch(`${getApiBaseUrl()}/auth/login`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${googleIdToken}`,
    },
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error("Login failed");
  }

  return response.json();
}

/**
 * Get current authenticated user
 * Returns null if not authenticated (401 response)
 */
export async function getCurrentUser(
  signal?: AbortSignal,
): Promise<User | null> {
  const response = await fetch(`${getApiBaseUrl()}/user/current`, {
    credentials: "include",
    signal,
  });

  if (response.status === 401) {
    return null;
  }

  if (!response.ok) {
    throw new Error("Failed to fetch current user");
  }

  return response.json();
}

/**
 * Logout current user
 */
export async function logout(): Promise<void> {
  const response = await fetch(`${getApiBaseUrl()}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error("Logout failed");
  }
}
