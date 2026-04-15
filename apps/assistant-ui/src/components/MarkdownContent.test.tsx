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

  it("renders h1 heading", () => {
    const { container } = render(<MarkdownContent content="# Heading 1" />);
    const h1 = container.querySelector("h1");
    expect(h1).toBeInTheDocument();
    expect(h1).toHaveTextContent("Heading 1");
  });

  it("renders h2 heading", () => {
    const { container } = render(<MarkdownContent content="## Heading 2" />);
    const h2 = container.querySelector("h2");
    expect(h2).toBeInTheDocument();
    expect(h2).toHaveTextContent("Heading 2");
  });

  it("renders h3 heading", () => {
    const { container } = render(<MarkdownContent content="### Heading 3" />);
    const h3 = container.querySelector("h3");
    expect(h3).toBeInTheDocument();
    expect(h3).toHaveTextContent("Heading 3");
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

  it("renders fenced code block with language", () => {
    const { container } = render(
      <MarkdownContent content={"```javascript\nconst x = 1;\n```"} />,
    );
    const pre = container.querySelector("pre");
    const code = container.querySelector("pre code");
    expect(pre).toBeInTheDocument();
    expect(code).toBeInTheDocument();
    expect(code).toHaveAttribute("aria-label", "javascript code");
    expect(code).toHaveTextContent("const x = 1;");
  });

  it("renders fenced code block without language", () => {
    const { container } = render(
      <MarkdownContent content={"```\nplain code\n```"} />,
    );
    const pre = container.querySelector("pre");
    const code = container.querySelector("pre code");
    expect(pre).toBeInTheDocument();
    expect(code).toBeInTheDocument();
    expect(code).not.toHaveAttribute("aria-label");
    expect(code).toHaveClass("block");
    expect(code).toHaveTextContent("plain code");
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

  it("renders horizontal rules", () => {
    const { container } = render(<MarkdownContent content="---" />);
    const hr = container.querySelector("hr");
    expect(hr).toBeInTheDocument();
  });

  it("renders GFM tables", () => {
    const tableMarkdown =
      "| Name | Age |\n| --- | --- |\n| Alice | 30 |\n| Bob | 25 |";
    const { container } = render(<MarkdownContent content={tableMarkdown} />);
    const table = container.querySelector("table");
    expect(table).toBeInTheDocument();
    const headers = container.querySelectorAll("th");
    expect(headers).toHaveLength(2);
    expect(headers[0]).toHaveTextContent("Name");
    expect(headers[1]).toHaveTextContent("Age");
    const cells = container.querySelectorAll("td");
    expect(cells).toHaveLength(4);
    expect(cells[0]).toHaveTextContent("Alice");
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
