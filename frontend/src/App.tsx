import { useState, useCallback } from "react";
import { useScreenplay } from "./hooks/useScreenplay";
import { ShotCard } from "./components/ShotCard";

function App() {
  const {
    screenplay,
    status,
    progressMessage,
    progress,
    selectedSceneIndex,
    setSelectedSceneIndex,
    startConvert,
    reset,
  } = useScreenplay();

  const [inputText, setInputText] = useState("");
  const [showInput, setShowInput] = useState(true);
  const [selectedShotId, setSelectedShotId] = useState<string | null>(null);

  const handleShotClick = useCallback(
    (shotId: string) => {
      setSelectedShotId(selectedShotId === shotId ? null : shotId);
    },
    [selectedShotId]
  );

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
            <button
              onClick={handleReset}
              className="text-xs px-3 py-1 bg-zinc-800 hover:bg-zinc-700 rounded border border-zinc-700 transition-colors"
            >
              New
            </button>
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
        <ResultView
          screenplay={screenplay}
          selectedSceneIndex={selectedSceneIndex}
          selectedShotId={selectedShotId}
          onSelectScene={setSelectedSceneIndex}
          onShotClick={handleShotClick}
        />
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
}: {
  screenplay: any;
  selectedSceneIndex: number;
  selectedShotId: string | null;
  onSelectScene: (i: number) => void;
  onShotClick: (id: string) => void;
}) {
  const scene = screenplay.scenes[selectedSceneIndex];
  if (!scene) return <div className="flex-1 p-8 text-zinc-500">No scene data</div>;

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* Left sidebar: scene nav + characters + stats */}
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

        <div className="mt-6 pt-4 border-t border-zinc-800">
          <div className="text-xs text-zinc-500 space-y-1">
            <p>{screenplay.meta.total_scenes} scenes</p>
            <p>{screenplay.meta.total_shots} shots</p>
            <p>{screenplay.characters.length} characters</p>
            <p>{screenplay.meta.total_duration_estimate}</p>
          </div>
        </div>
      </aside>

      {/* Right: current scene shots as plain divs */}
      <main className="flex-1 overflow-y-auto p-4">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-lg font-semibold mb-1">
            {scene.scene_id} &middot; {scene.location}
          </h2>
          <p className="text-xs text-zinc-500 mb-4">
            {scene.time_of_day} &middot; {scene.atmosphere}
          </p>

          <div className="space-y-3">
            {scene.shots.map((shot: any) => (
              <ShotCard
                key={shot.shot_id}
                shot={shot}
                isSelected={shot.shot_id === selectedShotId}
                onClick={() => onShotClick(shot.shot_id)}
              />
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
