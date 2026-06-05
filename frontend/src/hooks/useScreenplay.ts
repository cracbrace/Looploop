/**
 * 剧本数据状态管理 Hook
 */

import { useState, useCallback, useRef } from "react";
import type {
  Screenplay,
  PipelineStatus,
  PipelineStage,
} from "../types/screenplay";
import {
  convertNovel,
  streamProgress,
  getScreenplay,
  regenerateShot,
} from "../api/client";

export function useScreenplay() {
  const [screenplay, setScreenplay] = useState<Screenplay | null>(null);
  const [status, setStatus] = useState<PipelineStatus>("idle");
  const [progressMessage, setProgressMessage] = useState("");
  const [progress, setProgress] = useState(0);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [selectedSceneIndex, setSelectedSceneIndex] = useState(0);
  const [selectedShotId, setSelectedShotId] = useState<string | null>(null);
  const [selectedCharacterId, setSelectedCharacterId] = useState<
    string | null
  >(null);
  const [originalText, setOriginalText] = useState("");
  const [paragraphs, setParagraphs] = useState<string[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  // Undo/redo stacks
  const undoStackRef = useRef<any[]>([]);
  const redoStackRef = useRef<any[]>([]);

  const startConvert = useCallback(async (text: string, onLog?: (msg: string) => void) => {
    setStatus("pending");
    setProgressMessage("正在提交...");
    setProgress(0);
    setScreenplay(null);
    setOriginalText(text);
    setParagraphs(text.split("\n\n"));

    try {
      const id = await convertNovel(text);
      setTaskId(id);

      setStatus("running");

      abortRef.current = streamProgress(
        id,
        (stage: PipelineStage) => {
          setStatus(stage.stage as PipelineStatus);
          setProgressMessage(stage.message);
          setProgress(stage.progress);
          if (stage.logs && onLog) {
            stage.logs.forEach((msg) => onLog(msg));
          }
        },
        async () => {
          // Done — fetch the result
          try {
            const sp = await getScreenplay(id);
            setScreenplay(sp);
            setStatus("done");
            setSelectedSceneIndex(0);
          } catch {
            setStatus("error");
            setProgressMessage("获取剧本失败");
          }
        },
        (err: string) => {
          setStatus("error");
          setProgressMessage(err);
        }
      );
    } catch (err) {
      setStatus("error");
      setProgressMessage(err instanceof Error ? err.message : "转换失败");
    }
  }, []);

  const cancelConvert = useCallback(() => {
    abortRef.current?.abort();
    setStatus("idle");
  }, []);

  const loadFromHistory = useCallback(async (historyTaskId: string) => {
    setStatus("pending");
    setProgressMessage("Loading from history...");
    try {
      const sp = await getScreenplay(historyTaskId);
      if (sp && sp.meta) {
        setScreenplay(sp);
        setTaskId(historyTaskId);
        setStatus("done");
        setProgress(1.0);
        setSelectedSceneIndex(0);
      } else {
        setStatus("error");
        setProgressMessage("Screenplay data is empty or invalid");
      }
    } catch (err) {
      setStatus("error");
      setProgressMessage(err instanceof Error ? err.message : "Failed to load");
    }
  }, []);

  const updateScreenplay = useCallback(
    (updater: (prev: any) => any, pushUndo = true) => {
      setScreenplay((prev: any) => {
        if (!prev) return prev;
        if (pushUndo) {
          undoStackRef.current.push(JSON.parse(JSON.stringify(prev)));
          redoStackRef.current = [];
          if (undoStackRef.current.length > 50) undoStackRef.current.shift();
        }
        return updater(prev);
      });
    },
    []
  );

  const undo = useCallback(() => {
    const prev = undoStackRef.current.pop();
    if (!prev) return;
    setScreenplay((current: any) => {
      if (current) redoStackRef.current.push(JSON.parse(JSON.stringify(current)));
      return prev;
    });
  }, []);

  const redo = useCallback(() => {
    const next = redoStackRef.current.pop();
    if (!next) return;
    setScreenplay((current: any) => {
      if (current) undoStackRef.current.push(JSON.parse(JSON.stringify(current)));
      return next;
    });
  }, []);

  const canUndo = () => undoStackRef.current.length > 0;
  const canRedo = () => redoStackRef.current.length > 0;

  const handleRegenerateShot = useCallback(
    async (
      sceneId: string,
      shotId: string,
      userFeedback?: string,
    ) => {
      if (!screenplay) return;
      try {
        const newShot = await regenerateShot(
          sceneId,
          shotId,
          screenplay,
          userFeedback,
        );
        // 局部更新
        setScreenplay((prev) => {
          if (!prev) return prev;
          const newScenes = prev.scenes.map((scene) => {
            if (scene.scene_id !== sceneId) return scene;
            return {
              ...scene,
              shots: scene.shots.map((shot) =>
                shot.shot_id === shotId ? newShot : shot
              ),
            };
          });
          return { ...prev, scenes: newScenes };
        });
      } catch (err) {
        console.error("Regenerate shot failed:", err);
      }
    },
    [screenplay]
  );

  const reset = useCallback(() => {
    setScreenplay(null);
    setStatus("idle");
    setProgressMessage("");
    setProgress(0);
    setTaskId(null);
    setSelectedSceneIndex(0);
    setSelectedShotId(null);
    setSelectedCharacterId(null);
  }, []);

  return {
    screenplay,
    status,
    progressMessage,
    progress,
    taskId,
    selectedSceneIndex,
    selectedShotId,
    selectedCharacterId,
    originalText,
    paragraphs,
    setSelectedSceneIndex,
    setSelectedShotId,
    setSelectedCharacterId,
    startConvert,
    cancelConvert,
    handleRegenerateShot,
    updateScreenplay,
    undo,
    redo,
    canUndo,
    canRedo,
    loadFromHistory,
    reset,
  };
}
