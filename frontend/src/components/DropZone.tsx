import { useState, useRef, useCallback } from "react";

interface ChapterInfo {
  index: number;
  title: string;
  preview: string;
  selected: boolean;
}

interface DropZoneProps {
  onChaptersReady: (chapters: ChapterInfo[]) => void;
  onTextReady: (text: string) => void;
  disabled: boolean;
}

const CHAPTER_RE = /^(第[一二三四五六七八九十百千\d]+[章节回]\b|Chapter\s+\d+)/m;

export function DropZone({ onChaptersReady, onTextReady, disabled }: DropZoneProps) {
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const parseText = useCallback((raw: string) => {
    const lines = raw.split("\n");
    const chapters: ChapterInfo[] = [];
    let currentChapter: ChapterInfo | null = null;

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;

      if (CHAPTER_RE.test(trimmed)) {
        if (currentChapter) chapters.push(currentChapter);
        currentChapter = {
          index: chapters.length,
          title: trimmed.slice(0, 60),
          preview: "",
          selected: true,
        };
      } else if (currentChapter) {
        if (currentChapter.preview.length < 80) {
          currentChapter.preview += (currentChapter.preview ? " " : "") + trimmed;
        }
      }
    }
    if (currentChapter) chapters.push(currentChapter);

    // 未识别到章节 → 全文作为一个章节
    if (chapters.length === 0) {
      chapters.push({
        index: 0, title: "正文", preview: raw.slice(0, 100).replace(/\n/g, " "), selected: true,
      });
    }

    onChaptersReady(chapters);
    return chapters;
  }, [onChaptersReady]);

  const handleFile = useCallback(async (file: File) => {
    let text = "";
    const ext = file.name.split(".").pop()?.toLowerCase();

    if (ext === "docx") {
      try {
        const mammoth = await import("mammoth");
        const result = await mammoth.extractRawText({ arrayBuffer: await file.arrayBuffer() });
        text = result.value;
      } catch {
        text = await file.text();
      }
    } else {
      text = await file.text();
    }

    onTextReady(text);
    parseText(text);
  }, [onTextReady, parseText]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (disabled) return;
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, [disabled, handleFile]);

  const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  }, [handleFile]);

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors cursor-pointer
        ${dragOver ? "border-emerald-500 bg-emerald-500/5" : "border-zinc-700 hover:border-zinc-500"}
        ${disabled ? "opacity-40 pointer-events-none" : ""}`}
      onClick={() => fileRef.current?.click()}
    >
      <input ref={fileRef} type="file" accept=".txt,.docx,.md,.markdown" onChange={handleChange} className="hidden" />
      <p className="text-sm text-zinc-400 mb-1">
        {dragOver ? "Drop your file here" : "Drag & drop a file here, or click to browse"}
      </p>
      <p className="text-[10px] text-zinc-600">.txt &middot; .docx &middot; .md</p>
    </div>
  );
}

export function ChapterTree({ chapters, onToggle, onSelectAll, onDeselectAll }: {
  chapters: ChapterInfo[];
  onToggle: (index: number) => void;
  onSelectAll: () => void;
  onDeselectAll: () => void;
}) {
  if (chapters.length <= 1) return null;

  const selected = chapters.filter((c) => c.selected).length;
  return (
    <div className="mt-3 bg-zinc-900 border border-zinc-800 rounded-lg p-3 max-h-48 overflow-y-auto">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">
          Chapters ({selected}/{chapters.length})
        </span>
        <div className="flex gap-1">
          <button onClick={onSelectAll} className="text-[10px] text-zinc-500 hover:text-zinc-300">All</button>
          <span className="text-zinc-700">|</span>
          <button onClick={onDeselectAll} className="text-[10px] text-zinc-500 hover:text-zinc-300">None</button>
        </div>
      </div>
      {chapters.map((ch) => (
        <label key={ch.index}
          className="flex items-start gap-2 py-1 cursor-pointer hover:bg-zinc-800/30 rounded px-1 transition-colors">
          <input type="checkbox" checked={ch.selected} onChange={() => onToggle(ch.index)}
            className="mt-0.5 accent-emerald-600" />
          <div>
            <span className="text-xs text-zinc-200">{ch.title}</span>
            {ch.preview && <p className="text-[10px] text-zinc-600 truncate">{ch.preview}</p>}
          </div>
        </label>
      ))}
    </div>
  );
}
