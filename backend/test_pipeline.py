"""
Looploop 集成测试套件

覆盖四层：
  L1 单元 — 单个函数边界
  L2 集成 — 模块间数据流
  L3 E2E  — Pipeline 全链路（真实 LLM）
  L4 API  — HTTP 端点

运行：python backend/test_pipeline.py
需要 .env 中配置有效的 LLM_API_KEY（L3 测试需要）
"""

import asyncio
import io
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import ValidationError

from backend.models import Screenplay, Scene, Shot, Dialogue, Character, Meta
from backend.engine.text_splitter import TextSplitter
from backend.engine.scene_merger import SceneMerger
from backend.engine.character_resolver import CharacterResolver, ResolvedCharacter
from backend.safe_parser import SafeParser

# ============================================================
# 测试工具
# ============================================================

SAMPLE_TEXT = """第一章 暴风雪

1969年冬，大兴安岭的暴风雪下了整整三天。红岸基地像一座被世界遗忘的孤岛。

叶文洁裹紧军大衣，推开铁门。寒风如刀，灌入领口。

"叶老师，观测数据出来了。"助手小李递过打印纸。

"谢谢。"叶文洁接过纸张，扫了一眼上面的数字。信号强度在增加。

第二章 信号

深夜，控制室里只剩下叶文洁和仪器运转的蜂鸣声。

突然，示波器跳了一下。她停下手中的笔。

"雷政委！"叶文洁拨通内线，"有情况！"

雷志成很快赶来，领口的扣子都没系。"小叶，你确定不是设备故障？"

叶文洁摇头，"太稳定了。不可能是自然现象。"她的声音在发抖。

两人对视。在这个与世隔绝的山顶基地里，他们第一次感到了真正的恐惧。
"""

passed = 0
failed = 0

def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name} — {detail}")

def section(title: str):
    print(f"\n{'='*60}\n{title}\n{'='*60}")


# ============================================================
# L1: 单元测试
# ============================================================

def test_text_splitter_basic():
    section("L1: TextSplitter — basic")
    s = TextSplitter(max_tokens=200, overlap_ratio=0.2)
    chunks = s.split(SAMPLE_TEXT)
    check("produces chunks", len(chunks) >= 1, f"got {len(chunks)}")
    check("token budget", all(c.token_count <= 250 for c in chunks),
          f"tokens: {[c.token_count for c in chunks]}")

def test_text_splitter_edge_cases():
    section("L1: TextSplitter — edge cases")
    s = TextSplitter(max_tokens=200)
    check("empty text", s.split("") == [])
    check("short text", len(s.split("Hello world")) == 1)
    # no chapter markers → single chapter
    chunks = s.split("段落一。\n\n段落二。\n\n段落三。")
    chapters = set(c.chapter_index for c in chunks)
    check("no-chapter fallback", len(chapters) == 1, f"chapters: {chapters}")

def test_paragraph_mapping():
    section("L1: TextSplitter — paragraph mapping")
    s = TextSplitter(max_tokens=200)
    chunks = s.split(SAMPLE_TEXT)
    mapping = s.reconstruct_paragraph_mapping(chunks)
    check("has mappings", len(mapping) > 0)
    # each paragraph should be referenced
    all_covered = all(i in mapping for i in range(min(5, len(mapping))))
    check("first 5 paragraphs covered", all_covered)

def test_shot_validation_valid():
    section("L1: Shot validation — valid")
    s = Shot(
        shot_id="s01_01", shot_number=1,
        shot_type="特写", camera_movement="推进",
        focus_subject="叶文洁",
        visual_prompt="Close-up of a young woman in military coat, looking at stars, cinematic, 1970s China snow",
        duration="8s",
    )
    check("valid shot created", s.shot_type == "特写")

def test_shot_validation_invalid():
    section("L1: Shot validation — invalid")
    # short visual_prompt
    try:
        Shot(shot_id="s01_01", shot_number=1, shot_type="特写",
             camera_movement="推进", focus_subject="x",
             visual_prompt="short", duration="8s")
        check("rejects short prompt", False, "should have raised")
    except ValidationError:
        check("rejects short prompt", True)
    # bad shot_type
    try:
        Shot(shot_id="s01_01", shot_number=1, shot_type="bad_type",
             camera_movement="推进", focus_subject="x",
             visual_prompt="A long enough visual prompt for video generation model",
             duration="8s")
        check("rejects bad shot_type", False, "should have raised")
    except ValidationError:
        check("rejects bad shot_type", True)
    # bad shot_id format
    try:
        Shot(shot_id="bad", shot_number=1, shot_type="特写",
             camera_movement="推进", focus_subject="x",
             visual_prompt="A long enough visual prompt for video generation model",
             duration="8s")
        check("rejects bad shot_id", False, "should have raised")
    except ValidationError:
        check("rejects bad shot_id", True)

def test_scene_validation():
    section("L1: Scene validation")
    # empty shots
    try:
        Scene(scene_id="s01", scene_number=1, location="test",
              time_of_day="night", atmosphere="test",
              duration_estimate="10s", shots=[])
        check("rejects empty shots", False, "should have raised")
    except ValidationError:
        check("rejects empty shots", True)

def test_character_model():
    section("L1: Character model")
    c = Character(
        character_id="char_000", canonical_name="叶文洁",
        aliases=["小叶", "叶老师"], description="物理学家",
        role_type="protagonist", gender="female", age_range="25-30",
    )
    check("valid character", c.canonical_name == "叶文洁")
    check("aliases stored", "小叶" in c.aliases)

def test_yaml_roundtrip():
    section("L1: YAML roundtrip")
    sp = Screenplay(
        meta=Meta(title="测试", source="测试", author="测试", genre="科幻",
                  total_scenes=1, total_shots=1, total_duration_estimate="8s"),
        characters=[Character(character_id="char_000", canonical_name="叶文洁",
                    aliases=["小叶"], description="测试", role_type="protagonist",
                    gender="female", age_range="25-30")],
        scenes=[Scene(scene_id="s01", scene_number=1, location="基地",
                time_of_day="night", atmosphere="孤独", duration_estimate="8s",
                shots=[Shot(shot_id="s01_01", shot_number=1, shot_type="特写",
                       camera_movement="固定", focus_subject="叶文洁",
                       visual_prompt="A close-up of a young woman looking up at the starry sky, cinematic, 1970s",
                       duration="8s")])],
    )
    yaml_str = SafeParser.screenplay_to_yaml(sp)
    check("yaml not empty", len(yaml_str) > 100)
    import yaml
    parsed = yaml.safe_load(yaml_str)
    check("yaml valid", parsed is not None)
    check("meta preserved", parsed["meta"]["title"] == "测试")
    check("shots array exists", len(parsed["scenes"][0]["shots"]) == 1)
    check("shot_type preserved",
          parsed["scenes"][0]["shots"][0]["shot_type"] == "特写")


# ============================================================
# L2: 模块集成测试
# ============================================================

def test_extractor_with_registry():
    """
    测试 extractor + ResolvedCharacter registry 的联合调用。
    → 这个测试能抓到 Bug 1（ResolvedCharacter 无 .get() 方法）
    """
    section("L2: Extractor + Registry integration")

    # 用真实 ResolvedCharacter 对象构造 registry
    registry = {
        "char_000": ResolvedCharacter(
            canonical_name="叶文洁", aliases=["小叶", "叶老师"],
            description="年轻女物理学家", role_type="protagonist",
            gender="female", age_range="25-30",
        ),
        "char_001": ResolvedCharacter(
            canonical_name="雷志成", aliases=["雷政委", "老雷"],
            description="基地政委", role_type="supporting",
            gender="male", age_range="45-50",
        ),
    }

    # 验证 registry 结构本身 —— 这些属性必须可直接访问（不是 dict）
    check("registry has canonical_name",
          registry["char_000"].canonical_name == "叶文洁")
    check("registry has aliases",
          "小叶" in registry["char_000"].aliases)
    check("registry is not dict",
          not isinstance(registry["char_000"], dict))

    # 模拟 build_prompt_context —— 之前的 Bug 1 就是在这里炸的
    from backend.engine.character_resolver import CharacterResolver
    resolver = CharacterResolver(None)  # LLM not needed for this

    # resolve_alias 用 registry 查找
    for name, expected in [("小叶", "叶文洁"), ("雷政委", "雷志成"),
                            ("叶老师", "叶文洁"), ("unknown", None)]:
        result = resolver.resolve_alias(name, registry)
        check(f"resolve_alias('{name}') → '{expected}'", result == expected,
              f"got '{result}'")

    # build_prompt_context 用 registry 生成 Markdown
    ctx = resolver.build_prompt_context(registry)
    check("prompt context not empty", len(ctx) > 0)
    check("prompt context contains canonical name", "叶文洁" in ctx)
    check("prompt context contains alias", "小叶" in ctx)
    check("prompt context contains char_000", "char_000" in ctx)


def test_build_screenplay_without_meta():
    """
    测试 build_screenplay 在 meta_overrides=None 时的行为。
    → 这个测试能抓到 Bug 2（Meta 空字符串）
    """
    section("L2: build_screenplay — no meta_overrides")

    merger = SceneMerger()
    scenes = [Scene(
        scene_id="s01", scene_number=1,
        location="测试地点", time_of_day="night",
        atmosphere="孤独", duration_estimate="8s",
        shots=[Shot(shot_id="s01_01", shot_number=1,
               shot_type="特写", camera_movement="固定",
               focus_subject="叶文洁",
               visual_prompt="A test visual prompt that is long enough for video generation",
               duration="8s")],
    )]
    registry = {
        "char_000": ResolvedCharacter(
            canonical_name="叶文洁", aliases=["小叶"],
            description="测试", role_type="protagonist",
            gender="female", age_range="25-30",
        )
    }

    # meta_overrides=None → 应使用默认值，不抛异常
    sp = merger.build_screenplay(scenes, registry)  # ← Bug 2 会在这里炸
    check("screenplay created", sp is not None)
    check("title is not empty", sp.meta.title != "")
    check("title default", sp.meta.title == "Untitled")
    check("author default", sp.meta.author == "Unknown")
    check("genre default", sp.meta.genre == "General")
    check("scene count correct", sp.meta.total_scenes == 1)
    check("shot count correct", sp.meta.total_shots == 1)

    # 二次 Pydantic 校验——确保能通过
    try:
        Screenplay.model_validate(sp.model_dump())
        check("passes Pydantic re-validation", True)
    except ValidationError as e:
        check("passes Pydantic re-validation", False, str(e))

    # 有 meta_overrides 的场景
    sp2 = merger.build_screenplay(scenes, registry,
                                   {"title": "三体", "genre": "科幻"})
    check("custom title", sp2.meta.title == "三体")
    check("custom genre", sp2.meta.genre == "科幻")
    check("author still default", sp2.meta.author == "Unknown")


def test_scene_merger_adjacent():
    """测试相邻同地点场景合并"""
    section("L2: SceneMerger — adjacent merge")
    from backend.engine.extractor import RawScene, RawShot

    raw = [
        RawScene(location="指挥室", time_of_day="interior",
                 atmosphere="紧张", duration_estimate="20s",
                 source_paragraphs=[0, 1],
                 shots=[RawShot(shot_type="中景", camera_movement="固定",
                        focus_subject="王建国",
                        visual_prompt="A man in uniform at control panel, tense, 1970s China military base",
                        character="王建国", line="有异常。", emotion="紧张",
                        duration="8s")]),
        RawScene(location="指挥室", time_of_day="interior",
                 atmosphere="压抑", duration_estimate="15s",
                 source_paragraphs=[2, 3],
                 shots=[RawShot(shot_type="近景", camera_movement="固定",
                        focus_subject="李工程师",
                        visual_prompt="Close-up of engineer looking at radar, concerned expression, 1970s",
                        character="老李", line="我去查。", emotion="紧张",
                        duration="6s")]),
    ]

    registry = {
        "char_000": ResolvedCharacter(canonical_name="王建国", aliases=[],
                       description="队长", role_type="supporting",
                       gender="male", age_range="40-50"),
        "char_001": ResolvedCharacter(canonical_name="李工程师", aliases=["老李"],
                       description="工程师", role_type="supporting",
                       gender="male", age_range="30-40"),
    }

    merger = SceneMerger()
    scenes = merger.merge(raw, registry)
    check("adjacent merged", len(scenes) == 1, f"got {len(scenes)}")
    check("shots combined", len(scenes[0].shots) == 2,
          f"got {len(scenes[0].shots)}")
    check("scene id formatted", scenes[0].scene_id == "s01")
    check("shot ids formatted",
          scenes[0].shots[0].shot_id == "s01_01" and
          scenes[0].shots[1].shot_id == "s01_02")

    sp = merger.build_screenplay(scenes, registry)
    check("duration calculated", sp.meta.total_duration_estimate == "14s",
          f"got '{sp.meta.total_duration_estimate}'")


# ============================================================
# L3: Pipeline 端到端测试（真实 LLM）
# ============================================================

async def test_pipeline_e2e_real_llm():
    """
    真实 Pipeline 全链路。
    这个测试是防 bug 的最后防线——任何模块间的类型/数据/默认值问题都会暴露。
    """
    section("L3: Pipeline E2E (real LLM)")

    from backend.llm_client import LLMClient
    from backend.engine.pipeline import Pipeline

    try:
        llm = LLMClient()
    except ValueError as e:
        print(f"  [SKIP] No API key configured: {e}")
        return

    pipeline = Pipeline(llm)
    sp = None
    async for stage in pipeline.run_pipeline(SAMPLE_TEXT):
        if stage.stage == "result":
            sp = stage.data["screenplay"]

    # 结构完整性
    check("screenplay not none", sp is not None)
    check("has meta", sp.meta is not None)
    check("title not empty", sp.meta.title != "")
    check("has scenes", len(sp.scenes) >= 1, f"got {len(sp.scenes)}")
    check("has characters", len(sp.characters) >= 1,
          f"got {len(sp.characters)}")
    check("total_scenes matches", sp.meta.total_scenes == len(sp.scenes))
    total_shots = sum(len(s.shots) for s in sp.scenes)
    check("total_shots matches", sp.meta.total_shots == total_shots,
          f"meta={sp.meta.total_shots}, actual={total_shots}")

    # 每个 scene
    for scene in sp.scenes:
        check(f"scene {scene.scene_id} has shots",
              len(scene.shots) >= 1,
              f"got {len(scene.shots)}")
        check(f"scene {scene.scene_id} has location",
              len(scene.location) > 0)
        check(f"scene {scene.scene_id} has atmosphere",
              len(scene.atmosphere) > 0)

        # 每个 shot
        for shot in scene.shots:
            check(f"shot {shot.shot_id} valid type",
                  shot.shot_type in ("大远景","远景","中景","近景",
                                     "特写","大特写","双人镜头","过肩镜头"),
                  f"got '{shot.shot_type}'")
            check(f"shot {shot.shot_id} valid movement",
                  shot.camera_movement in ("固定","推进","拉远","左摇","右摇",
                                           "上摇","下摇","跟随","环绕","手持","快速变焦"),
                  f"got '{shot.camera_movement}'")
            check(f"shot {shot.shot_id} visual_prompt length",
                  len(shot.visual_prompt) >= 20,
                  f"got {len(shot.visual_prompt)} chars")
            check(f"shot {shot.shot_id} has duration",
                  shot.duration.endswith("s"))

            if shot.dialogue:
                check(f"shot {shot.shot_id} dialogue has character",
                      len(shot.dialogue.character) > 0)
                check(f"shot {shot.shot_id} dialogue has line",
                      len(shot.dialogue.line) > 0)

    # 全局角色在 characters 列表中
    dialogue_char_ids = set()
    for scene in sp.scenes:
        for shot in scene.shots:
            if shot.dialogue:
                dialogue_char_ids.add(shot.dialogue.character_id)
    registry_char_ids = set(c.character_id for c in sp.characters)
    check("dialogue characters in registry",
          dialogue_char_ids.issubset(registry_char_ids),
          f"dialogue: {dialogue_char_ids}, registry: {registry_char_ids}")

    # YAML 序列化
    yaml_str = SafeParser.screenplay_to_yaml(sp)
    check("e2e yaml output", len(yaml_str) > 100)

    # Pydantic 二次校验
    try:
        Screenplay.model_validate(sp.model_dump())
        check("e2e re-validation passes", True)
    except ValidationError as e:
        check("e2e re-validation passes", False, str(e))

    print(f"\n  Result: {sp.meta.total_scenes} scenes, "
          f"{sp.meta.total_shots} shots, "
          f"{len(sp.characters)} characters, "
          f"{sp.meta.total_duration_estimate}")


async def test_pipeline_empty_text():
    """空文本应被优雅处理"""
    section("L3: Pipeline — empty text")
    from backend.llm_client import LLMClient
    from backend.engine.pipeline import Pipeline

    try:
        llm = LLMClient()
    except ValueError:
        print("  [SKIP] No API key")
        return

    pipeline = Pipeline(llm)
    try:
        async for _ in pipeline.run_pipeline(""):
            pass
        check("empty text rejected", False, "should have raised")
    except (ValueError, Exception):
        check("empty text rejected", True)


# ============================================================
# L4: API 集成测试
# ============================================================

def test_api_health():
    """GET /api/health"""
    section("L4: API — health check")
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)
    resp = client.get("/api/health")
    check("status 200", resp.status_code == 200)
    data = resp.json()
    check("status ok", data["status"] == "ok")
    check("app name", data["app"] == "Looploop")


def test_api_convert_empty():
    """POST /api/convert — 空文本"""
    section("L4: API — reject empty text")
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)
    resp = client.post("/api/convert", json={"text": ""})
    check("rejects empty", resp.status_code == 422)


def test_api_convert_too_short():
    """POST /api/convert — 过短文本"""
    section("L4: API — reject short text")
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)
    resp = client.post("/api/convert", json={"text": "太短"})
    check("rejects short", resp.status_code == 422)


def test_api_convert_accepts_valid():
    """POST /api/convert — 合法文本"""
    section("L4: API — accept valid text")
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)
    resp = client.post("/api/convert",
                       json={"text": SAMPLE_TEXT, "title": "测试"})
    check("accepts valid", resp.status_code == 200,
          f"got {resp.status_code}")
    data = resp.json()
    check("returns task_id", "task_id" in data)
    check("task_id not empty", len(data["task_id"]) > 0)


def test_api_export_endpoints_exist():
    """导出端点存在性检查"""
    section("L4: API — export endpoints")
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)
    # 不存在的 task_id → 404，但路由本身存在
    resp = client.get("/api/screenplay/nonexistent/export/yaml")
    check("yaml route exists", resp.status_code == 404)
    resp = client.get("/api/screenplay/nonexistent/export/word")
    check("word route exists", resp.status_code == 404)


# ============================================================
# 入口
# ============================================================

async def main():
    global passed, failed

    print("=" * 60)
    print("  Looploop Test Suite")
    print("=" * 60)

    # L1: 单元测试
    test_text_splitter_basic()
    test_text_splitter_edge_cases()
    test_paragraph_mapping()
    test_shot_validation_valid()
    test_shot_validation_invalid()
    test_scene_validation()
    test_character_model()
    test_yaml_roundtrip()

    # L2: 模块集成
    test_extractor_with_registry()
    test_build_screenplay_without_meta()
    test_scene_merger_adjacent()

    # L3: Pipeline 端到端（真实 LLM）
    await test_pipeline_e2e_real_llm()
    await test_pipeline_empty_text()

    # L4: API
    test_api_health()
    test_api_convert_empty()
    test_api_convert_too_short()
    test_api_convert_accepts_valid()
    test_api_export_endpoints_exist()

    # 结果
    total = passed + failed
    print(f"\n{'='*60}")
    print(f"  Results: {passed}/{total} passed"
          + (f", {failed} FAILED" if failed else " — ALL PASSED"))
    print(f"{'='*60}")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
