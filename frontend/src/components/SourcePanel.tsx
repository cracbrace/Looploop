interface SourcePanelProps {
  paragraphs: string[];
  highlightedParagraphs: number[];
  onClose: () => void;
}

export function SourcePanel({
  paragraphs,
  highlightedParagraphs,
  onClose,
}: SourcePanelProps) {
  const highlightSet = new Set(highlightedParagraphs);

  return (
    <div className="h-48 border-t border-zinc-800 bg-zinc-900/80 backdrop-blur shrink-0 overflow-hidden flex flex-col">
      <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800 shrink-0">
        <h3 className="text-xs font-semibold text-zinc-400">
          Source Text
          {highlightedParagraphs.length > 0 && (
            <span className="ml-2 text-amber-400">
              Paragraphs: {highlightedParagraphs.join(", ")}
            </span>
          )}
        </h3>
        <button
          onClick={onClose}
          className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          Close
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {paragraphs.length === 0 ? (
          <p className="text-xs text-zinc-600">Original text not available</p>
        ) : (
          paragraphs.map((p, i) => (
            <p
              key={i}
              className={`text-xs leading-relaxed mb-2 px-2 py-1 rounded transition-colors
                ${highlightSet.has(i)
                  ? "bg-amber-500/10 text-amber-200 border-l-2 border-amber-500 pl-3"
                  : "text-zinc-500"
                }`}
            >
              <span className="text-zinc-600 mr-2 font-mono">{i}</span>
              {p.slice(0, 200)}
              {p.length > 200 ? "..." : ""}
            </p>
          ))
        )}
      </div>
    </div>
  );
}
