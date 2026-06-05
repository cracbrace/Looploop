import { useState, useCallback, useEffect, useRef } from "react";
import { useScreenplay } from "./hooks/useScreenplay";
import { ShotCard } from "./components/ShotCard";
import { Sidebar } from "./components/Sidebar";
import { HistoryPanel } from "./components/HistoryPanel";
import { getYamlUrl, getWordUrl, saveScreenplay } from "./api/client";

// 左侧面板像素边界
const LEFT_MIN = 240;
const LEFT_MAX = 500;
const LEFT_DEFAULT = 360;

function App() {
  const {
    screenplay, status, progressMessage, progress,
    selectedSceneIndex, setSelectedSceneIndex,
    selectedShotId, setSelectedShotId,
    originalText, paragraphs,
    startConvert, handleRegenerateShot, updateScreenplay,
    loadFromHistory, taskId, reset,
  } = useScreenplay();

  const [inputText, setInputText] = useState("");
  const [showInput, setShowInput] = useState(true);
  const [showExport, setShowExport] = useState(false);
  const [historyKey, setHistoryKey] = useState(0);

  // --- 左侧面板像素拖拽状态 ---
  const [leftWidth, setLeftWidth] = useState(LEFT_DEFAULT);
  const dragging = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleLeftDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const onMove = (ev: MouseEvent) => {
      if (!dragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const x = ev.clientX - rect.left;
      setLeftWidth(Math.max(LEFT_MIN, Math.min(LEFT_MAX, Math.round(x))));
    };
    const onUp = () => {
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }, []);

  const handleStart = () => {
    if (inputText.trim().length < 100) return;
    setShowInput(false);
    startConvert(inputText);
  };
  const handleReset = () => { reset(); setShowInput(true); setInputText(""); };

  const handleShotClick = useCallback((shotId: string) => {
    setSelectedShotId(selectedShotId === shotId ? null : shotId);
  }, [selectedShotId, setSelectedShotId]);

  const handleHistorySelect = useCallback(async (historyTaskId: string) => {
    setShowInput(false); setSelectedShotId(null);
    await loadFromHistory(historyTaskId);
  }, [loadFromHistory, setSelectedShotId]);

  useEffect(() => { if (status === "done") setHistoryKey((k) => k + 1); }, [status]);

  const handleShotEdit = useCallback(async (sceneId: string, shotId: string, field: string, value: string) => {
    if (!taskId) return;
    let updated: any = null;
    updateScreenplay((prev: any) => {
      const newScenes = prev.scenes.map((scene: any) => {
        if (scene.scene_id !== sceneId) return scene;
        return {
          ...scene,
          shots: scene.shots.map((shot: any) => {
            if (shot.shot_id !== shotId) return shot;
            const s = { ...shot };
            switch (field) {
              case "visual_prompt": s.visual_prompt = value; break;
              case "focus_subject": s.focus_subject = value; break;
              case "duration": s.duration = value; break;
              case "sfx": s.sfx = value; break;
              case "dialogue_line": if (s.dialogue) s.dialogue = { ...s.dialogue, line: value }; break;
              case "dialogue_emotion": if (s.dialogue) s.dialogue = { ...s.dialogue, emotion: value }; break;
            }
            return s;
          }),
        };
      });
      updated = { ...prev, scenes: newScenes };
      return updated;
    });
    if (updated) saveScreenplay(taskId, updated).catch(() => {});
  }, [taskId, updateScreenplay]);

  const highlightedParagraphs: number[] = [];
  if (screenplay && selectedShotId) {
    for (const scene of screenplay.scenes)
      for (const shot of scene.shots)
        if (shot.shot_id === selectedShotId) highlightedParagraphs.push(...shot.source_paragraphs);
  }

  const selectedShot = screenplay && selectedShotId
    ? screenplay.scenes.flatMap((s: any) => s.shots).find((sh: any) => sh.shot_id === selectedShotId)
    : null;

  // ---- Input view ----
  if (showInput) {
    return (
      <div className="h-screen flex flex-col bg-[#050505] text-zinc-200">
        <Header status={status} progressMessage={progressMessage} hasScreenplay={false}
          showExport={false} setShowExport={() => {}} taskId={null} onReset={handleReset} />
        <div className="flex-1 flex">
          <div className="w-56 flex-shrink-0 border-r border-zinc-800/80 bg-[#0c0c0c]">
            <HistoryPanel currentTaskId={taskId} onSelect={handleHistorySelect} refreshKey={historyKey} />
          </div>
          <div className="flex-1 flex items-center justify-center p-8 bg-[#0a0a0a]">
            <InputView text={inputText} onChange={setInputText} onSubmit={handleStart}
              loading={status === "pending" || status === "running"} progress={progress} progressMessage={progressMessage} />
          </div>
        </div>
      </div>
    );
  }

  // ---- Loading ----
  if (!screenplay) {
    return (
      <div className="h-screen flex flex-col bg-[#050505] text-zinc-200">
        <Header status={status} progressMessage={progressMessage} hasScreenplay={false}
          showExport={false} setShowExport={() => {}} taskId={null} onReset={handleReset} />
        <LoadingView progress={progress} message={progressMessage} status={status} />
      </div>
    );
  }

  const scene = screenplay.scenes[selectedSceneIndex];

  // ---- Main result view ----
  return (
    <div className="h-screen flex flex-col bg-[#050505] text-zinc-200" ref={containerRef}>
      <Header status={status} progressMessage={progressMessage} hasScreenplay={true}
        showExport={showExport} setShowExport={setShowExport} taskId={taskId} onReset={handleReset} />

      <div className="flex-1 flex overflow-hidden">
        {/* 1. 左侧边栏：像素宽度，flex-shrink-0 禁止被挤压 */}
        <div
          style={{ width: `${leftWidth}px` }}
          className="flex flex-col flex-shrink-0 bg-[#0c0c0c] border-r border-zinc-800/80 overflow-hidden"
        >
          <div className="h-[35%] min-h-[100px]">
            <HistoryPanel currentTaskId={taskId} onSelect={handleHistorySelect} refreshKey={historyKey} />
          </div>
          <div className="flex-1 overflow-y-auto">
            <Sidebar
              scenes={screenplay.scenes}
              characters={screenplay.characters}
              meta={screenplay.meta}
              totalCharacters={screenplay.characters.length}
              selectedSceneIndex={selectedSceneIndex}
              onSelectScene={setSelectedSceneIndex}
            />
          </div>
          {/* Shot Detail */}
          <div className="border-t border-zinc-800/80 p-3 max-h-[35%] overflow-y-auto">
            <h3 className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-2">Shot Detail</h3>
            {selectedShot ? (
              <div className="space-y-1.5 text-[11px] text-zinc-400">
                <div><span className="text-zinc-600">Type</span> <span className="text-zinc-200 ml-1">{selectedShot.shot_type}</span></div>
                <div><span className="text-zinc-600">Movement</span> <span className="text-zinc-200 ml-1">{selectedShot.camera_movement}</span></div>
                <div><span className="text-zinc-600">Duration</span> <span className="text-zinc-200 ml-1">{selectedShot.duration}</span></div>
                <div><span className="text-zinc-600">Focus</span> <span className="text-zinc-200 ml-1">{selectedShot.focus_subject}</span></div>
                {selectedShot.sfx && <div><span className="text-zinc-600">SFX</span> <span className="text-amber-400/70 ml-1">{selectedShot.sfx}</span></div>}
                <div className="pt-1.5 border-t border-zinc-800/50 mt-1.5">
                  <p className="text-zinc-500 mb-0.5">Visual Prompt</p>
                  <p className="text-zinc-300 leading-snug">{selectedShot.visual_prompt}</p>
                </div>
              </div>
            ) : (
              <p className="text-[11px] text-zinc-600">Click a shot</p>
            )}
          </div>
        </div>

        {/* 2. 拖拽分隔条 */}
        <div
          onMouseDown={handleLeftDragStart}
          className="w-1.5 h-full cursor-col-resize flex-shrink-0 bg-transparent hover:bg-emerald-500/50 transition-colors duration-200 z-50"
          title="拖拽调整宽度"
        />

        {/* 3. 右侧主体：flex-1 min-w-0 防止子元素撑爆 */}
        <div className="flex-1 min-w-0 flex flex-row overflow-hidden bg-[#0a0a0a]">
          {/* 剧本分镜流 */}
          <div className="flex-1 min-w-0 overflow-y-auto p-6">
            <div className="max-w-3xl mx-auto">
              {!scene ? (
                <div className="text-zinc-500 p-8 text-center">Select a scene from the left panel</div>
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
                  <div className="space-y-3">
                    {scene.shots.map((shot: any) => (
                      <ShotCard key={shot.shot_id} shot={shot}
                        isSelected={shot.shot_id === selectedShotId}
                        onClick={() => handleShotClick(shot.shot_id)}
                        onRegenerate={(fb) => handleRegenerateShot(scene.scene_id, shot.shot_id, fb)}
                        onEdit={(f, v) => handleShotEdit(scene.scene_id, shot.shot_id, f, v)}
                      />
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>

          {/* 4. 右侧 Source Text 面板 */}
          <SourcePanel
            paragraphs={paragraphs}
            highlightedParagraphs={highlightedParagraphs}
            selectedShotId={selectedShotId}
          />
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Sub-components
// ============================================================

function SourcePanel({ paragraphs, highlightedParagraphs, selectedShotId }: {
  paragraphs: string[];
  highlightedParagraphs: number[];
  selectedShotId: string | null;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  if (collapsed) {
    return (
      <div className="flex-shrink-0 border-l border-zinc-800/80 bg-[#0c0c0c] flex flex-col items-center pt-3 w-8">
        <button onClick={() => setCollapsed(false)}
          className="text-zinc-500 hover:text-zinc-300 text-xs transition-colors"
          title="Expand source panel">&#171;</button>
        {selectedShotId && (
          <div className="mt-2 w-1.5 h-1.5 rounded-full bg-amber-500" title="Source available" />
        )}
      </div>
    );
  }

  const highlightSet = new Set(highlightedParagraphs);

  return (
    <div ref={panelRef} className="w-72 flex-shrink-0 border-l border-zinc-800/80 bg-[#0c0c0c] flex flex-col overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800/80 shrink-0">
        <h4 className="text-[10px] font-bold text-zinc-500 tracking-wider uppercase">Source Text</h4>
        <button onClick={() => setCollapsed(true)}
          className="text-zinc-500 hover:text-zinc-300 text-xs transition-colors"
          title="Collapse source panel">&#187;</button>
      </div>

      {!selectedShotId ? (
        <div className="flex-1 flex items-center justify-center p-4">
          <p className="text-[11px] text-zinc-600 text-center">Click a shot card<br />to view source text</p>
        </div>
      ) : paragraphs.length === 0 ? (
        <div className="flex-1 flex items-center justify-center p-4">
          <p className="text-[11px] text-zinc-600">Original text not available</p>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-3">
          {highlightedParagraphs.length > 0 && (
            <p className="text-[10px] text-amber-400 mb-2">
              &para; {highlightedParagraphs.join(", ")}
            </p>
          )}
          {paragraphs.map((p, i) => (
            <p key={i}
              className={`text-[11px] leading-relaxed mb-2 px-2 py-1 rounded transition-colors
                ${highlightSet.has(i)
                  ? "bg-amber-500/10 text-amber-200 border-l-2 border-amber-500 pl-2.5"
                  : "text-zinc-500"}`}
            >
              <span className="text-zinc-600 mr-1.5 font-mono text-[10px]">{i}</span>
              {p.slice(0, 250)}
              {p.length > 250 ? "…" : ""}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

function Header({ status, progressMessage, hasScreenplay, showExport, setShowExport, taskId, onReset }: {
  status: string; progressMessage: string; hasScreenplay: boolean;
  showExport: boolean; setShowExport: (b: boolean) => void; taskId: string | null; onReset: () => void;
}) {
  return (
    <header className="h-10 flex items-center justify-between px-4 border-b border-zinc-800/80 shrink-0 bg-[#080808]">
      <h1 className="text-[11px] font-semibold tracking-tight text-zinc-400">
        Looploop <span className="text-zinc-600 font-normal">噜噜</span>
      </h1>
      <div className="flex items-center gap-2">
        {status === "running" && <span className="text-[10px] text-zinc-500">{progressMessage}</span>}
        {hasScreenplay && (
          <>
            <div className="relative">
              <button onClick={() => setShowExport(!showExport)}
                className="text-[10px] px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 rounded border border-zinc-700/50 transition-colors">
                Export
              </button>
              {showExport && taskId && (
                <div className="absolute right-0 top-8 w-36 bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl z-50 py-1">
                  <a href={getYamlUrl(taskId)} onClick={() => setShowExport(false)}
                    className="block px-3 py-1.5 text-[10px] text-zinc-300 hover:bg-zinc-700">YAML (AI Pipeline)</a>
                  <a href={getWordUrl(taskId)} onClick={() => setShowExport(false)}
                    className="block px-3 py-1.5 text-[10px] text-zinc-300 hover:bg-zinc-700">Word (Edit)</a>
                </div>
              )}
            </div>
            <button onClick={onReset}
              className="text-[10px] px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 rounded border border-zinc-700/50 transition-colors">
              New
            </button>
          </>
        )}
      </div>
    </header>
  );
}

function InputView({ text, onChange, onSubmit, loading, progress, progressMessage }: {
  text: string; onChange: (v: string) => void; onSubmit: () => void;
  loading: boolean; progress: number; progressMessage: string;
}) {
  return (
    <div className="w-full max-w-2xl">
      <h2 className="text-xl font-semibold mb-2">Start a New Screenplay</h2>
      <p className="text-zinc-500 text-sm mb-4">Paste 3+ chapters. AI extracts scenes, shots, and dialogue automatically.</p>
      <textarea value={text} onChange={(e) => onChange(e.target.value)}
        placeholder="Paste your novel text here..."
        className="w-full h-56 bg-zinc-900 border border-zinc-700 rounded-lg p-4 text-sm text-zinc-200
                   placeholder-zinc-600 resize-none focus:outline-none focus:border-zinc-500 transition-colors"
        disabled={loading} />
      <div className="mt-4 flex items-center justify-between">
        <span className="text-xs text-zinc-600">{text.length} chars (min 100)</span>
        <button onClick={onSubmit} disabled={text.trim().length < 100 || loading}
          className="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40
                     disabled:cursor-not-allowed rounded-lg text-sm font-medium transition-colors">
          {loading ? `Converting ${Math.round(progress * 100)}%` : "Convert"}
        </button>
      </div>
      {loading && (
        <>
          <div className="mt-4 w-full bg-zinc-800 rounded-full h-1 overflow-hidden">
            <div className="h-full bg-emerald-500 transition-all duration-300 rounded-full"
              style={{ width: `${Math.round(progress * 100)}%` }} />
          </div>
          <p className="mt-2 text-xs text-zinc-500 text-center">{progressMessage}</p>
        </>
      )}
    </div>
  );
}

function LoadingView({ progress, message, status }: { progress: number; message: string; status: string }) {
  if (status === "error") {
    return (
      <div className="flex-1 flex items-center justify-center bg-[#0a0a0a]">
        <div className="text-center"><p className="text-red-400 mb-2">Conversion Failed</p>
          <p className="text-zinc-500 text-sm">{message}</p></div>
      </div>
    );
  }
  return (
    <div className="flex-1 flex items-center justify-center bg-[#0a0a0a]">
      <div className="text-center">
        <div className="w-8 h-8 border-2 border-zinc-700 border-t-emerald-400 rounded-full animate-spin mx-auto mb-4" />
        <p className="text-zinc-400 text-sm">{message}</p>
        <div className="mt-4 w-48 bg-zinc-800 rounded-full h-1 overflow-hidden mx-auto">
          <div className="h-full bg-emerald-500 transition-all duration-300 rounded-full"
            style={{ width: `${Math.round(progress * 100)}%` }} />
        </div>
      </div>
    </div>
  );
}

export default App;
