/**
 * Tests for ToolDetail component
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { ToolDetail } from "./ToolDetail";

describe("ToolDetail", () => {
  beforeEach(() => {
    // Reset DOM before each test
  });

  afterEach(() => {
    cleanup();
  });

  it("should render tool name", () => {
    const tool = { name: "test_tool" };
    render(<ToolDetail tool={tool} />);
    expect(screen.getByText("test_tool")).toBeInTheDocument();
  });

  it("should render success status", () => {
    const tool = { name: "test_tool", status: "success" };
    render(<ToolDetail tool={tool} />);
    expect(screen.getByText("✓ Success")).toBeInTheDocument();
  });

  it("should render error status", () => {
    const tool = { name: "test_tool", status: "error" };
    render(<ToolDetail tool={tool} />);
    expect(screen.getByText("✗ Error")).toBeInTheDocument();
  });

  it("should render error message", () => {
    const tool = { name: "test_tool", error: "Test error occurred" };
    render(<ToolDetail tool={tool} />);
    expect(screen.getByText("Test error occurred")).toBeInTheDocument();
  });

  it("should render input parameters", () => {
    const tool = { name: "test_tool", input: { query: "test", limit: 10 } };
    render(<ToolDetail tool={tool} />);
    expect(screen.getByText("Input")).toBeInTheDocument();
  });

  it("should render output", () => {
    const tool = { name: "test_tool", output: { results: ["a", "b"] } };
    render(<ToolDetail tool={tool} />);
    expect(screen.getByText("Output")).toBeInTheDocument();
  });

  it("should handle missing properties gracefully", () => {
    const tool = { name: "test_tool" };
    const { container } = render(<ToolDetail tool={tool} />);
    expect(container.querySelector(".tool-detail")).toBeInTheDocument();
  });

  it("should not render empty input section", () => {
    const tool = { name: "test_tool", input: {} };
    render(<ToolDetail tool={tool} />);
    expect(screen.queryByText("Input")).not.toBeInTheDocument();
  });

  it("should not render empty output section", () => {
    const tool = { name: "test_tool", output: {} };
    render(<ToolDetail tool={tool} />);
    expect(screen.queryByText("Output")).not.toBeInTheDocument();
  });
});
