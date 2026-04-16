/**
 * Tests for EvidencePanel component
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { EvidencePanel } from "./EvidencePanel";
import type { Evidence } from "../types/api";

describe("EvidencePanel", () => {
  let originalWindowOpen: typeof window.open;

  beforeEach(() => {
    originalWindowOpen = window.open;
    window.open = vi.fn();

    Object.defineProperty(document.body.style, "overflow", {
      writable: true,
      configurable: true,
      value: "",
    });
  });

  afterEach(() => {
    cleanup();
    window.open = originalWindowOpen;
    vi.clearAllMocks();
  });

  it("should render null when closed", () => {
    const onClose = vi.fn();
    const mockEvidence: Evidence = { sources: [] };
    const { container } = render(
      <EvidencePanel isOpen={false} evidence={mockEvidence} onClose={onClose} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("should render evidence panel when open", () => {
    const onClose = vi.fn();
    const mockEvidence: Evidence = { sources: [] };
    render(
      <EvidencePanel isOpen={true} evidence={mockEvidence} onClose={onClose} />,
    );
    expect(screen.getByTestId("evidence-panel")).toBeInTheDocument();
  });

  it("should display header", () => {
    const onClose = vi.fn();
    const mockEvidence: Evidence = { sources: [] };
    render(
      <EvidencePanel isOpen={true} evidence={mockEvidence} onClose={onClose} />,
    );
    const headers = screen.queryAllByText("Evidence Details");
    expect(headers.length).toBeGreaterThan(0);
  });

  it("should close when close button is clicked", () => {
    const onClose = vi.fn();
    const mockEvidence: Evidence = { sources: [] };
    render(
      <EvidencePanel isOpen={true} evidence={mockEvidence} onClose={onClose} />,
    );
    fireEvent.click(screen.getByTestId("evidence-panel-close"));
    expect(onClose).toHaveBeenCalled();
  });

  it("should close when Escape key is pressed", () => {
    const onClose = vi.fn();
    const mockEvidence: Evidence = { sources: [] };
    render(
      <EvidencePanel isOpen={true} evidence={mockEvidence} onClose={onClose} />,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("should close when clicking on backdrop", () => {
    const onClose = vi.fn();
    const mockEvidence: Evidence = { sources: [] };
    render(
      <EvidencePanel isOpen={true} evidence={mockEvidence} onClose={onClose} />,
    );
    const panel = screen.getByTestId("evidence-panel");
    fireEvent.click(panel);
    expect(onClose).toHaveBeenCalled();
  });

  it("should display empty state when no evidence", () => {
    const onClose = vi.fn();
    const mockEvidence: Evidence = { sources: [], tools: [], memory: [] };
    render(
      <EvidencePanel isOpen={true} evidence={mockEvidence} onClose={onClose} />,
    );
    expect(
      screen.getByText("No evidence details available for this message."),
    ).toBeInTheDocument();
  });
});
