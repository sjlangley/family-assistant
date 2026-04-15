/**
 * MarkdownContent component for rendering markdown text
 * Used for assistant messages in chat interfaces
 */

import { createContext, useContext, type ComponentProps } from "react";
import ReactMarkdown from "react-markdown";
import type { ExtraProps } from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Context used to signal that a `code` element is rendered inside a `pre`
 * block (i.e., it is a fenced code block, not inline code).
 */
const BlockCodeContext = createContext(false);

/**
 * Renders the outer `<pre>` wrapper for fenced code blocks and provides
 * context so the nested `<code>` renderer knows it is block-level.
 */
function PreBlock({ children }: ComponentProps<"pre"> & ExtraProps) {
  return (
    <BlockCodeContext.Provider value={true}>
      <pre className="mb-2 overflow-x-auto">{children}</pre>
    </BlockCodeContext.Provider>
  );
}

/**
 * Renders a `<code>` element as either block or inline based on whether it
 * lives inside a `<pre>` (detected via React context).  This correctly
 * handles fenced code blocks with *and* without a language specifier,
 * because react-markdown v9+ removed the `inline` prop.
 */
function CodeBlock({
  children,
  className,
}: ComponentProps<"code"> & ExtraProps) {
  const isBlock = useContext(BlockCodeContext);
  const language =
    isBlock && className?.startsWith("language-")
      ? className.replace("language-", "")
      : undefined;
  return isBlock ? (
    <code
      className="block bg-black/10 rounded p-2 text-xs font-mono overflow-x-auto whitespace-pre"
      aria-label={language ? `${language} code` : undefined}
    >
      {children}
    </code>
  ) : (
    <code className="bg-black/10 rounded px-1 py-0.5 text-xs font-mono">
      {children}
    </code>
  );
}

interface MarkdownContentProps {
  content: string;
  className?: string;
}

/**
 * Renders markdown content with GitHub Flavored Markdown support.
 * Applies prose styling for headers, lists, code blocks, and tables.
 */
export function MarkdownContent({
  content,
  className = "",
}: MarkdownContentProps) {
  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className="text-xl font-bold mt-2 mb-1">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-lg font-semibold mt-2 mb-1">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-base font-semibold mt-1 mb-1">{children}</h3>
          ),
          p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
          ul: ({ children }) => (
            <ul className="list-disc list-inside mb-2 space-y-1">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal list-inside mb-2 space-y-1">
              {children}
            </ol>
          ),
          li: ({ children }) => <li className="ml-2">{children}</li>,
          code: CodeBlock,
          pre: PreBlock,
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-current opacity-70 pl-3 my-2">
              {children}
            </blockquote>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              className="underline hover:opacity-80"
              target="_blank"
              rel="noopener noreferrer"
            >
              {children}
            </a>
          ),
          strong: ({ children }) => (
            <strong className="font-bold">{children}</strong>
          ),
          em: ({ children }) => <em className="italic">{children}</em>,
          hr: () => <hr className="my-2 border-current opacity-30" />,
          table: ({ children }) => (
            <div className="overflow-x-auto mb-2">
              <table className="text-xs border-collapse">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border border-current/30 px-2 py-1 font-semibold text-left">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-current/30 px-2 py-1">{children}</td>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
