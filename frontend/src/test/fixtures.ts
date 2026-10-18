import type { Scene, Screenplay, Shot } from "../types/screenplay";

/**
 * 组件测试共用的 fixture。
 *
 * 用 `satisfies` 而不是 `as`：字段写错/写漏时 `tsc -b` 会直接报错，
 * 而不是把错误悄悄放过 —— 这正是 PR 16 计划里要求的「类型守卫」。
 */

const baseShot = {
  shot_id: "s01_01",
  shot_number: 1,
  shot_type: "特写",
  camera_movement: "推进",
  focus_subject: "叶文洁",
  visual_prompt:
    "Close-up of a young woman in a military coat reading a printout, 1969, cinematic",
  duration: "8s",
  source_paragraphs: [0],
  extra: {},
} satisfies Shot;

const baseDialogue = {
  character: "叶文洁",
  character_id: "char_000",
  line: "谢谢。",
  emotion: "冷静",
} satisfies NonNullable<Shot["dialogue"]>;

export function makeShot(overrides: Partial<Shot> = {}): Shot {
  return { ...baseShot, ...overrides };
}

export function makeShotWithDialogue(overrides: Partial<Shot> = {}): Shot {
  return makeShot({ dialogue: baseDialogue, ...overrides });
}

const baseScene = {
  scene_id: "s01",
  material_id: "S01",
  scene_number: 1,
  location: "红岸基地",
  time_of_day: "night",
  atmosphere: "孤独",
  duration_estimate: "8s",
  source_paragraphs: [0],
  shots: [baseShot],
} satisfies Scene;

export function makeScene(overrides: Partial<Scene> = {}): Scene {
  return { ...baseScene, ...overrides };
}

export function makeScreenplay(overrides: Partial<Screenplay> = {}): Screenplay {
  return {
    meta: {
      title: "测试剧本",
      source: "测试",
      author: "测试",
      genre: "科幻",
      total_scenes: 1,
      total_shots: 1,
      total_duration_estimate: "8s",
      language: "zh-CN",
      version: "0.1.0",
    },
    characters: [
      {
        character_id: "char_000",
        material_id: "C01",
        canonical_name: "叶文洁",
        aliases: ["小叶"],
        description: "物理学家",
        role_type: "protagonist",
        gender: "female",
        age_range: "25-30",
      },
    ],
    scenes: [baseScene],
    ...overrides,
  };
}

/** 供 Sidebar 使用的轻量场景列表 */
export function makeSceneList(count: number): Array<Pick<Scene, "scene_id" | "material_id" | "location">> {
  return Array.from({ length: count }, (_, i) => ({
    scene_id: `s0${i + 1}`,
    material_id: `S0${i + 1}`,
    location: `地点${i + 1}`,
  }));
}
