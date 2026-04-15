/**
 * Tests for MarkdownContent component
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MarkdownContent } from "./MarkdownContent";

describe("MarkdownContent", () => {
  it("renders plain text", () => {
    render(<MarkdownContent content="Hello world" />);
    expect(screen.getByText("Hello world")).toBeInTheDocument();
  });

  it("renders bold text", () => {
    const { container } = render(<MarkdownContent content="**bold text**" />);
    const bold = container.querySelector("strong");
    expect(bold).toBeInTheDocument();
    expect(bold).toHaveTextContent("bold text");
  });

  it("renders italic text", () => {
    const { container } = render(<MarkdownContent content="_italic text_" />);
    const em = container.querySelector("em");
    expect(em).toBeInTheDocument();
    expect(em).toHaveTextContent("italic text");
  });

  it("renders headings", () => {
    const { container } = render(<MarkdownContent content="# Heading 1" />);
    const h1 = container.querySelector("h1");
    expect(h1).toBeInTheDocument();
    expect(h1).toHaveTextContent("Heading 1");
  });

  it("renders unordered lists", () => {
    const { container } = render(
      <MarkdownContent content={"- Item 1\n- Item 2\n- Item 3"} />,
    );
    const items = container.querySelectorAll("li");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("Item 1");
    expect(items[2]).toHaveTextContent("Item 3");
  });

  it("renders ordered lists", () => {
    const { container } = render(
      <MarkdownContent content={"1. First\n2. Second"} />,
    );
    const ol = container.querySelector("ol");
    expect(ol).toBeInTheDocument();
    const items = container.querySelectorAll("li");
    expect(items).toHaveLength(2);
  });

  it("renders inline code", () => {
    const { container } = render(
      <MarkdownContent content="Use `console.log()` to debug" />,
    );
    const code = container.querySelector("code");
    expect(code).toBeInTheDocument();
    expect(code).toHaveTextContent("console.log()");
  });

  it("renders links with correct attributes", () => {
    const { container } = render(
      <MarkdownContent content="[Click here](https://example.com)" />,
    );
    const link = container.querySelector("a");
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "https://example.com");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link).toHaveTextContent("Click here");
  });

  it("renders blockquotes", () => {
    const { container } = render(<MarkdownContent content="> A quote" />);
    const blockquote = container.querySelector("blockquote");
    expect(blockquote).toBeInTheDocument();
    expect(blockquote).toHaveTextContent("A quote");
  });

  it("renders GFM strikethrough", () => {
    const { container } = render(
      <MarkdownContent content="~~strikethrough~~" />,
    );
    const del = container.querySelector("del");
    expect(del).toBeInTheDocument();
    expect(del).toHaveTextContent("strikethrough");
  });

  it("applies optional className to wrapper", () => {
    const { container } = render(
      <MarkdownContent content="Hello" className="custom-class" />,
    );
    expect(container.firstChild).toHaveClass("custom-class");
  });
});
