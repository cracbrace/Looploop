import { useEffect, useRef, useState } from "react";

interface LogEntry {
  id: number;
  level: "info" | "warn" | "error";
  message: string;
  time: string;
}

interface LogDrawerProps {
  logs: LogEntry[];
  open: boolean;
  onToggle: () => void;
  onClear: () => void;
}

export function LogDrawer({ logs, open, onToggle, onClear }: LogDrawerProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs, open]);

  const levelStyle = {
    info: "text-zinc-400",
    warn: "text-amber-400",
    error: "text-red-400",
  };

  return (
    <>
      {/* Toggle button */}
      <button
        onClick={onToggle}
        className={`fixed bottom-4 right-4 z-50 px-3 py-1.5 rounded-full text-[10px] font-medium
          transition-all shadow-lg
          ${open
            ? "bg-zinc-800 text-zinc-300 border border-zinc-700"
            : "bg-zinc-800 text-zinc-400 border border-zinc-700 hover:text-zinc-200"
          }`}
      >
        {open ? "Close Log" : `Logs${logs.length ? ` (${logs.length})` : ""}`}
      </button>

      {/* Drawer panel */}
      {open && (
        <div className="fixed bottom-12 right-4 z-50 w-96 h-80 bg-[#0c0c0c] border border-zinc-700/80
          rounded-lg shadow-2xl flex flex-col overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-zinc-800 shrink-0">
            <span className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">
              Pipeline Log
            </span>
            <button onClick={onClear}
              className="text-[10px] text-zinc-600 hover:text-zinc-400 transition-colors">
              Clear
            </button>
          </div>
          {/* Log lines */}
          <div className="flex-1 overflow-y-auto p-2 font-mono text-[11px] leading-relaxed">
            {logs.length === 0 ? (
              <p className="text-zinc-600 text-center mt-8">Waiting for pipeline events...</p>
            ) : (
              logs.map((entry) => (
                <div key={entry.id} className="flex gap-2 hover:bg-zinc-800/30 px-1 rounded">
                  <span className="text-zinc-600 shrink-0">{entry.time}</span>
                  <span className={levelStyle[entry.level]}>{entry.message}</span>
                </div>
              ))
            )}
            <div ref={bottomRef} />
          </div>
        </div>
      )}
    </>
  );
}
