import { useState, useCallback, useEffect, useRef } from "react";
import { useScreenplay } from "./hooks/useScreenplay";
import { ShotCard } from "./components/ShotCard";
import { Sidebar } from "./components/Sidebar";
import { HistoryPanel } from "./components/HistoryPanel";
import { DropZone, ChapterTree } from "./components/DropZone";
import { LogDrawer } from "./components/LogDrawer";
import { getYamlUrl, getWordUrl, getManifestUrl, saveScreenplay } from "./api/client";

const LEFT_MIN = 240;
const LEFT_MAX = 500;
const LEFT_DEFAULT = 320;
const BOTTOM_MIN = 120;
const BOTTOM_MAX = 500;
const BOTTOM_DEFAULT = 200;

function App() {
  const {
    screenplay, status, progressMessage, progress,
    selectedSceneIndex, setSelectedSceneIndex,
    selectedShotId, setSelectedShotId,
    originalText, paragraphs,
    startConvert, handleRegenerateShot, updateScreenplay,
    undo, redo, canUndo, canRedo,
    loadFromHistory, taskId, reset,
  } = useScreenplay();

  const [inputText, setInputText] = useState("");
  const [showInput, setShowInput] = useState(true);
  const [showExport, setShowExport] = useState(false);
  const [historyKey, setHistoryKey] = useState(0);
  const [logOpen, setLogOpen] = useState(false);
  const [pipelineLogs, setPipelineLogs] = useState<Array<{ id: number; level: "info"|"warn"|"error"; message: string; time: string }>>([]);
  const logIdRef = useRef(0);
  // Chapter selection state (moved from InputView to App for filtering)
  const [chapters, setChapters] = useState<Array<{ index: number; title: string; preview: string; selected: boolean; startLine: number; endLine: number; text: string }>>([]);

  // 左侧面板像素宽度
  const [leftWidth, setLeftWidth] = useState(LEFT_DEFAULT);
  const containerRef = useRef<HTMLDivElement>(null);

  // 底部原文面板像素高度
  const [bottomHeight, setBottomHeight] = useState(BOTTOM_DEFAULT);
  const bottomStartRef = useRef({ startY: 0, startHeight: 0 });

  // ---- 左侧水平拖拽 ----
  const handleLeftDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    const onMove = (ev: MouseEvent) => {
      if (!containerRef.current) return;
      const x = ev.clientX - containerRef.current.getBoundingClientRect().left;
      setLeftWidth(Math.max(LEFT_MIN, Math.min(LEFT_MAX, Math.round(x))));
    };
    const onUp = () => {
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }, []);

  // ---- 底部垂直拖拽 ----
  const handleBottomDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";
    bottomStartRef.current = { startY: e.clientY, startHeight: bottomHeight };
    const onMove = (ev: MouseEvent) => {
      const delta = bottomStartRef.current.startY - ev.clientY;
      setBottomHeight(Math.max(BOTTOM_MIN, Math.min(BOTTOM_MAX, bottomStartRef.current.startHeight + delta)));
    };
    const onUp = () => {
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }, [bottomHeight]);

  const handleStart = () => {
    // Filter text by selected chapters
    let effectiveText = inputText;
    const selected = chapters.filter(c => c.selected);
    if (selected.length > 0 && selected.length < chapters.length) {
      effectiveText = selected.map(c => c.text).join("\n\n");
    }
    if (effectiveText.trim().length < 100) return;
    setShowInput(false);
    setPipelineLogs([]);
    logIdRef.current = 0;
    startConvert(effectiveText, (logMsg: string) => {
      const now = new Date();
      const time = `${String(now.getHours()).padStart(2,"0")}:${String(now.getMinutes()).padStart(2,"0")}:${String(now.getSeconds()).padStart(2,"0")}`;
      const level: "info"|"warn"|"error" = logMsg.includes("失败") || logMsg.includes("Error") ? "error" : logMsg.includes("合并") || logMsg.includes("新增") ? "warn" : "info";
      setPipelineLogs((prev) => [...prev, { id: ++logIdRef.current, level, message: logMsg, time }]);
    });
  };
  const handleReset = () => { reset(); setShowInput(true); setInputText(""); };
  const handleShotClick = useCallback((id: string) => setSelectedShotId(selectedShotId === id ? null : id), [selectedShotId, setSelectedShotId]);
  const handleHistorySelect = useCallback(async (id: string) => { setShowInput(false); setSelectedShotId(null); await loadFromHistory(id); }, [loadFromHistory, setSelectedShotId]);
  useEffect(() => { if (status === "done") setHistoryKey((k) => k + 1); }, [status]);

  // Ctrl+Z / Ctrl+Y keyboard handler
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "z" && !e.shiftKey) {
        e.preventDefault();
        if (canUndo()) { undo(); if (taskId) saveScreenplay(taskId, screenplay!).catch(() => {}); }
      }
      if ((e.ctrlKey || e.metaKey) && (e.key === "y" || (e.key === "z" && e.shiftKey))) {
        e.preventDefault();
        if (canRedo()) { redo(); if (taskId) saveScreenplay(taskId, screenplay!).catch(() => {}); }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [canUndo, canRedo, undo, redo, taskId, screenplay]);

  // Shot reorder handler
  const handleShotReorder = useCallback(async (sceneId: string, fromIndex: number, toIndex: number) => {
    if (!taskId || fromIndex === toIndex) return;
    let updated: any = null;
    updateScreenplay((prev: any) => {
      const ns = prev.scenes.map((scene: any) => {
        if (scene.scene_id !== sceneId) return scene;
        const shots = [...scene.shots];
        const [moved] = shots.splice(fromIndex, 1);
        shots.splice(toIndex, 0, moved);
        // Renumber
        const renumbered = shots.map((s: any, i: number) => ({
          ...s, shot_number: i + 1, shot_id: `${sceneId}_${String(i + 1).padStart(2, "0")}`,
        }));
        return { ...scene, shots: renumbered };
      });
      updated = { ...prev, scenes: ns };
      return updated;
    });
    if (updated) saveScreenplay(taskId, updated).catch(() => {});
  }, [taskId, updateScreenplay]);

  const handleShotEdit = useCallback(async (sceneId: string, shotId: string, field: string, value: string) => {
    if (!taskId) return;
    let updated: any = null;
    updateScreenplay((prev: any) => {
      const ns = prev.scenes.map((s: any) => s.scene_id !== sceneId ? s : {
        ...s, shots: s.shots.map((sh: any) => {
          if (sh.shot_id !== shotId) return sh;
          const c = { ...sh };
          switch (field) {
            case "visual_prompt": c.visual_prompt = value; break;
            case "focus_subject": c.focus_subject = value; break;
            case "duration": c.duration = value; break;
            case "sfx": c.sfx = value; break;
            case "dialogue_line": if (c.dialogue) c.dialogue = { ...c.dialogue, line: value }; break;
            case "dialogue_emotion": if (c.dialogue) c.dialogue = { ...c.dialogue, emotion: value }; break;
          }
          return c;
        }),
      });
      updated = { ...prev, scenes: ns };
      return updated;
    });
    if (updated) saveScreenplay(taskId, updated).catch(() => {});
  }, [taskId, updateScreenplay]);

  const selectedShot = screenplay && selectedShotId
    ? screenplay.scenes.flatMap((s: any) => s.shots).find((sh: any) => sh.shot_id === selectedShotId) : null;

  // ── Input ──
  if (showInput) {
    return (
      <div className="h-screen flex flex-col bg-[#050505] text-zinc-200">
        <Header status={status} msg={progressMessage} hasSP={false} canUndo={false} canRedo={false} onUndo={() => {}} onRedo={() => {}} showExport={false} setShowExport={() => {}} taskId={null} onReset={handleReset} />
        <div className="flex-1 flex">
          <div style={{ width: `${LEFT_DEFAULT}px` }} className="flex-shrink-0 border-r border-zinc-800/60 bg-[#0c0c0c] overflow-hidden">
            <HistoryPanel currentTaskId={taskId} onSelect={handleHistorySelect} refreshKey={historyKey} />
          </div>
          <div className="flex-1 flex items-center justify-center p-8 bg-[#0a0a0a]">
            <InputView text={inputText} onChange={setInputText} onSubmit={handleStart}
              chapters={chapters} setChapters={setChapters}
              loading={status === "pending" || status === "running"} progress={progress} msg={progressMessage} />
          </div>
        </div>
      </div>
    );
  }

  // ── Loading ──
  if (!screenplay) {
    return (
      <div className="h-screen flex flex-col bg-[#050505] text-zinc-200">
        <Header status={status} msg={progressMessage} hasSP={false} canUndo={false} canRedo={false} onUndo={() => {}} onRedo={() => {}} showExport={false} setShowExport={() => {}} taskId={null} onReset={handleReset} />
        <LoadingView progress={progress} message={progressMessage} status={status} />
      </div>
    );
  }

  const scene = screenplay.scenes[selectedSceneIndex];

  // 当前场景的段落索引 + 选中镜头高亮 (必须在 scene 声明之后)
  const sceneParagraphs: number[] = [];
  const highlightedParagraphs: number[] = [];
  if (scene) {
    for (const sh of scene.shots) sceneParagraphs.push(...sh.source_paragraphs);
    if (selectedShotId)
      for (const sh of scene.shots)
        if (sh.shot_id === selectedShotId) highlightedParagraphs.push(...sh.source_paragraphs);
  }

  // ── Main ──
  return (
    <div className="h-screen flex flex-col bg-[#050505] text-zinc-200" ref={containerRef}>
      <Header status={status} msg={progressMessage} hasSP={true} showExport={showExport} setShowExport={setShowExport} taskId={taskId} onReset={handleReset}
        canUndo={canUndo()} canRedo={canRedo()} onUndo={() => { undo(); if (taskId && screenplay) saveScreenplay(taskId, screenplay).catch(() => {}); }}
        onRedo={() => { redo(); if (taskId && screenplay) saveScreenplay(taskId, screenplay).catch(() => {}); }} />
      <LogDrawer logs={pipelineLogs} open={logOpen} onToggle={() => setLogOpen(!logOpen)} onClear={() => setPipelineLogs([])} />

      <div className="flex-1 flex overflow-hidden">
        {/* ═══════════════════════════════════════════════════════ */}
        {/* 左侧边栏：历史/场景导航/角色 + 底部 Shot Detail */}
        {/* ═══════════════════════════════════════════════════════ */}
        <div style={{ width: `${leftWidth}px` }}
          className="flex flex-col flex-shrink-0 bg-[#0c0c0c] border-r border-zinc-800/60 overflow-hidden">
          {/* Upper: Shot Detail (high info density, benefits from flex space) */}
          <div className="flex-1 overflow-y-auto">
            <HistorySection
              currentTaskId={taskId}
              onSelect={handleHistorySelect}
              refreshKey={historyKey}
            />
            <div className="p-3">
              <div className="text-[10px] font-bold text-emerald-500/80 uppercase tracking-wider mb-2">Shot Detail</div>
              {selectedShot ? (
                <div className="space-y-1.5 text-[11px] text-zinc-400">
                  <div><span className="text-zinc-600">Type</span> <span className="text-zinc-200 ml-1">{selectedShot.shot_type}</span></div>
                  <div><span className="text-zinc-600">Movement</span> <span className="text-zinc-200 ml-1">{selectedShot.camera_movement}</span></div>
                  <div><span className="text-zinc-600">Duration</span> <span className="text-zinc-200 ml-1">{selectedShot.duration}</span></div>
                  <div><span className="text-zinc-600">Focus</span> <span className="text-zinc-200 ml-1">{selectedShot.focus_subject}</span></div>
                  {selectedShot.sfx && <div><span className="text-zinc-600">SFX</span> <span className="text-amber-400/70 ml-1">{selectedShot.sfx}</span></div>}
                  <div className="pt-1.5 mt-1.5 border-t border-zinc-800/50">
                    <p className="text-zinc-500 mb-0.5">Visual Prompt</p>
                    <p className="text-zinc-300 leading-snug break-words">{selectedShot.visual_prompt}</p>
                  </div>
                </div>
              ) : (
                <p className="text-[11px] text-zinc-600">Click a shot to see details</p>
              )}
            </div>
          </div>
          {/* Bottom: Scene nav + Characters (compact, low density) */}
          <div className="border-t border-zinc-800/80 bg-[#090909] shrink-0">
            <Sidebar
              scenes={screenplay.scenes} characters={screenplay.characters}
              meta={screenplay.meta} totalCharacters={screenplay.characters.length}
              selectedSceneIndex={selectedSceneIndex} onSelectScene={setSelectedSceneIndex}
            />
          </div>
          {/* Scene nav + Characters (compact, fixed bottom) */}
          <div className="h-40 border-t border-zinc-800/80 bg-[#090909] p-3 overflow-y-auto shrink-0">
            {screenplay.characters.map((c: any) => (
              <span key={c.character_id} className="inline-block text-[11px] text-zinc-400 mr-3 mb-1">
                {c.canonical_name}
              </span>
            ))}
            <div className="text-[10px] text-zinc-600 mt-2 pt-2 border-t border-zinc-800/50">
              {screenplay.meta.total_scenes} scenes · {screenplay.meta.total_shots} shots · {screenplay.meta.total_duration_estimate}
            </div>
          </div>
        </div>

        {/* 水平拖拽条 */}
        <div onMouseDown={handleLeftDragStart}
          className="w-1.5 cursor-col-resize flex-shrink-0 bg-transparent hover:bg-emerald-500/30 transition-colors z-50" />

        {/* ═══════════════════════════════════════════════════════ */}
        {/* 右侧主核心区：上下分层 */}
        {/* ═══════════════════════════════════════════════════════ */}
        <div className="flex-1 min-w-0 flex flex-col bg-[#0a0a0a] overflow-hidden">

          {/* 上：剧本分镜流 —— 独占最大横向空间 */}
          <div className="flex-1 min-h-0 overflow-y-auto p-6">
            <div className="max-w-4xl mx-auto">
              {!scene ? (
                <div className="text-zinc-500 p-12 text-center text-sm">Select a scene from the left panel</div>
              ) : (
                <>
                  <div className="mb-6">
                    <h2 className="text-lg font-semibold mb-1">
                      {scene.scene_id} &middot; {scene.location}
                    </h2>
                    <p className="text-xs text-zinc-500">
                      {scene.time_of_day} &middot; {scene.atmosphere}
                      {scene.era && <span> &middot; {scene.era}</span>}
                      {scene.weather && <span> &middot; {scene.weather}</span>}
                      <span className="ml-2 text-zinc-600">| {scene.duration_estimate}</span>
                    </p>
                  </div>
                  <div className="space-y-4">
                    {scene.shots.map((shot: any, idx: number) => (
                      <ShotCard key={shot.shot_id} shot={shot} shotIndex={idx}
                        isSelected={shot.shot_id === selectedShotId}
                        onClick={() => handleShotClick(shot.shot_id)}
                        onRegenerate={(fb) => handleRegenerateShot(scene.scene_id, shot.shot_id, fb)}
                        onEdit={(f, v) => handleShotEdit(scene.scene_id, shot.shot_id, f, v)}
                        onDragStart={(e, fromIdx) => { e.dataTransfer.setData("text/plain", String(fromIdx)); }}
                        onDragOver={(e) => { e.preventDefault(); }}
                        onDrop={(e, toIdx) => {
                          const fromIdx = parseInt(e.dataTransfer.getData("text/plain"));
                          if (!isNaN(fromIdx)) handleShotReorder(scene.scene_id, fromIdx, toIdx);
                        }}
                      />
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>

          {/* 垂直拖拽条 */}
          <div onMouseDown={handleBottomDragStart}
            className="h-[6px] cursor-row-resize flex-shrink-0 bg-zinc-900 hover:bg-emerald-500/40 transition-colors z-50 relative group">
            <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-[2px] w-12 mx-auto bg-zinc-600 group-hover:bg-emerald-400/70 group-hover:w-20 transition-all rounded-full" />
          </div>

          {/* 下：原文对照面板 —— 横向通栏，长文本阅读 */}
          <div style={{ height: `${bottomHeight}px` }}
            className="flex-shrink-0 bg-[#0c0c0c] border-t border-zinc-800/60 flex flex-col overflow-hidden">
            <div className="px-4 py-2 bg-[#111] border-b border-zinc-900 flex justify-between items-center shrink-0">
              <span className="text-[10px] font-bold text-zinc-400 tracking-wider uppercase">
                Source Text (原文对照)
              </span>
              <span className="text-[10px] text-zinc-600">
                {selectedShotId
                  ? `Scene: ${scene.scene_id} · Paragraphs: ${highlightedParagraphs.join(", ") || "none"}`
                  : `Scene: ${scene.scene_id} · ${sceneParagraphs.length} paragraphs`}
              </span>
            </div>
            <div className="flex-1 overflow-y-auto p-4 font-serif text-sm leading-relaxed text-zinc-400">
              {paragraphs.length === 0 ? (
                <p className="text-zinc-600 text-xs">Original text not available for this session</p>
              ) : (
                (() => {
                  const hs = new Set(highlightedParagraphs);
                  const sp = new Set(sceneParagraphs);
                  const filtered = paragraphs
                    .map((p, i) => ({ p, i }))
                    .filter(({ i }) => sp.has(i));
                  if (filtered.length === 0) {
                    return <p className="text-xs text-zinc-600">No source paragraphs mapped for this scene</p>;
                  }
                  return filtered.map(({ p, i }) => (
                    <p key={i}
                      className={`mb-2 px-3 py-1.5 rounded transition-all
                        ${hs.has(i)
                          ? "bg-amber-500/10 text-amber-200 border-l-2 border-amber-500 pl-4"
                          : "text-zinc-500 border-l-2 border-transparent pl-4 hover:text-zinc-300"
                        }`}
                    >
                      <span className="text-zinc-600 mr-2 font-mono text-xs align-top">{i}</span>
                      {p}
                    </p>
                  ));
                })()
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// Sub-components
// ═══════════════════════════════════════════════════════════

function Header({ status, msg, hasSP, showExport, setShowExport, taskId, onReset, canUndo, canRedo, onUndo, onRedo }: {
  status: string; msg: string; hasSP: boolean;
  showExport: boolean; setShowExport: (b: boolean) => void; taskId: string | null; onReset: () => void;
  canUndo: boolean; canRedo: boolean; onUndo: () => void; onRedo: () => void;
}) {
  return (
    <header className="h-10 flex items-center justify-between px-4 border-b border-zinc-800/80 shrink-0 bg-[#080808]">
      <h1 className="text-[11px] font-semibold tracking-tight text-zinc-400">
        Looploop <span className="text-zinc-600 font-normal">噜噜</span>
      </h1>
      <div className="flex items-center gap-2">
        {status === "running" && <span className="text-[10px] text-zinc-500">{msg}</span>}
        {hasSP && (
          <>
            <div className="flex items-center gap-1 mr-1 border-r border-zinc-700/50 pr-2">
              <button onClick={onUndo} disabled={!canUndo}
                className="text-[10px] px-1.5 py-0.5 rounded hover:bg-zinc-700 disabled:opacity-30 disabled:cursor-default transition-colors"
                title="Undo (Ctrl+Z)">↩</button>
              <button onClick={onRedo} disabled={!canRedo}
                className="text-[10px] px-1.5 py-0.5 rounded hover:bg-zinc-700 disabled:opacity-30 disabled:cursor-default transition-colors"
                title="Redo (Ctrl+Y)">↪</button>
            </div>
            <div className="relative">
              <button onClick={() => setShowExport(!showExport)}
                className="text-[10px] px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 rounded border border-zinc-700/50 transition-colors">Export</button>
              {showExport && taskId && (
                <div className="absolute right-0 top-8 w-36 bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl z-50 py-1">
                  <a href={getYamlUrl(taskId)} onClick={() => setShowExport(false)}
                    className="block px-3 py-1.5 text-[10px] text-zinc-300 hover:bg-zinc-700">YAML (AI Pipeline)</a>
                  <a href={getManifestUrl(taskId)} onClick={() => setShowExport(false)}
                    className="block px-3 py-1.5 text-[10px] text-zinc-300 hover:bg-zinc-700">Manifest (C/S/P)</a>
                  <a href={getWordUrl(taskId)} onClick={() => setShowExport(false)}
                    className="block px-3 py-1.5 text-[10px] text-zinc-300 hover:bg-zinc-700">Word (Edit)</a>
                </div>
              )}
            </div>
            <button onClick={onReset}
              className="text-[10px] px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 rounded border border-zinc-700/50 transition-colors">New</button>
          </>
        )}
      </div>
    </header>
  );
}

function HistorySection({ currentTaskId, onSelect, refreshKey }: {
  currentTaskId: string | null; onSelect: (id: string) => void; refreshKey: number;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2 text-[10px] font-bold text-zinc-500
                   tracking-wider uppercase hover:bg-zinc-800/30 transition-colors border-b border-zinc-900"
      >
        History
        <span className={`text-zinc-600 transition-transform ${open ? "rotate-90" : ""}`}>&#8250;</span>
      </button>
      {open && (
        <div className="border-b border-zinc-900">
          <HistoryPanel currentTaskId={currentTaskId} onSelect={onSelect} refreshKey={refreshKey} />
        </div>
      )}
    </div>
  );
}

function InputView({ text, onChange, onSubmit, loading, progress, msg, chapters, setChapters }: {
  text: string; onChange: (v: string) => void; onSubmit: () => void;
  loading: boolean; progress: number; msg: string;
  chapters: Array<{ index: number; title: string; preview: string; selected: boolean; startLine: number; endLine: number; text: string }>;
  setChapters: React.Dispatch<React.SetStateAction<Array<{ index: number; title: string; preview: string; selected: boolean; startLine: number; endLine: number; text: string }>>>;
}) {
  const chapterTimer = useRef<ReturnType<typeof setTimeout>>();

  const handleTextReady = (raw: string) => onChange(raw);
  const handleChaptersReady = (chs: Array<{ index: number; title: string; preview: string; selected: boolean; startLine: number; endLine: number; text: string }>) => setChapters(chs);
  const toggleChapter = (i: number) => setChapters((prev) => prev.map((c) => c.index === i ? { ...c, selected: !c.selected } : c));

  // Debounced re-parse when text changes (for pasted text, not just drag-and-drop)
  useEffect(() => {
    if (chapterTimer.current) clearTimeout(chapterTimer.current);
    chapterTimer.current = setTimeout(() => {
      if (text.trim().length > 50 && chapters.length === 0) {
        // Only trigger if no chapters detected yet (DropZone takes priority)
        // Manually parse here using same logic as DropZone
        const norm = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n")
          .replace(/(?<=[。！？!?\n])\s*(第[一二三四五六七八九十百千\d]+[章节回]\b)/g, "\n$1")
          .replace(/\n{3,}/g, "\n\n").trim();
        const lines = norm.split("\n");
        const chs: any[] = [];
        let cur: any = null;
        for (let i = 0; i < lines.length; i++) {
          const t = lines[i].trim();
          if (/^(第[一二三四五六七八九十百千\d]+[章节回]\b|Chapter\s+\d+)/m.test(t)) {
            if (cur) { cur.endLine = i; cur.text = lines.slice(cur.startLine, i).join("\n"); chs.push(cur); }
            cur = { index: chs.length, title: t.slice(0, 60), preview: "", selected: true, startLine: i, endLine: i, text: "" };
          } else if (cur && t && cur.preview.length < 80) {
            cur.preview += (cur.preview ? " " : "") + t;
          }
        }
        if (cur) { cur.endLine = lines.length; cur.text = lines.slice(cur.startLine, lines.length).join("\n"); chs.push(cur); }
        if (chs.length > 1) setChapters(chs);
      }
    }, 600);
    return () => { if (chapterTimer.current) clearTimeout(chapterTimer.current); };
  }, [text]);

  const effectiveText = text;

  return (
    <div className="w-full max-w-2xl">
      <h2 className="text-xl font-semibold mb-2">Start a New Screenplay</h2>
      <p className="text-zinc-500 text-sm mb-4">Drop a .txt / .docx / .md file, or paste text below. AI extracts scenes, shots, and dialogue automatically.</p>
      <DropZone onChaptersReady={handleChaptersReady} onTextReady={handleTextReady} disabled={loading} />
      <ChapterTree chapters={chapters} onToggle={toggleChapter}
        onSelectAll={() => setChapters((prev) => prev.map((c) => ({ ...c, selected: true })))}
        onDeselectAll={() => setChapters((prev) => prev.map((c) => ({ ...c, selected: false })))} />
      <textarea value={text} onChange={(e) => onChange(e.target.value)}
        placeholder="Or paste your novel text here..."
        className="mt-3 w-full h-40 bg-zinc-900 border border-zinc-700 rounded-lg p-4 text-sm text-zinc-200
                   placeholder-zinc-600 resize-none focus:outline-none focus:border-zinc-500 transition-colors"
        disabled={loading} />
      <div className="mt-4 flex items-center justify-between">
        <span className="text-xs text-zinc-600">{effectiveText.length} chars (min 100)</span>
        <button onClick={onSubmit} disabled={effectiveText.trim().length < 100 || loading}
          className="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40
                     disabled:cursor-not-allowed rounded-lg text-sm font-medium transition-colors">
          {loading ? `Converting ${Math.round(progress * 100)}%` : "Convert"}
        </button>
      </div>
      {loading && (
        <>
          <div className="mt-4 w-full bg-zinc-800 rounded-full h-1 overflow-hidden">
            <div className="h-full bg-emerald-500 transition-all duration-300 rounded-full" style={{ width: `${Math.round(progress * 100)}%` }} />
          </div>
          <p className="mt-2 text-xs text-zinc-500 text-center">{msg}</p>
        </>
      )}
    </div>
  );
}

function LoadingView({ progress, message, status }: { progress: number; message: string; status: string }) {
  if (status === "error")
    return <div className="flex-1 flex items-center justify-center bg-[#0a0a0a]"><div className="text-center"><p className="text-red-400 mb-2">Conversion Failed</p><p className="text-zinc-500 text-sm">{message}</p></div></div>;
  return (
    <div className="flex-1 flex items-center justify-center bg-[#0a0a0a]">
      <div className="text-center">
        <div className="w-8 h-8 border-2 border-zinc-700 border-t-emerald-400 rounded-full animate-spin mx-auto mb-4" />
        <p className="text-zinc-400 text-sm">{message}</p>
        <div className="mt-4 w-48 bg-zinc-800 rounded-full h-1 overflow-hidden mx-auto">
          <div className="h-full bg-emerald-500 transition-all duration-300 rounded-full" style={{ width: `${Math.round(progress * 100)}%` }} />
        </div>
      </div>
    </div>
  );
}

export default App;
