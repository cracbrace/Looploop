import { useState, useCallback, useEffect } from "react";
import { Panel, Group, Separator } from "react-resizable-panels";
import { useScreenplay } from "./hooks/useScreenplay";
import { ShotCard } from "./components/ShotCard";
import { Sidebar } from "./components/Sidebar";
import { SourcePanel } from "./components/SourcePanel";
import { HistoryPanel } from "./components/HistoryPanel";
import { getYamlUrl, getWordUrl, saveScreenplay } from "./api/client";

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
  const [showSource, setShowSource] = useState(false);
  const [showExport, setShowExport] = useState(false);
  const [historyKey, setHistoryKey] = useState(0);

  const handleStart = () => {
    if (inputText.trim().length < 100) return;
    setShowInput(false);
    startConvert(inputText);
  };
  const handleReset = () => { reset(); setShowInput(true); setShowSource(false); setInputText(""); };

  const handleShotClick = useCallback((shotId: string) => {
    const newId = selectedShotId === shotId ? null : shotId;
    setSelectedShotId(newId);
    if (newId) setShowSource(true);
  }, [selectedShotId, setSelectedShotId]);

  const handleHistorySelect = useCallback(async (historyTaskId: string) => {
    setShowInput(false); setSelectedShotId(null); setShowSource(false);
    await loadFromHistory(historyTaskId);
  }, [loadFromHistory, setSelectedShotId]);

  useEffect(() => { if (status === "done") setHistoryKey((k) => k + 1); }, [status]);

  const handleShotEdit = useCallback(async (sceneId: string, shotId: string, field: string, value: string) => {
    if (!taskId) return;
    let updatedScreenplay: any = null;
    updateScreenplay((prev: any) => {
      const newScenes = prev.scenes.map((scene: any) => {
        if (scene.scene_id !== sceneId) return scene;
        return {
          ...scene,
          shots: scene.shots.map((shot: any) => {
            if (shot.shot_id !== shotId) return shot;
            const updated = { ...shot };
            switch (field) {
              case "visual_prompt": updated.visual_prompt = value; break;
              case "focus_subject": updated.focus_subject = value; break;
              case "duration": updated.duration = value; break;
              case "sfx": updated.sfx = value; break;
              case "dialogue_line": if (updated.dialogue) updated.dialogue = { ...updated.dialogue, line: value }; break;
              case "dialogue_emotion": if (updated.dialogue) updated.dialogue = { ...updated.dialogue, emotion: value }; break;
            }
            return updated;
          }),
        };
      });
      updatedScreenplay = { ...prev, scenes: newScenes };
      return updatedScreenplay;
    });
    if (updatedScreenplay) saveScreenplay(taskId, updatedScreenplay).catch(() => {});
  }, [taskId, updateScreenplay]);

  const highlightedParagraphs: number[] = [];
  if (screenplay && selectedShotId) {
    for (const scene of screenplay.scenes) {
      for (const shot of scene.shots) {
        if (shot.shot_id === selectedShotId) highlightedParagraphs.push(...shot.source_paragraphs);
      }
    }
  }

  const selectedShot = screenplay && selectedShotId
    ? screenplay.scenes.flatMap((s: any) => s.shots).find((sh: any) => sh.shot_id === selectedShotId)
    : null;

  if (showInput) {
    return (
      <div className="h-screen flex flex-col bg-zinc-950 text-zinc-100">
        <Header status={status} progressMessage={progressMessage} screenplay={!!screenplay}
          showExport={showExport} setShowExport={setShowExport} taskId={taskId}
          onReset={handleReset} hasScreenplay={!!screenplay} />
        <div className="flex-1 flex">
          <div className="w-56 border-r border-zinc-800 shrink-0">
            <HistoryPanel currentTaskId={taskId} onSelect={handleHistorySelect} refreshKey={historyKey} />
          </div>
          <div className="flex-1 flex items-center justify-center p-8">
            <InputView text={inputText} onChange={setInputText} onSubmit={handleStart}
              loading={status === "pending" || status === "running"} progress={progress} progressMessage={progressMessage} />
          </div>
        </div>
      </div>
    );
  }

  if (!screenplay) {
    return (
      <div className="h-screen flex flex-col bg-zinc-950 text-zinc-100">
        <Header status={status} progressMessage={progressMessage} screenplay={false}
          showExport={false} setShowExport={() => {}} taskId={null}
          onReset={handleReset} hasScreenplay={false} />
        <LoadingView progress={progress} message={progressMessage} status={status} />
      </div>
    );
  }

  const scene = screenplay.scenes[selectedSceneIndex];

  return (
    <div className="h-screen flex flex-col bg-zinc-950 text-zinc-100">
      <Header status={status} progressMessage={progressMessage} screenplay={true}
        showExport={showExport} setShowExport={setShowExport} taskId={taskId}
        onReset={handleReset} hasScreenplay={true} />

      <div className="flex-1 overflow-hidden">
        <Group direction="horizontal">
          {/* Panel A: History + Scene Nav */}
          <Panel defaultSize={18} minSize={12} maxSize={30}>
            <div className="h-full flex flex-col border-r border-zinc-800">
              <div className="h-2/5">
                <HistoryPanel currentTaskId={taskId} onSelect={handleHistorySelect} refreshKey={historyKey} />
              </div>
              <div className="flex-1 overflow-hidden">
                <Group direction="vertical">
                  <Panel defaultSize={70} minSize={30}>
                    <Sidebar
                      scenes={screenplay.scenes}
                      characters={screenplay.characters}
                      meta={screenplay.meta}
                      totalCharacters={screenplay.characters.length}
                      selectedSceneIndex={selectedSceneIndex}
                      onSelectScene={setSelectedSceneIndex}
                    />
                  </Panel>
                  <Separator className="h-0.5 hover:h-1 bg-zinc-800 hover:bg-zinc-600 transition-all" />
                  <Panel defaultSize={30} minSize={15}>
                    <div className="p-3">
                      <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Shot Detail</h3>
                      {selectedShot ? (
                        <div className="space-y-2 text-xs text-zinc-400">
                          <div><span className="text-zinc-600">Type</span> <span className="text-zinc-200 ml-1">{selectedShot.shot_type}</span></div>
                          <div><span className="text-zinc-600">Movement</span> <span className="text-zinc-200 ml-1">{selectedShot.camera_movement}</span></div>
                          <div><span className="text-zinc-600">Duration</span> <span className="text-zinc-200 ml-1">{selectedShot.duration}</span></div>
                          <div><span className="text-zinc-600">Focus</span> <span className="text-zinc-200 ml-1">{selectedShot.focus_subject}</span></div>
                          {selectedShot.sfx && <div><span className="text-zinc-600">SFX</span> <span className="text-amber-400/70 ml-1">{selectedShot.sfx}</span></div>}
                          <div className="pt-2 border-t border-zinc-800">
                            <p className="text-zinc-600 mb-1">Visual Prompt</p>
                            <p className="text-zinc-300 leading-relaxed">{selectedShot.visual_prompt}</p>
                          </div>
                        </div>
                      ) : (
                        <p className="text-xs text-zinc-600">Click a shot to see details</p>
                      )}
                    </div>
                  </Panel>
                </Group>
              </div>
            </div>
          </Panel>

          <Separator className="w-1 hover:w-1.5 bg-transparent hover:bg-emerald-600/50 transition-all cursor-col-resize" />

          {/* Panel B: Main screenplay content */}
          <Panel defaultSize={62} minSize={35}>
            <div className="h-full flex flex-col">
              <div className="flex-1 overflow-y-auto p-6">
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
                            onRegenerate={(feedback) => handleRegenerateShot(scene.scene_id, shot.shot_id, feedback)}
                            onEdit={(field, value) => handleShotEdit(scene.scene_id, shot.shot_id, field, value)}
                          />
                        ))}
                      </div>
                    </>
                  )}
                </div>
              </div>

              {/* Panel D: Source text (bottom) */}
              {showSource && (
                <SourcePanel paragraphs={paragraphs} highlightedParagraphs={highlightedParagraphs}
                  onClose={() => setShowSource(false)} />
              )}
            </div>
          </Panel>
        </Group>
      </div>
    </div>
  );
}

// ============================================================
// Sub-components
// ============================================================

function Header({ status, progressMessage, hasScreenplay, showExport, setShowExport, taskId, onReset }: {
  status: string; progressMessage: string; screenplay: boolean;
  showExport: boolean; setShowExport: (b: boolean) => void; taskId: string | null;
  onReset: () => void; hasScreenplay: boolean;
}) {
  return (
    <header className="h-11 flex items-center justify-between px-4 border-b border-zinc-800 shrink-0 bg-zinc-950">
      <h1 className="text-xs font-semibold tracking-tight text-zinc-300">
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
                <div className="absolute right-0 top-8 w-40 bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl z-50 py-1">
                  <a href={getYamlUrl(taskId)} onClick={() => setShowExport(false)}
                    className="block px-3 py-1.5 text-[10px] text-zinc-300 hover:bg-zinc-700 transition-colors">
                    YAML (AI Pipeline)
                  </a>
                  <a href={getWordUrl(taskId)} onClick={() => setShowExport(false)}
                    className="block px-3 py-1.5 text-[10px] text-zinc-300 hover:bg-zinc-700 transition-colors">
                    Word (Edit)
                  </a>
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

function LoadingView({ progress, message, status }: { progress: number; message: string; status: string; }) {
  if (status === "error") {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center"><p className="text-red-400 mb-2">Conversion Failed</p>
          <p className="text-zinc-500 text-sm">{message}</p></div>
      </div>
    );
  }
  return (
    <div className="flex-1 flex items-center justify-center">
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
