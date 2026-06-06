import { useState, useRef, useCallback } from "react";

interface ChapterInfo {
  index: number;
  title: string;
  preview: string;
  selected: boolean;
  startLine: number;
  endLine: number;
  text: string;
}

interface DropZoneProps {
  onChaptersReady: (chapters: ChapterInfo[]) => void;
  onTextReady: (text: string) => void;
  disabled: boolean;
}

const CHAPTER_RE = /^(第[一二三四五六七八九十百千\d]+[章节回]\b|Chapter\s+\d+)/m;

function normalizeText(raw: string): string {
  let t = raw.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  // 在非行首的章节标记前插入换行
  t = t.replace(/(?<=[。！？!?\n])\s*(第[一二三四五六七八九十百千\d]+[章节回]\b)/g, "\n$1");
  t = t.replace(/(?<=[.?!\n])\s*(Chapter\s+\d+)/gi, "\n$1");
  return t.replace(/\n{3,}/g, "\n\n").trim();
}

export function DropZone({ onChaptersReady, onTextReady, disabled }: DropZoneProps) {
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const parseText = useCallback((raw: string) => {
    const normalized = normalizeText(raw);
    console.log("[ChapterTree] parseText called, raw length:", raw.length, "normalized length:", normalized.length);
    const lines = normalized.split("\n");
    const chapters: ChapterInfo[] = [];
    let currentChapter: ChapterInfo | null = null;
    let chapterStartLine = 0;

    for (let i = 0; i < lines.length; i++) {
      const trimmed = lines[i].trim();

      if (CHAPTER_RE.test(trimmed)) {
        if (currentChapter) {
          currentChapter.endLine = i;
          currentChapter.text = lines.slice(currentChapter.startLine, i).join("\n");
          chapters.push(currentChapter);
        }
        chapterStartLine = i;
        currentChapter = {
          index: chapters.length,
          title: trimmed.slice(0, 60),
          preview: "",
          selected: true,
          startLine: i,
          endLine: i,
          text: "",
        };
      } else if (currentChapter && trimmed) {
        if (currentChapter.preview.length < 80) {
          currentChapter.preview += (currentChapter.preview ? " " : "") + trimmed;
        }
      }
    }
    if (currentChapter) {
      currentChapter.endLine = lines.length;
      currentChapter.text = lines.slice(currentChapter.startLine, lines.length).join("\n");
      chapters.push(currentChapter);
    }

    console.log("[ChapterTree] detected chapters:", chapters.length,
      chapters.map(c => c.title).join(", "),
      "will call onChaptersReady after fallback check");
    if (chapters.length === 0) {
      chapters.push({
        index: 0, title: "全文", preview: raw.slice(0, 100).replace(/\n/g, " "),
        selected: true, startLine: 0, endLine: lines.length, text: raw,
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
  console.log("[ChapterTree] render called, chapters.length:", chapters.length);
  if (chapters.length <= 1) {
    console.log("[ChapterTree] hidden — need ≥2 chapters, got", chapters.length);
    return null;
  }

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
