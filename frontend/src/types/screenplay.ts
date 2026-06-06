/**
 * Looploop TypeScript 类型定义
 *
 * 与后端 Pydantic 模型一一对应。
 */

export interface Meta {
  title: string;
  source: string;
  author: string;
  genre: string;
  total_scenes: number;
  total_shots: number;
  total_duration_estimate: string;
  target_platform?: string;
  language: string;
  version: string;
}

export interface Dialogue {
  character: string;
  character_id: string;
  line: string;
  emotion: string;
  delivery?: string;
}

export interface Shot {
  shot_id: string;
  shot_number: number;
  shot_type: string;
  camera_movement: string;
  focus_subject: string;
  visual_prompt: string;
  timeline?: string[];
  background?: string;
  dialogue?: Dialogue;
  sfx?: string;
  bgm?: string;
  duration: string;
  source_paragraphs: number[];
  extra: Record<string, unknown>;
}

export interface Scene {
  scene_id: string;
  material_id?: string;
  scene_number: number;
  location: string;
  time_of_day: string;
  era?: string;
  atmosphere: string;
  weather?: string;
  duration_estimate: string;
  source_paragraphs: number[];
  shots: Shot[];
}

export interface Character {
  character_id: string;
  material_id?: string;
  canonical_name: string;
  aliases: string[];
  description: string;
  role_type: string;
  gender: string;
  age_range: string;
}

export interface Screenplay {
  meta: Meta;
  characters: Character[];
  scenes: Scene[];
}

export interface QualityReport {
  character_stats: CharacterStat[];
  shot_type_distribution: Record<string, number>;
  camera_movement_distribution: Record<string, number>;
  scene_duration_breakdown: SceneDuration[];
  issues: Issue[];
  total_scenes: number;
  total_shots: number;
  total_characters: number;
  total_dialogue_shots: number;
  silent_shot_ratio: number;
  issue_count: number;
  error_count: number;
  warning_count: number;
}

export interface CharacterStat {
  character_id: string;
  canonical_name: string;
  total_appearances: number;
  total_lines: number;
  scene_ids: string[];
  first_scene: string;
}

export interface SceneDuration {
  scene_id: string;
  scene_number: number;
  location: string;
  duration_estimate: string;
  shot_count: number;
}

export interface Issue {
  severity: string;
  type: string;
  message: string;
  location: string;
}

export interface PipelineStage {
  stage: string;
  message: string;
  progress: number;
  data?: Record<string, unknown>;
  logs?: string[];
}

export type PipelineStatus =
  | "idle"
  | "pending"
  | "running"
  | "splitting"
  | "extracting"
  | "characters_refine"
  | "merging"
  | "building"
  | "done"
  | "error";
