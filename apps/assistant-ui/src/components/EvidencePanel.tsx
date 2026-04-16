/**
 * EvidencePanel component for displaying evidence details
 * Supports sources, tools, and memory with responsive modal behavior
 */

import { useEffect, useRef, useCallback } from "react";
import type { Evidence } from "../types/api";
import { SourceDetail } from "./SourceDetail";
import { ToolDetail } from "./ToolDetail";
import { MemoryDetail } from "./MemoryDetail";

interface EvidencePanelProps {
  isOpen: boolean;
  evidence: Evidence | null;
  onClose: () => void;
}

export function EvidencePanel({
  isOpen,
  evidence,
  onClose,
}: EvidencePanelProps) {
  const contentRef = useRef<HTMLDivElement>(null);

  // Handle Escape key to close panel
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  // Handle click outside to close panel
  const handleBackdropClick = useCallback(
    (event: React.MouseEvent) => {
      // Only close if clicking directly on the backdrop
      if (event.target === event.currentTarget) {
        onClose();
      }
    },
    [onClose],
  );

  // Prevent body scroll when panel is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "unset";
    }

    return () => {
      document.body.style.overflow = "unset";
    };
  }, [isOpen]);

  if (!isOpen || !evidence) {
    return null;
  }

  return (
    <div
      className="evidence-panel"
      onClick={handleBackdropClick}
      data-testid="evidence-panel"
    >
      <div
        className="evidence-panel-content"
        ref={contentRef}
        data-testid="evidence-panel-content"
      >
        {/* Header */}
        <div className="evidence-panel-header">
          <h2 className="evidence-panel-title">Evidence Details</h2>
          <button
            onClick={onClose}
            className="evidence-panel-close"
            data-testid="evidence-panel-close"
            aria-label="Close evidence panel"
            title="Press Escape to close"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="evidence-panel-body">
          {/* Sources Section */}
          {evidence.sources && evidence.sources.length > 0 && (
            <div className="evidence-section">
              <div className="evidence-section-title">Sources</div>
              <div className="space-y-2">
                {evidence.sources.map((source, index) => (
                  <SourceDetail key={`source-${index}`} source={source} />
                ))}
              </div>
            </div>
          )}

          {/* Tools Section */}
          {evidence.tools && evidence.tools.length > 0 && (
            <div className="evidence-section">
              <div className="evidence-section-title">Tools Used</div>
              <div className="space-y-2">
                {evidence.tools.map((tool, index) => (
                  <ToolDetail key={`tool-${index}`} tool={tool} />
                ))}
              </div>
            </div>
          )}

          {/* Memory Section */}
          {evidence.memory && evidence.memory.length > 0 && (
            <div className="evidence-section">
              <div className="evidence-section-title">Memory Used</div>
              <div className="space-y-2">
                {evidence.memory.map((mem, index) => (
                  <MemoryDetail key={`memory-${index}`} memory={mem} />
                ))}
              </div>
            </div>
          )}

          {/* Empty state */}
          {(!evidence.sources || evidence.sources.length === 0) &&
            (!evidence.tools || evidence.tools.length === 0) &&
            (!evidence.memory || evidence.memory.length === 0) && (
              <div className="evidence-section-empty">
                No evidence details available for this message.
              </div>
            )}
        </div>
      </div>
    </div>
  );
}
