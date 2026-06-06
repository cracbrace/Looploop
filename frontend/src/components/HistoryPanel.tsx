import { useState, useEffect, useRef } from "react";
import { fetchHistory, deleteTask, renameTask } from "../api/client";

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
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const editRef = useRef<HTMLInputElement>(null);

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

  const startEdit = (item: HistoryItem, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(item.task_id);
    setEditTitle(item.title);
    setTimeout(() => editRef.current?.focus(), 0);
  };

  const saveEdit = async (taskId: string) => {
    const trimmed = editTitle.trim();
    if (trimmed && trimmed !== items.find(i => i.task_id === taskId)?.title) {
      try {
        await renameTask(taskId, trimmed);
        setItems((prev) => prev.map(i => i.task_id === taskId ? { ...i, title: trimmed } : i));
      } catch { /* ignore */ }
    }
    setEditingId(null);
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
              {editingId === item.task_id ? (
                <input
                  ref={editRef}
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  onBlur={() => saveEdit(item.task_id)}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); saveEdit(item.task_id); } if (e.key === "Escape") { e.preventDefault(); setEditingId(null); } }}
                  onClick={(e) => e.stopPropagation()}
                  className="text-xs font-medium bg-zinc-700 border border-zinc-500 rounded px-1 py-0 w-full
                             text-zinc-200 focus:outline-none focus:border-emerald-500"
                />
              ) : (
                <div
                  className="text-xs font-medium truncate cursor-text hover:text-zinc-200 transition-colors"
                  onDoubleClick={(e) => startEdit(item, e)}
                  title="Double-click to rename"
                >{item.title}</div>
              )}
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
