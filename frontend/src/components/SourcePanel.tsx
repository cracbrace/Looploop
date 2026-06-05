import { useRef, useEffect, useState } from "react";

interface SourcePanelProps {
  paragraphs: string[];
  highlightedParagraphs: number[];
  onClose: () => void;
  visible: boolean;
}

export function SourcePanel({
  paragraphs,
  highlightedParagraphs,
  onClose,
  visible,
}: SourcePanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [fontSize, setFontSize] = useState("text-xs");

  // Dynamic font sizing based on panel height
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const h = entry.contentRect.height;
        if (h > 300) setFontSize("text-sm");
        else if (h > 200) setFontSize("text-xs");
        else if (h > 120) setFontSize("text-[11px]");
        else setFontSize("text-[10px]");
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  if (!visible) {
    return (
      <div className="h-full flex items-center justify-center text-zinc-600">
        <p className="text-xs">Click a shot card to view source text</p>
      </div>
    );
  }

  const highlightSet = new Set(highlightedParagraphs);

  return (
    <div ref={containerRef} className="h-full border-t border-zinc-800 bg-zinc-900/90 overflow-hidden flex flex-col">
      <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800 shrink-0">
        <h3 className="text-xs font-semibold text-zinc-400">
          Source Text
          {highlightedParagraphs.length > 0 && (
            <span className="ml-2 text-amber-400 font-normal">
              &para; {highlightedParagraphs.join(", ")}
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
          <p className={`${fontSize} text-zinc-600`}>Original text not available</p>
        ) : (
          paragraphs.map((p, i) => (
            <p
              key={i}
              className={`${fontSize} leading-relaxed mb-2 px-2 py-1 rounded transition-colors
                ${highlightSet.has(i)
                  ? "bg-amber-500/10 text-amber-200 border-l-2 border-amber-500 pl-3"
                  : "text-zinc-500"
                }`}
            >
              <span className="text-zinc-600 mr-2 font-mono">{i}</span>
              {p.slice(0, 300)}
              {p.length > 300 ? "..." : ""}
            </p>
          ))
        )}
      </div>
    </div>
  );
}
