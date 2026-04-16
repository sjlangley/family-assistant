/**
 * ToolDetail component for displaying tool execution details
 */

interface ToolInput {
  [key: string]: unknown;
}

interface ToolOutput {
  [key: string]: unknown;
}

interface Tool {
  name: string;
  input?: ToolInput;
  output?: ToolOutput;
  status?: "success" | "error";
  error?: string;
}

interface ToolDetailProps {
  tool: Tool;
}

export function ToolDetail({ tool }: ToolDetailProps) {
  const formatJSON = (obj: unknown): string => {
    try {
      return JSON.stringify(obj, null, 2);
    } catch {
      return String(obj);
    }
  };

  return (
    <div className="tool-detail">
      <div className="tool-detail-name">{tool.name}</div>

      {/* Status */}
      {tool.status && (
        <div className="tool-detail-section">
          <div className="tool-detail-section-title">Status</div>
          <div
            className={`text-xs font-medium ${tool.status === "success" ? "text-[#2f6b53]" : "text-[#a54034]"}`}
          >
            {tool.status === "success" ? "✓ Success" : "✗ Error"}
          </div>
        </div>
      )}

      {/* Error message */}
      {tool.error && (
        <div className="tool-detail-section">
          <div className="tool-detail-section-title">Error</div>
          <div className="text-xs text-[#a54034]">{tool.error}</div>
        </div>
      )}

      {/* Input */}
      {tool.input && Object.keys(tool.input).length > 0 && (
        <div className="tool-detail-section">
          <div className="tool-detail-section-title">Input</div>
          <pre className="tool-detail-input">
            {formatJSON(tool.input)}
          </pre>
        </div>
      )}

      {/* Output */}
      {tool.output && Object.keys(tool.output).length > 0 && (
        <div className="tool-detail-section">
          <div className="tool-detail-section-title">Output</div>
          <pre className="tool-detail-output">
            {formatJSON(tool.output)}
          </pre>
        </div>
      )}
    </div>
  );
}
