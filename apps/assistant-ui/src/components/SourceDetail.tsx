/**
 * SourceDetail component for displaying individual source information
 */

interface Source {
  title?: string;
  url?: string;
  snippet?: string;
  relevance?: number;
}

interface SourceDetailProps {
  source: Source;
}

export function SourceDetail({ source }: SourceDetailProps) {
  const openSource = () => {
    if (source.url) {
      window.open(source.url, "_blank", "noopener,noreferrer");
    }
  };

  return (
    <div className="source-detail">
      {source.title && (
        <div className="source-detail-title">{source.title}</div>
      )}

      {source.url && (
        <button
          onClick={openSource}
          className="source-detail-url"
          data-testid="source-detail-url"
        >
          {source.url}
        </button>
      )}

      {source.snippet && (
        <div className="source-detail-row">
          <div className="source-detail-label">Snippet</div>
          <div className="source-detail-content">{source.snippet}</div>
        </div>
      )}

      {source.relevance !== undefined && (
        <div className="source-detail-row">
          <div className="source-detail-label">Relevance</div>
          <div className="source-detail-content">
            {(source.relevance * 100).toFixed(0)}%
          </div>
        </div>
      )}
    </div>
  );
}
