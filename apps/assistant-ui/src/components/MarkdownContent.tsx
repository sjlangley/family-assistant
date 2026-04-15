/**
 * MarkdownContent component for rendering markdown text
 * Used for assistant messages in chat interfaces
 */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

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
          code: ({ children, className: codeClassName, inline }) => {
            const language = codeClassName?.startsWith("language-")
              ? codeClassName.replace("language-", "")
              : undefined;
            return inline ? (
              <code className="bg-black/10 rounded px-1 py-0.5 text-xs font-mono">
                {children}
              </code>
            ) : (
              <code
                className="block bg-black/10 rounded p-2 text-xs font-mono overflow-x-auto whitespace-pre"
                aria-label={language ? `${language} code` : undefined}
              >
                {children}
              </code>
            );
          },
          pre: ({ children }) => (
            <pre className="mb-2 overflow-x-auto">{children}</pre>
          ),
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
