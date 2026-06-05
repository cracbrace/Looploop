import { useState, useEffect } from "react";
import { fetchHistory, deleteTask } from "../api/client";

interface HistoryItem {
  task_id: string;
  title: string;
  status: string;
  created_at: string;
}

interface HistoryPanelProps {
  currentTaskId: string | null;
  onSelect: (taskId: string) => void;
  refreshKey: number;
}

export function HistoryPanel({ currentTaskId, onSelect, refreshKey }: HistoryPanelProps) {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const data = await fetchHistory();
      setItems(data.filter((i) => i.status === "done"));
    } catch {
      // backend might not be running
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, [refreshKey]);

  const handleDelete = async (taskId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await deleteTask(taskId);
      setItems((prev) => prev.filter((i) => i.task_id !== taskId));
    } catch { /* ignore */ }
  };

  const formatTime = (iso: string) => {
    try {
      return new Date(iso).toLocaleString("zh-CN", {
        month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit",
      });
    } catch {
      return "";
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800 shrink-0">
        <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">
          History
        </h3>
        <button
          onClick={load}
          className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          title="Refresh"
        >
          {loading ? "..." : "↻"}
        </button>
      </div>
      <div className="flex-1 overflow-y-auto">
        {items.length === 0 ? (
          <p className="text-xs text-zinc-600 px-3 py-4 text-center">
            {loading ? "Loading..." : "No history yet"}
          </p>
        ) : (
          items.map((item) => (
            <button
              key={item.task_id}
              onClick={() => onSelect(item.task_id)}
              className={`w-full text-left px-3 py-2 border-b border-zinc-800/50
                transition-colors group
                ${item.task_id === currentTaskId
                  ? "bg-zinc-800 text-zinc-100"
                  : "text-zinc-400 hover:bg-zinc-800/30 hover:text-zinc-200"
                }`}
            >
              <div className="text-xs font-medium truncate">{item.title}</div>
              <div className="flex items-center justify-between mt-0.5">
                <span className="text-[10px] text-zinc-500">
                  {formatTime(item.created_at)}
                </span>
                <button
                  onClick={(e) => handleDelete(item.task_id, e)}
                  className="text-[10px] text-zinc-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all"
                >
                  ×
                </button>
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
