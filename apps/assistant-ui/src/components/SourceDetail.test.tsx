/**
 * Tests for SourceDetail component
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { SourceDetail } from "./SourceDetail";

describe("SourceDetail", () => {
  let originalWindowOpen: typeof window.open;

  beforeEach(() => {
    originalWindowOpen = window.open;
    window.open = vi.fn();
  });

  afterEach(() => {
    cleanup();
    window.open = originalWindowOpen;
    vi.clearAllMocks();
  });

  it("should render source title", () => {
    const source = { title: "Test Source" };
    render(<SourceDetail source={source} />);
    expect(screen.getByText("Test Source")).toBeInTheDocument();
  });

  it("should render source URL", () => {
    const source = { url: "https://example.com" };
    render(<SourceDetail source={source} />);
    expect(screen.getByText("https://example.com")).toBeInTheDocument();
  });

  it("should open URL when clicked", () => {
    const source = { url: "https://example.com" };
    render(<SourceDetail source={source} />);
    fireEvent.click(screen.getByTestId("source-detail-url"));
    expect(window.open).toHaveBeenCalledWith(
      "https://example.com",
      "_blank",
      "noopener,noreferrer",
    );
  });

  it("should render snippet", () => {
    const source = { snippet: "This is a test snippet" };
    render(<SourceDetail source={source} />);
    expect(screen.getByText("This is a test snippet")).toBeInTheDocument();
  });

  it("should render relevance score", () => {
    const source = { relevance: 0.95 };
    render(<SourceDetail source={source} />);
    expect(screen.getByText("95%")).toBeInTheDocument();
  });

  it("should handle missing properties gracefully", () => {
    const source = {};
    const { container } = render(<SourceDetail source={source} />);
    expect(container.querySelector(".source-detail")).toBeInTheDocument();
  });

  it("should format relevance as percentage", () => {
    const source = { relevance: 0.5 };
    render(<SourceDetail source={source} />);
    expect(screen.getByText("50%")).toBeInTheDocument();
  });
});
