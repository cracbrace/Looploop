import { useState } from "react";

const shotTypeColor: Record<string, string> = {
  "大远景": "border-l-blue-500",
  "远景": "border-l-sky-500",
  "中景": "border-l-green-500",
  "近景": "border-l-yellow-500",
  "特写": "border-l-orange-500",
  "大特写": "border-l-red-500",
  "双人镜头": "border-l-purple-500",
  "过肩镜头": "border-l-pink-500",
};

interface ShotCardProps {
  shot: {
    shot_id: string;
    shot_number: number;
    shot_type: string;
    camera_movement: string;
    focus_subject: string;
    visual_prompt: string;
    sfx?: string;
    dialogue?: {
      character: string;
      emotion: string;
      line: string;
    } | null;
    duration: string;
  };
  isSelected: boolean;
  onClick: () => void;
}

export function ShotCard({ shot, isSelected, onClick }: ShotCardProps) {
  const borderColor = shotTypeColor[shot.shot_type] || "border-l-zinc-600";

  return (
    <div
      onClick={onClick}
      className={`bg-zinc-900 border border-zinc-800 rounded-lg p-3 border-l-2 ${borderColor}
        transition-all cursor-pointer hover:border-zinc-600
        ${isSelected ? "ring-1 ring-emerald-500/50 border-emerald-500/50" : ""}`}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs font-mono text-zinc-500">{shot.shot_id}</span>
        <span className="text-xs px-1.5 py-0.5 bg-zinc-800 rounded text-zinc-300">
          {shot.shot_type}
        </span>
        <span className="text-xs px-1.5 py-0.5 bg-zinc-800 rounded text-zinc-400">
          {shot.camera_movement}
        </span>
        <span className="text-xs text-zinc-500 ml-auto">{shot.duration}</span>
      </div>
      <p className="text-xs text-zinc-400 mb-1">Focus: {shot.focus_subject}</p>
      {shot.sfx && <p className="text-xs text-amber-500/70 mb-1">SFX: {shot.sfx}</p>}
      {shot.dialogue ? (
        <p className="text-sm text-zinc-200 mt-2 bg-zinc-800/50 rounded px-2 py-1">
          <span className="text-emerald-400 font-medium">
            {shot.dialogue.character}
          </span>
          <span className="text-zinc-500 text-xs ml-1">
            ({shot.dialogue.emotion})
          </span>
          ：{shot.dialogue.line}
        </p>
      ) : (
        <p className="text-xs text-zinc-600 mt-1 italic">No dialogue</p>
      )}
      <p className="text-xs text-zinc-600 mt-1 truncate">
        prompt: {shot.visual_prompt}
      </p>
    </div>
  );
}
