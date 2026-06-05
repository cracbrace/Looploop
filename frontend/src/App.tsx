import { useState } from "react";

function App() {
  const [health, setHealth] = useState<string>("checking...");

  const checkHealth = async () => {
    try {
      const res = await fetch("/api/health");
      const data = await res.json();
      setHealth(JSON.stringify(data, null, 2));
    } catch {
      setHealth("Backend not connected");
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col items-center justify-center">
      <h1 className="text-4xl font-bold mb-2 tracking-tight">
        Looploop{" "}
        <span className="text-zinc-500 font-normal">噜噜</span>
      </h1>
      <p className="text-zinc-400 mb-8 text-lg">
        AI 短剧全自动管线 · 结构化导演指令生成器
      </p>

      <button
        onClick={checkHealth}
        className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm
                   transition-colors cursor-pointer border border-zinc-700"
      >
        Check Backend
      </button>

      <pre className="mt-4 text-xs text-zinc-500 font-mono">{health}</pre>
    </div>
  );
}

export default App;
