/**
 * MemoryDetail component for displaying memory information
 */

interface Memory {
  type?: string;
  content?: string;
  timestamp?: string;
  source?: string;
}

interface MemoryDetailProps {
  memory: Memory;
}

export function MemoryDetail({ memory }: MemoryDetailProps) {
  const formatTimestamp = (timestamp: string): string => {
    try {
      const date = new Date(timestamp);
      // Check if the date is valid
      if (isNaN(date.getTime())) {
        return timestamp;
      }
      return date.toLocaleString();
    } catch {
      return timestamp;
    }
  };

  return (
    <div className="memory-detail">
      {memory.type && (
        <div className="memory-detail-type">{memory.type}</div>
      )}

      {memory.content && (
        <div className="memory-detail-content">{memory.content}</div>
      )}

      {memory.source && (
        <div className="text-xs text-[#6e675d] mt-2">
          <span className="font-medium">From:</span> {memory.source}
        </div>
      )}

      {memory.timestamp && (
        <div className="memory-detail-timestamp">
          {formatTimestamp(memory.timestamp)}
        </div>
      )}
    </div>
  );
}
