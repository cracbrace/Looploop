import { useState, useRef, useEffect } from "react";

const shotTypeColor: Record<string, string> = {
  "大远景": "border-l-blue-500", "远景": "border-l-sky-500",
  "中景": "border-l-green-500", "近景": "border-l-yellow-500",
  "特写": "border-l-orange-500", "大特写": "border-l-red-500",
  "双人镜头": "border-l-purple-500", "过肩镜头": "border-l-pink-500",
};

interface EditableFieldProps {
  value: string;
  onSave: (val: string) => void;
  className?: string;
  as?: "span" | "p";
  placeholder?: string;
  prefix?: string;
}

function EditableField({ value, onSave, className, as = "span", placeholder = "", prefix = "" }: EditableFieldProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const save = () => {
    if (draft.trim() !== value) onSave(draft.trim());
    setEditing(false);
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={save}
        onKeyDown={(e) => {
          if (e.key === "Enter") save();
          if (e.key === "Escape") { setDraft(value); setEditing(false); }
        }}
        className="bg-zinc-700 border border-zinc-500 rounded px-1 py-0 text-inherit w-full
                   focus:outline-none focus:border-emerald-500"
        style={{ fontSize: "inherit" }}
      />
    );
  }

  const Tag = as;
  return (
    <Tag
      className={`${className} cursor-text hover:bg-zinc-700/50 rounded px-1 -mx-1 transition-colors`}
      onDoubleClick={() => { setDraft(value); setEditing(true); }}
      title="Double-click to edit"
    >
      {prefix}{value || placeholder}
    </Tag>
  );
}

interface ShotCardProps {
  shot: {
    shot_id: string;
    shot_number: number;
    shot_type: string;
    camera_movement: string;
    focus_subject: string;
    visual_prompt: string;
    sfx?: string;
    dialogue?: { character: string; emotion: string; line: string } | null;
    duration: string;
  };
  isSelected: boolean;
  onClick: () => void;
  onRegenerate?: (feedback?: string) => Promise<void>;
  onEdit?: (field: string, value: string) => void;
}

export function ShotCard({ shot, isSelected, onClick, onRegenerate, onEdit }: ShotCardProps) {
  const [showRegen, setShowRegen] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [loading, setLoading] = useState(false);
  const borderColor = shotTypeColor[shot.shot_type] || "border-l-zinc-600";

  const handleRegen = async () => {
    if (!onRegenerate) return;
    setLoading(true);
    await onRegenerate(feedback || undefined);
    setLoading(false);
    setShowRegen(false);
    setFeedback("");
  };

  const edit = (field: string, value: string) => {
    onEdit?.(field, value);
  };

  return (
    <div
      onClick={onClick}
      className={`bg-zinc-900 border border-zinc-800 rounded-lg p-3 border-l-2 ${borderColor}
        transition-all cursor-pointer hover:border-zinc-600
        ${isSelected ? "ring-1 ring-emerald-500/50 border-emerald-500/50" : ""}
        ${loading ? "opacity-60 animate-pulse" : ""}`}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs font-mono text-zinc-500">{shot.shot_id}</span>
        <span className="text-xs px-1.5 py-0.5 bg-zinc-800 rounded text-zinc-300">
          {shot.shot_type}
        </span>
        <span className="text-xs px-1.5 py-0.5 bg-zinc-800 rounded text-zinc-400">
          {shot.camera_movement}
        </span>
        <EditableField
          value={shot.duration}
          onSave={(v) => edit("duration", v)}
          className="text-xs text-zinc-500 ml-auto"
        />
        {onRegenerate && (
          <button
            onClick={(e) => { e.stopPropagation(); setShowRegen(!showRegen); }}
            className="text-xs px-1.5 py-0.5 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-700 rounded transition-colors"
            title="Regenerate this shot"
          >&#x21bb;</button>
        )}
      </div>

      <EditableField
        value={shot.focus_subject}
        onSave={(v) => edit("focus_subject", v)}
        className="text-xs text-zinc-400 mb-1"
        prefix="Focus: "
      />
      {shot.sfx !== undefined && (
        <EditableField
          value={shot.sfx || ""}
          onSave={(v) => edit("sfx", v)}
          className="text-xs text-amber-500/70 mb-1"
          prefix="SFX: "
          placeholder="Add sound effect..."
        />
      )}
      {shot.dialogue ? (
        <p className="text-sm text-zinc-200 mt-2 bg-zinc-800/50 rounded px-2 py-1">
          <span className="text-emerald-400 font-medium">
            {shot.dialogue.character}
          </span>
          <EditableField
            value={shot.dialogue.emotion}
            onSave={(v) => edit("dialogue_emotion", v)}
            className="text-zinc-500 text-xs ml-1"
          />
          ：
          <EditableField
            value={shot.dialogue.line}
            onSave={(v) => edit("dialogue_line", v)}
            className="text-zinc-200"
          />
        </p>
      ) : (
        <p className="text-xs text-zinc-600 mt-1 italic">No dialogue</p>
      )}
      <EditableField
        value={shot.visual_prompt}
        onSave={(v) => edit("visual_prompt", v)}
        className="text-xs text-zinc-600 mt-1 truncate block"
        prefix="prompt: "
      />

      {showRegen && (
        <div className="mt-2 pt-2 border-t border-zinc-700" onClick={(e) => e.stopPropagation()}>
          <input
            type="text"
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="What to change? (e.g. handheld style)"
            className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs
                       text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500"
          />
          <div className="flex gap-2 mt-1">
            <button onClick={handleRegen} disabled={loading}
              className="text-xs px-2 py-0.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 rounded transition-colors">
              {loading ? "..." : "Regenerate"}
            </button>
            <button onClick={() => setShowRegen(false)}
              className="text-xs px-2 py-0.5 text-zinc-400 hover:text-zinc-200 transition-colors">
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
