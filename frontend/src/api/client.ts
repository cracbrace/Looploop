/**
 * Looploop API 客户端
 *
 * 封装所有后端 API 调用。
 */

import type { Screenplay, Shot, PipelineStage } from "../types/screenplay";

const BASE = "/api";

export async function convertNovel(
  text: string,
  meta?: { title?: string; author?: string; genre?: string }
): Promise<string> {
  const res = await fetch(`${BASE}/convert`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, ...meta }),
  });
  if (!res.ok) throw new Error(`Convert failed: ${res.statusText}`);
  const data = await res.json();
  return data.task_id;
}

export function streamProgress(
  taskId: string,
  onStage: (stage: PipelineStage) => void,
  onDone: () => void,
  onError: (err: string) => void,
): AbortController {
  const controller = new AbortController();

  fetch(`${BASE}/convert/${taskId}/stream`, { signal: controller.signal })
    .then((res) => {
      if (!res.body) throw new Error("No response body");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      function read() {
        reader.read().then(({ done, value }) => {
          if (done) return;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                const data = JSON.parse(line.slice(6));
                if (data.stage === "done") {
                  onDone();
                } else if (data.stage === "error") {
                  onError(data.message || "Unknown error");
                } else {
                  onStage(data);
                }
              } catch {
                // skip unparseable lines
              }
            }
          }
          read();
        });
      }
      read();
    })
    .catch((err) => {
      if (err.name !== "AbortError") {
        onError(err.message);
      }
    });

  return controller;
}

export async function getScreenplay(
  taskId: string
): Promise<Screenplay> {
  const res = await fetch(`${BASE}/screenplay/${taskId}`);
  if (!res.ok) throw new Error(`Get screenplay failed: ${res.statusText}`);
  return res.json();
}

export async function regenerateShot(
  sceneId: string,
  shotId: string,
  currentScreenplay: Screenplay,
  userFeedback?: string,
): Promise<Shot> {
  const res = await fetch(
    `${BASE}/shots/${sceneId}/${shotId}/regenerate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_feedback: userFeedback || "",
        current_screenplay: currentScreenplay,
      }),
    }
  );
  if (!res.ok) throw new Error(`Regenerate failed: ${res.statusText}`);
  const data = await res.json();
  return data.shot;
}

export function getYamlUrl(taskId: string): string {
  return `${BASE}/screenplay/${taskId}/export/yaml`;
}

export function getZipUrl(taskId: string): string {
  return `${BASE}/screenplay/${taskId}/export/zip`;
}

export function getManifestUrl(taskId: string): string {
  return `${BASE}/screenplay/${taskId}/export/manifest`;
}

export function getWordUrl(taskId: string): string {
  return `${BASE}/screenplay/${taskId}/export/word`;
}

export async function fetchHistory(): Promise<
  Array<{ task_id: string; title: string; status: string; created_at: string }>
> {
  const res = await fetch(`${BASE}/tasks`);
  if (!res.ok) throw new Error("Failed to fetch history");
  return res.json();
}

export async function deleteTask(taskId: string): Promise<void> {
  const res = await fetch(`${BASE}/tasks/${taskId}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete task");
}

export async function renameTask(taskId: string, title: string): Promise<void> {
  const res = await fetch(`${BASE}/tasks/${taskId}/title`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error("Failed to rename task");
}

export async function saveScreenplay(
  taskId: string,
  screenplay: Screenplay
): Promise<void> {
  const res = await fetch(`${BASE}/screenplay/${taskId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ screenplay }),
  });
  if (!res.ok) throw new Error("Failed to save screenplay");
}
