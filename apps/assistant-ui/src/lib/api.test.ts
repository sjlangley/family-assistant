import { describe, it, expect, vi, beforeEach } from "vitest";
import * as api from "./api";

// Mock fetch globally
const mockFetch = vi.fn();
globalThis.fetch = mockFetch as any;

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
        "/auth/login",
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
        "/user/current",
        expect.objectContaining({
          credentials: "include",
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
        "/auth/logout",
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
});
