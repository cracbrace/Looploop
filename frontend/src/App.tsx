import { useState } from "react";
import { useScreenplay } from "./hooks/useScreenplay";

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
      {/* 顶部标题栏 */}
      <header className="h-12 flex items-center justify-between px-4 border-b border-zinc-800 shrink-0">
        <h1 className="text-sm font-semibold tracking-tight">
          Looploop <span className="text-zinc-500 font-normal">噜噜</span>
        </h1>
        <div className="flex items-center gap-3">
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
        <ResultView
          screenplay={screenplay}
          selectedSceneIndex={selectedSceneIndex}
          onSelectScene={setSelectedSceneIndex}
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
        <h2 className="text-xl font-semibold mb-2">开始转换</h2>
        <p className="text-zinc-400 text-sm mb-4">
          粘贴 3 章以上的小说文本，AI 将自动生成结构化剧本
        </p>

        <textarea
          value={text}
          onChange={(e) => onChange(e.target.value)}
          placeholder="在此粘贴小说正文..."
          className="w-full h-64 bg-zinc-900 border border-zinc-700 rounded-lg p-4 text-sm
                     text-zinc-200 placeholder-zinc-600 resize-none focus:outline-none
                     focus:border-zinc-500 transition-colors"
          disabled={loading}
        />

        <div className="mt-4 flex items-center justify-between">
          <span className="text-xs text-zinc-500">
            {text.length} 字符（最少 100 字符）
          </span>
          <button
            onClick={onSubmit}
            disabled={text.trim().length < 100 || loading}
            className="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40
                       disabled:cursor-not-allowed rounded-lg text-sm font-medium
                       transition-colors cursor-pointer"
          >
            {loading ? `转换中 ${Math.round(progress * 100)}%` : "开始转换"}
          </button>
        </div>

        {loading && (
          <div className="mt-4 w-full bg-zinc-800 rounded-full h-1.5 overflow-hidden">
            <div
              className="h-full bg-emerald-500 transition-all duration-300 rounded-full"
              style={{ width: `${Math.round(progress * 100)}%` }}
            />
          </div>
        )}

        {loading && progressMessage && (
          <p className="mt-2 text-xs text-zinc-500 text-center">
            {progressMessage}
          </p>
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
          <p className="text-red-400 mb-2">转换失败</p>
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
  onSelectScene,
}: {
  screenplay: any;
  selectedSceneIndex: number;
  onSelectScene: (i: number) => void;
}) {
  const scene = screenplay.scenes[selectedSceneIndex];

  if (!scene) return null;

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* 左侧——场景导航 */}
      <aside className="w-60 border-r border-zinc-800 overflow-y-auto p-3 shrink-0">
        <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3">
          Scenes
        </h3>
        {screenplay.scenes.map((s: any, i: number) => (
          <button
            key={s.scene_id}
            onClick={() => onSelectScene(i)}
            className={`w-full text-left px-3 py-2 rounded text-sm mb-1 transition-colors cursor-pointer
              ${i === selectedSceneIndex
                ? "bg-zinc-800 text-zinc-100"
                : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"
              }`}
          >
            {s.scene_id} · {s.location}
          </button>
        ))}

        <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2 mt-6">
          Characters
        </h3>
        {screenplay.characters.map((c: any) => (
          <div
            key={c.character_id}
            className="text-xs text-zinc-500 px-3 py-1"
          >
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

      {/* 右侧——剧本内容 */}
      <main className="flex-1 overflow-y-auto p-4">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-lg font-semibold mb-1">
            {scene.scene_id} · {scene.location}
          </h2>
          <p className="text-xs text-zinc-500 mb-4">
            {scene.time_of_day} · {scene.atmosphere} · {scene.duration_estimate}
          </p>

          <div className="space-y-3">
            {scene.shots.map((shot: any) => (
              <div
                key={shot.shot_id}
                className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 hover:border-zinc-700 transition-colors"
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-mono text-zinc-500">
                    {shot.shot_id}
                  </span>
                  <span className="text-xs px-1.5 py-0.5 bg-zinc-800 rounded text-zinc-300">
                    {shot.shot_type}
                  </span>
                  <span className="text-xs px-1.5 py-0.5 bg-zinc-800 rounded text-zinc-400">
                    {shot.camera_movement}
                  </span>
                  <span className="text-xs text-zinc-500 ml-auto">
                    {shot.duration}
                  </span>
                </div>
                <p className="text-xs text-zinc-400 mb-1">
                  Focus: {shot.focus_subject}
                </p>
                {shot.dialogue && (
                  <p className="text-sm text-zinc-200 mt-2 bg-zinc-800/50 rounded px-2 py-1">
                    <span className="text-emerald-400 font-medium">
                      {shot.dialogue.character}
                    </span>
                    <span className="text-zinc-500 text-xs ml-1">
                      ({shot.dialogue.emotion})
                    </span>
                    ：{shot.dialogue.line}
                  </p>
                )}
                <p className="text-xs text-zinc-600 mt-1 truncate">
                  prompt: {shot.visual_prompt}
                </p>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
