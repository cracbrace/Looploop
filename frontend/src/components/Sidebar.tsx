interface SidebarProps {
  scenes: Array<{
    scene_id: string;
    material_id?: string;
    location: string;
  }>;
  characters: Array<{
    character_id: string;
    material_id?: string;
    canonical_name: string;
  }>;
  meta: {
    total_scenes: number;
    total_shots: number;
    total_duration_estimate: string;
  };
  totalCharacters: number;
  selectedSceneIndex: number;
  onSelectScene: (i: number) => void;
}

export function Sidebar({
  scenes,
  characters,
  meta,
  totalCharacters,
  selectedSceneIndex,
  onSelectScene,
}: SidebarProps) {
  return (
    <aside className="overflow-y-auto p-3">
      <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3">
        Scenes
      </h3>
      {scenes.map((s, i) => (
        <button
          key={s.scene_id}
          onClick={() => onSelectScene(i)}
          className={`w-full text-left px-3 py-2 rounded text-sm mb-1 transition-colors
            ${i === selectedSceneIndex
              ? "bg-zinc-800 text-zinc-100"
              : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"
            }`}
        >
          {(s as any).material_id || s.scene_id} &middot; {s.location}
        </button>
      ))}

      <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2 mt-6">
        Characters
      </h3>
      {characters.map((c) => (
        <div key={c.character_id} className="text-xs text-zinc-500 px-3 py-1">
          {(c as any).material_id || c.character_id} {c.canonical_name}
        </div>
      ))}

      <div className="mt-6 pt-4 border-t border-zinc-800">
        <div className="text-xs text-zinc-500 space-y-1">
          <p>{meta.total_scenes} scenes</p>
          <p>{meta.total_shots} shots</p>
          <p>{totalCharacters} characters</p>
          <p>{meta.total_duration_estimate}</p>
        </div>
      </div>
    </aside>
  );
}
