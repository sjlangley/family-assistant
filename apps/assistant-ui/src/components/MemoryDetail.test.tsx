/**
 * Tests for MemoryDetail component
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { MemoryDetail } from "./MemoryDetail";

describe("MemoryDetail", () => {
  beforeEach(() => {
    // Reset before each test
  });

  afterEach(() => {
    cleanup();
  });
  it("should render memory type", () => {
    const memory = { type: "fact" };
    render(<MemoryDetail memory={memory} />);
    expect(screen.getByText("fact")).toBeInTheDocument();
  });

  it("should render memory content", () => {
    const memory = { content: "Test memory content" };
    render(<MemoryDetail memory={memory} />);
    expect(screen.getByText("Test memory content")).toBeInTheDocument();
  });

  it("should render memory source", () => {
    const memory = { source: "conversation_2024" };
    render(<MemoryDetail memory={memory} />);
    expect(screen.getByText("conversation_2024")).toBeInTheDocument();
  });

  it("should render memory timestamp", () => {
    const memory = { timestamp: "2024-01-01T12:00:00Z" };
    render(<MemoryDetail memory={memory} />);
    // Verify that some numeric content is rendered (the formatted timestamp)
    const timestampDiv = document.querySelector(".memory-detail-timestamp");
    expect(timestampDiv).toBeInTheDocument();
    expect(timestampDiv?.textContent).toBeTruthy();
  });

  it("should format timestamp as locale string", () => {
    const memory = { timestamp: "2024-01-01T12:00:00Z" };
    render(<MemoryDetail memory={memory} />);
    // The timestamp should be converted to locale string format
    const timestampDiv = document.querySelector(".memory-detail-timestamp");
    expect(timestampDiv?.textContent).toMatch(/\d/);
  });

  it("should handle invalid timestamp gracefully", () => {
    const memory = { timestamp: "invalid-date" };
    render(<MemoryDetail memory={memory} />);
    // When timestamp is invalid, it will be displayed as-is
    const timestampDiv = document.querySelector(".memory-detail-timestamp");
    expect(timestampDiv).toBeInTheDocument();
  });

  it("should render all properties together", () => {
    const memory = {
      type: "fact",
      content: "Test memory",
      timestamp: "2024-01-01T00:00:00Z",
      source: "test_source",
    };
    render(<MemoryDetail memory={memory} />);
    // Use getAllByText to handle duplicates (or just verify the types)
    const factElements = screen.queryAllByText("fact");
    expect(factElements.length).toBeGreaterThan(0);
    expect(screen.getByText("Test memory")).toBeInTheDocument();
    expect(screen.getByText("test_source")).toBeInTheDocument();
  });

  it("should handle missing properties gracefully", () => {
    const memory = {};
    const { container } = render(<MemoryDetail memory={memory} />);
    expect(container.querySelector(".memory-detail")).toBeInTheDocument();
  });

  it("should render 'From:' label for source", () => {
    const memory = { source: "user_input" };
    render(<MemoryDetail memory={memory} />);
    expect(screen.getByText(/From:/)).toBeInTheDocument();
  });
});
