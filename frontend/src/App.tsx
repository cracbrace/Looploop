import { useState, useCallback } from "react";
import { useScreenplay } from "./hooks/useScreenplay";
import { getYamlUrl, getWordUrl } from "./api/client";
import type { Shot, Scene } from "./types/screenplay";

function App() {
  const {
    screenplay,
    status,
    progressMessage,
    progress,
    taskId,
    selectedSceneIndex,
    selectedShotId,
    originalText,
    paragraphs,
    setSelectedSceneIndex,
    setSelectedShotId,
    startConvert,
    handleRegenerateShot,
    reset,
  } = useScreenplay();

  const [inputText, setInputText] = useState("");
  const [showInput, setShowInput] = useState(true);
  const [showSource, setShowSource] = useState(false);
  const [showExport, setShowExport] = useState(false);

  const handleStart = () => {
    if (inputText.trim().length < 100) return;
    setShowInput(false);
    startConvert(inputText);
  };

  const handleReset = () => {
    reset();
    setShowInput(true);
    setShowSource(false);
    setInputText("");
  };

  const onShotClick = useCallback(
    (shotId: string) => {
      setSelectedShotId(selectedShotId === shotId ? null : shotId);
      if (shotId) setShowSource(true);
    },
    [selectedShotId, setSelectedShotId]
  );

  // 获取当前选中 shot 的 source_paragraphs
  const highlightedParagraphs: number[] = [];
  if (screenplay && selectedShotId) {
    for (const scene of screenplay.scenes) {
      for (const shot of scene.shots) {
        if (shot.shot_id === selectedShotId) {
          highlightedParagraphs.push(...shot.source_paragraphs);
        }
      }
    }
  }

  return (
    <div className="h-screen flex flex-col bg-zinc-950 text-zinc-100">
      {/* 顶部标题栏 */}
      <header className="h-12 flex items-center justify-between px-4 border-b border-zinc-800 shrink-0">
        <h1 className="text-sm font-semibold tracking-tight">
          Looploop <span className="text-zinc-500 font-normal">噜噜</span>
        </h1>
        <div className="flex items-center gap-2">
          {status === "running" && (
            <span className="text-xs text-zinc-400">{progressMessage}</span>
          )}
          {screenplay && (
            <>
              {showSource && (
                <button
                  onClick={() => setShowSource(false)}
                  className="text-xs px-2 py-1 text-zinc-400 hover:text-zinc-200 transition-colors"
                >
                  Hide Source
                </button>
              )}
              <div className="relative">
                <button
                  onClick={() => setShowExport(!showExport)}
                  className="text-xs px-3 py-1 bg-zinc-800 hover:bg-zinc-700 rounded border border-zinc-700 transition-colors"
                >
                  Export
                </button>
                {showExport && taskId && (
                  <div className="absolute right-0 top-8 w-44 bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl z-50 py-1">
                    <a
                      href={getYamlUrl(taskId)}
                      className="block px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700 transition-colors"
                      onClick={() => setShowExport(false)}
                    >
                      Export YAML (AI Pipeline)
                    </a>
                    <a
                      href={getWordUrl(taskId)}
                      className="block px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700 transition-colors"
                      onClick={() => setShowExport(false)}
                    >
                      Export Word (Edit)
                    </a>
                  </div>
                )}
              </div>
              <button
                onClick={handleReset}
                className="text-xs px-3 py-1 bg-zinc-800 hover:bg-zinc-700 rounded border border-zinc-700 transition-colors"
              >
                New
              </button>
            </>
          )}
        </div>
      </header>

      {/* 主体 */}
      {showInput ? (
        <InputView
          text={inputText}
          onChange={setInputText}
          onSubmit={handleStart}
          loading={status === "pending" || status === "running"}
          progress={progress}
          progressMessage={progressMessage}
        />
      ) : screenplay ? (
        <div className="flex-1 flex flex-col overflow-hidden">
          <ResultView
            screenplay={screenplay}
            selectedSceneIndex={selectedSceneIndex}
            selectedShotId={selectedShotId}
            onSelectScene={setSelectedSceneIndex}
            onShotClick={onShotClick}
            onRegenerateShot={handleRegenerateShot}
          />
          {showSource && (
            <SourcePanel
              paragraphs={paragraphs}
              highlightedParagraphs={highlightedParagraphs}
              onClose={() => setShowSource(false)}
            />
          )}
        </div>
      ) : (
        <LoadingView
          progress={progress}
          message={progressMessage}
          status={status}
        />
      )}
    </div>
  );
}

function InputView({
  text,
  onChange,
  onSubmit,
  loading,
  progress,
  progressMessage,
}: {
  text: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  loading: boolean;
  progress: number;
  progressMessage: string;
}) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8">
      <div className="w-full max-w-2xl">
        <h2 className="text-xl font-semibold mb-2">Start</h2>
        <p className="text-zinc-400 text-sm mb-4">
          Paste 3+ chapters. AI generates a structured screenplay automatically.
        </p>

        <textarea
          value={text}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Paste your novel text here..."
          className="w-full h-64 bg-zinc-900 border border-zinc-700 rounded-lg p-4 text-sm
                     text-zinc-200 placeholder-zinc-600 resize-none focus:outline-none
                     focus:border-zinc-500 transition-colors"
          disabled={loading}
        />

        <div className="mt-4 flex items-center justify-between">
          <span className="text-xs text-zinc-500">
            {text.length} chars (min 100)
          </span>
          <button
            onClick={onSubmit}
            disabled={text.trim().length < 100 || loading}
            className="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40
                       disabled:cursor-not-allowed rounded-lg text-sm font-medium transition-colors"
          >
            {loading ? `Converting ${Math.round(progress * 100)}%` : "Convert"}
          </button>
        </div>

        {loading && (
          <>
            <div className="mt-4 w-full bg-zinc-800 rounded-full h-1.5 overflow-hidden">
              <div
                className="h-full bg-emerald-500 transition-all duration-300 rounded-full"
                style={{ width: `${Math.round(progress * 100)}%` }}
              />
            </div>
            <p className="mt-2 text-xs text-zinc-500 text-center">
              {progressMessage}
            </p>
          </>
        )}
      </div>
    </div>
  );
}

function LoadingView({
  progress,
  message,
  status,
}: {
  progress: number;
  message: string;
  status: string;
}) {
  if (status === "error") {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-400 mb-2">Conversion Failed</p>
          <p className="text-zinc-500 text-sm">{message}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-center">
        <div className="w-8 h-8 border-2 border-zinc-600 border-t-emerald-400 rounded-full animate-spin mx-auto mb-4" />
        <p className="text-zinc-400 text-sm">{message}</p>
        <div className="mt-4 w-48 bg-zinc-800 rounded-full h-1.5 overflow-hidden mx-auto">
          <div
            className="h-full bg-emerald-500 transition-all duration-300 rounded-full"
            style={{ width: `${Math.round(progress * 100)}%` }}
          />
        </div>
      </div>
    </div>
  );
}

function ResultView({
  screenplay,
  selectedSceneIndex,
  selectedShotId,
  onSelectScene,
  onShotClick,
  onRegenerateShot,
}: {
  screenplay: any;
  selectedSceneIndex: number;
  selectedShotId: string | null;
  onSelectScene: (i: number) => void;
  onShotClick: (id: string) => void;
  onRegenerateShot: (sceneId: string, shotId: string, feedback?: string) => void;
}) {
  const scene = screenplay.scenes[selectedSceneIndex];
  if (!scene) return null;

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* Left sidebar */}
      <aside className="w-60 border-r border-zinc-800 overflow-y-auto p-3 shrink-0">
        <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3">
          Scenes
        </h3>
        {screenplay.scenes.map((s: any, i: number) => (
          <button
            key={s.scene_id}
            onClick={() => onSelectScene(i)}
            className={`w-full text-left px-3 py-2 rounded text-sm mb-1 transition-colors
              ${i === selectedSceneIndex
                ? "bg-zinc-800 text-zinc-100"
                : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"
              }`}
          >
            {s.scene_id} &middot; {s.location}
          </button>
        ))}

        <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2 mt-6">
          Characters
        </h3>
        {screenplay.characters.map((c: any) => (
          <div key={c.character_id} className="text-xs text-zinc-500 px-3 py-1">
            {c.canonical_name}
          </div>
        ))}

        <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2 mt-6">
          Stats
        </h3>
        <div className="text-xs text-zinc-500 space-y-1 px-3">
          <p>{screenplay.meta.total_scenes} scenes</p>
          <p>{screenplay.meta.total_shots} shots</p>
          <p>{screenplay.characters.length} characters</p>
          <p>{screenplay.meta.total_duration_estimate}</p>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto p-4">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-lg font-semibold mb-1">
            {scene.scene_id} &middot; {scene.location}
          </h2>
          <p className="text-xs text-zinc-500 mb-4">
            {scene.time_of_day} &middot; {scene.atmosphere} &middot;{" "}
            {scene.duration_estimate}
          </p>

          <div className="space-y-3">
            {scene.shots.map((shot: any) => (
              <ShotCard
                key={shot.shot_id}
                shot={shot}
                isSelected={shot.shot_id === selectedShotId}
                onClick={() => onShotClick(shot.shot_id)}
                onRegenerate={(feedback) =>
                  onRegenerateShot(scene.scene_id, shot.shot_id, feedback)
                }
              />
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}

function ShotCard({
  shot,
  isSelected,
  onClick,
  onRegenerate,
}: {
  shot: any;
  isSelected: boolean;
  onClick: () => void;
  onRegenerate: (feedback?: string) => void;
}) {
  const [showRegen, setShowRegen] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [loading, setLoading] = useState(false);

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

  const borderColor = shotTypeColor[shot.shot_type] || "border-l-zinc-600";

  const handleRegenClick = async () => {
    setLoading(true);
    await onRegenerate(feedback || undefined);
    setLoading(false);
    setShowRegen(false);
    setFeedback("");
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
        <span className="text-xs text-zinc-500 ml-auto">{shot.duration}</span>
        <button
          onClick={(e) => {
            e.stopPropagation();
            setShowRegen(!showRegen);
          }}
          className="text-xs px-1.5 py-0.5 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-700 rounded transition-colors"
          title="Regenerate this shot"
        >
          &#x21bb;
        </button>
      </div>
      <p className="text-xs text-zinc-400 mb-1">Focus: {shot.focus_subject}</p>
      {shot.sfx && (
        <p className="text-xs text-amber-500/70 mb-1">SFX: {shot.sfx}</p>
      )}
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

      {/* Regenerate form */}
      {showRegen && (
        <div
          className="mt-2 pt-2 border-t border-zinc-700"
          onClick={(e) => e.stopPropagation()}
        >
          <input
            type="text"
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="What to change? (e.g. handheld style)"
            className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs
                       text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500"
          />
          <div className="flex gap-2 mt-1">
            <button
              onClick={handleRegenClick}
              disabled={loading}
              className="text-xs px-2 py-0.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40
                         rounded transition-colors"
            >
              {loading ? "..." : "Regenerate"}
            </button>
            <button
              onClick={() => setShowRegen(false)}
              className="text-xs px-2 py-0.5 text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function SourcePanel({
  paragraphs,
  highlightedParagraphs,
  onClose,
}: {
  paragraphs: string[];
  highlightedParagraphs: number[];
  onClose: () => void;
}) {
  const highlightSet = new Set(highlightedParagraphs);

  return (
    <div className="h-48 border-t border-zinc-800 bg-zinc-900/80 backdrop-blur shrink-0 overflow-hidden flex flex-col">
      <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800 shrink-0">
        <h3 className="text-xs font-semibold text-zinc-400">
          Source Text
          {highlightedParagraphs.length > 0 && (
            <span className="ml-2 text-amber-400">
              Paragraphs: {highlightedParagraphs.join(", ")}
            </span>
          )}
        </h3>
        <button
          onClick={onClose}
          className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          Close
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {paragraphs.length === 0 ? (
          <p className="text-xs text-zinc-600">Original text not available</p>
        ) : (
          paragraphs.map((p, i) => (
            <p
              key={i}
              className={`text-xs leading-relaxed mb-2 px-2 py-1 rounded transition-colors
                ${highlightSet.has(i)
                  ? "bg-amber-500/10 text-amber-200 border-l-2 border-amber-500 pl-3"
                  : "text-zinc-500"
                }`}
            >
              <span className="text-zinc-600 mr-2 font-mono">{i}</span>
              {p.slice(0, 200)}
              {p.length > 200 ? "..." : ""}
            </p>
          ))
        )}
      </div>
    </div>
  );
}

export default App;
