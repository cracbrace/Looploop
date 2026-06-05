import { useState, useCallback } from "react";
import { useScreenplay } from "./hooks/useScreenplay";
import { ShotCard } from "./components/ShotCard";
import { Sidebar } from "./components/Sidebar";
import { SourcePanel } from "./components/SourcePanel";
import { getYamlUrl, getWordUrl } from "./api/client";

function App() {
  const {
    screenplay,
    status,
    progressMessage,
    progress,
    selectedSceneIndex,
    setSelectedSceneIndex,
    originalText,
    paragraphs,
    startConvert,
    handleRegenerateShot,
    taskId,
    reset,
  } = useScreenplay();

  const [inputText, setInputText] = useState("");
  const [showExport, setShowExport] = useState(false);
  const [showInput, setShowInput] = useState(true);
  const [selectedShotId, setSelectedShotId] = useState<string | null>(null);
  const [showSource, setShowSource] = useState(false);

  const handleShotClick = useCallback(
    (shotId: string) => {
      const newId = selectedShotId === shotId ? null : shotId;
      setSelectedShotId(newId);
      if (newId) setShowSource(true);
    },
    [selectedShotId]
  );

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

  const handleStart = () => {
    if (inputText.trim().length < 100) return;
    setShowInput(false);
    startConvert(inputText);
  };

  const handleReset = () => {
    reset();
    setShowInput(true);
    setInputText("");
  };

  return (
    <div className="h-screen flex flex-col bg-zinc-950 text-zinc-100">
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
              <div className="relative">
                <button
                  onClick={() => setShowExport(!showExport)}
                  className="text-xs px-3 py-1 bg-zinc-800 hover:bg-zinc-700 rounded border border-zinc-700 transition-colors"
                >
                  Export
                </button>
                {showExport && taskId && (
                  <div className="absolute right-0 top-8 w-44 bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl z-50 py-1">
                    <a href={getYamlUrl(taskId)}
                       className="block px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700 transition-colors"
                       onClick={() => setShowExport(false)}>
                      Export YAML (AI Pipeline)
                    </a>
                    <a href={getWordUrl(taskId)}
                       className="block px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700 transition-colors"
                       onClick={() => setShowExport(false)}>
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
            onShotClick={handleShotClick}
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
  onRegenerateShot: (sceneId: string, shotId: string, feedback?: string) => Promise<void>;
}) {
  if (!screenplay.scenes || screenplay.scenes.length === 0) {
    return <div className="flex-1 p-8 text-zinc-500">No scenes in screenplay data</div>;
  }
  const scene = screenplay.scenes[selectedSceneIndex];
  if (!scene) return <div className="flex-1 p-8 text-zinc-500">No scene data</div>;

  return (
    <div className="flex-1 flex overflow-hidden">
      <Sidebar
        scenes={screenplay.scenes}
        characters={screenplay.characters}
        meta={screenplay.meta}
        totalCharacters={screenplay.characters.length}
        selectedSceneIndex={selectedSceneIndex}
        onSelectScene={onSelectScene}
      />

      {/* Right: current scene shots as plain divs */}
      <main className="flex-1 overflow-y-auto p-4">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-lg font-semibold mb-1">
            {scene.scene_id} &middot; {scene.location}
          </h2>
          <p className="text-xs text-zinc-500 mb-4">
            {scene.time_of_day} &middot; {scene.atmosphere}
            {scene.era && <span> &middot; {scene.era}</span>}
            {scene.weather && <span> &middot; {scene.weather}</span>}
            <span className="ml-2 text-zinc-600">| {scene.duration_estimate}</span>
          </p>

          <div className="space-y-3">
            {scene.shots.map((shot: any) => (
              <ShotCard
                key={shot.shot_id}
                shot={shot}
                isSelected={shot.shot_id === selectedShotId}
                onClick={() => onShotClick(shot.shot_id)}
                onRegenerate={(feedback) => onRegenerateShot(scene.scene_id, shot.shot_id, feedback)}
              />
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
