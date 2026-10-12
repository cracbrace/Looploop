"""
LLMClient 的测试替身 —— 零成本、不联网、可预测的 LLM。

为什么不用 MagicMock
-------------------
`MagicMock()` 对任意属性访问都返回新的 Mock，于是 `generate_json()` 返回的不是
JSON 字符串而是 Mock 对象，Pydantic 校验当场炸，失败信息还是
"Expected str, got MagicMock" 这类噪音，完全定位不到业务问题。

`FakeLLM` 返回**合法数据**——测试一旦失败，必是业务链路的问题，而不是替身的问题。
这正是「mock 不是随便造个假的，而是造个符合契约的假的」。

两种工作模式
-----------
1. **按 prompt 分发**（默认）——用于跑完整 Pipeline。
   被测代码的调用顺序由 Pipeline 自己决定，写死「第 N 次返回什么」的脚本式替身
   极容易错位；按 prompt 特征串分发则与顺序天然解耦。
2. **脚本回放**（`responses=[...]`）——用于精确控制「先坏后好」的重试路径，
   例如 PR 11 的 SafeParser 重试、PR 10 的确定性事件序列。
"""

from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import dataclass
from typing import Any, Sequence

from backend.models import Character, Meta, Scene, Screenplay, Shot

# ============================================================
# 调用记录
# ============================================================


@dataclass(frozen=True)
class FakeLLMCall:
    """一次 LLM 调用的完整现场，供断言「mock 真的被走到了、走到了哪条路」。"""

    method: str
    prompt: str
    system_prompt: str
    temperature: float


# ============================================================
# prompt 特征串 —— 分发依据
# ============================================================

#: SafeParser 的修正 prompt / system prompt 特征
MARKER_FIX = "请修正"
MARKER_FIX_SYSTEM = "JSON 数据修正专家"
#: CharacterResolver.deduplicate() 的 Phase 2 语义消歧
MARKER_MERGE_GROUPS = "merge_groups"
#: CharacterResolver._confirm_alias() 的是否同一人判断
MARKER_SAME_PERSON = "same_person"
#: ChapterExtractor 的逐段提取（输出格式模板里含 characters_found）
MARKER_EXTRACTION = "characters_found"


# ============================================================
# 合法数据工厂
# ============================================================

#: 提取结果里刻意使用的可识别内容，用于断言「剧本确实出自 FakeLLM」
FAKE_LOCATION = "红岸基地 · 山顶 · 夜"
FAKE_SHOT_TYPES = ("远景", "近景")
FAKE_DIALOGUE_LINE = "谢谢。"
FAKE_CHARACTER = "叶文洁"

_EXTRACTION_TEMPLATE: dict[str, Any] = {
    "scenes": [
        {
            "location": FAKE_LOCATION,
            "time_of_day": "night",
            "atmosphere": "压抑、孤独",
            "weather": "暴风雪",
            "era": "1969年冬",
            "duration_estimate": "24s",
            "source_paragraphs": [0, 1],
            "shots": [
                {
                    "shot_type": "远景",
                    "camera_movement": "推进",
                    "focus_subject": "红岸基地",
                    "visual_prompt": (
                        "Wide shot of an isolated radar base on a snowy mountain "
                        "ridge at night, 1969 China, bleak and lonely, cinematic"
                    ),
                    "timeline": ["0-8s: 远景建立荒凉环境", "8-16s: 推进至基地铁门"],
                    "background": "暴风雪",
                    "character": "",
                    "line": "",
                    "emotion": "",
                    "delivery": "",
                    "sfx": "风雪呼啸",
                    "bgm": "低沉弦乐",
                    "duration": "16s",
                    "source_paragraphs": [0, 1],
                },
                {
                    "shot_type": "近景",
                    "camera_movement": "固定",
                    "focus_subject": FAKE_CHARACTER,
                    "visual_prompt": (
                        "Close-up of a young Chinese woman in a military coat "
                        "reading a printout under cold blue light, 1969, cinematic"
                    ),
                    "timeline": ["0-8s: 叶文洁低头读数据"],
                    "background": "控制室",
                    "character": FAKE_CHARACTER,
                    "line": FAKE_DIALOGUE_LINE,
                    "emotion": "冷静",
                    "delivery": "慢",
                    "sfx": "",
                    "bgm": "",
                    "duration": "8s",
                    "source_paragraphs": [2, 3],
                },
            ],
        }
    ],
    "characters_found": [FAKE_CHARACTER],
}


def default_extraction_payload() -> dict[str, Any]:
    """ChapterExtractor 期望的响应体（scene/shot/characters_found 全结构）。"""
    return copy.deepcopy(_EXTRACTION_TEMPLATE)


def make_valid_shot(**overrides) -> dict[str, Any]:
    """一份能通过 `Shot` 校验的镜头字典。"""
    shot = {
        "shot_id": "s01_01",
        "shot_number": 1,
        "shot_type": "特写",
        "camera_movement": "推进",
        "focus_subject": FAKE_CHARACTER,
        "visual_prompt": (
            "Close-up of a young woman in a military coat looking at the starry "
            "sky, cinematic, 1970s China snow"
        ),
        "duration": "8s",
    }
    shot.update(overrides)
    return shot


def make_valid_screenplay(title: str = "假剧本 · FakeLLM") -> Screenplay:
    """一份最小合法 Screenplay，可被 `Screenplay.model_validate` 接受。"""
    return Screenplay(
        meta=Meta(
            title=title,
            source="FakeLLM 测试源",
            author="FakeLLM",
            genre="科幻",
            total_scenes=1,
            total_shots=1,
            total_duration_estimate="8s",
        ),
        characters=[
            Character(
                character_id="char_000",
                material_id="C01",
                canonical_name=FAKE_CHARACTER,
                aliases=["小叶"],
                description="FakeLLM 构造的测试角色",
                role_type="protagonist",
                gender="female",
                age_range="25-30",
            )
        ],
        scenes=[
            Scene(
                scene_id="s01",
                material_id="S01",
                scene_number=1,
                location=FAKE_LOCATION,
                time_of_day="night",
                atmosphere="孤独",
                duration_estimate="8s",
                shots=[Shot(**make_valid_shot())],
            )
        ],
    )


def make_valid_screenplay_dict(title: str = "假剧本 · FakeLLM") -> dict[str, Any]:
    """`make_valid_screenplay()` 的 dict 形态，可直接喂给 `database.save_screenplay()`。"""
    return make_valid_screenplay(title).model_dump()


def make_valid_screenplay_json(title: str = "假剧本 · FakeLLM") -> str:
    """`make_valid_screenplay()` 的 JSON 字符串形态，用于模拟 LLM 原始输出。"""
    return json.dumps(make_valid_screenplay_dict(title), ensure_ascii=False)


# ============================================================
# FakeLLM
# ============================================================


class FakeLLM:
    """
    与 `backend.llm_client.LLMClient` 同接口的测试替身。

    可直接替换 `backend.routes.get_llm` 的返回值，从而让
    POST /convert → 后台 Pipeline → SSE 全链路在断网环境下跑通。
    """

    def __init__(
        self,
        responses: Sequence[str] | None = None,
        extraction_payload: dict[str, Any] | None = None,
        merge_groups: Sequence[Sequence[str]] | None = None,
        same_person: bool = True,
        delay_seconds: float = 0.0,
    ):
        """
        Args:
            responses: 脚本回放模式——按调用顺序依次返回；给 None 则走 prompt 分发。
            extraction_payload: 覆盖逐段提取的响应体。
            merge_groups: 语义消歧（deduplicate Phase 2）返回的合并组。
            same_person: `_confirm_alias` 的回答。
            delay_seconds: 每次 `generate_json` 人为延迟的秒数。
                用来制造「Pipeline 静默期」，验证 SSE 心跳确实发出（PR 10）。
        """
        self.responses: list[str] | None = list(responses) if responses is not None else None
        self.extraction_payload = extraction_payload
        self.merge_groups = [list(group) for group in (merge_groups or [])]
        self.same_person = same_person
        self.delay_seconds = delay_seconds

        #: 每一次调用的现场记录——「mock 真的被走到」的可断言证据
        self.calls: list[FakeLLMCall] = []

    # ------------------------------------------------------------
    # 断言辅助
    # ------------------------------------------------------------

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def prompts_containing(self, needle: str) -> list[str]:
        """返回所有包含指定特征串的 prompt，用于断言走了哪条业务分支。"""
        return [call.prompt for call in self.calls if needle in call.prompt]

    # ------------------------------------------------------------
    # LLMClient 接口
    # ------------------------------------------------------------

    async def generate_json(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.3,
        max_retries: int = 2,
    ) -> str:
        self.calls.append(FakeLLMCall("generate_json", prompt, system_prompt, temperature))
        await self._maybe_delay()
        return self._respond(prompt, system_prompt)

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_retries: int = 2,
    ) -> str:
        self.calls.append(FakeLLMCall("generate_text", prompt, system_prompt, temperature))
        if self.responses is not None:
            return self._next_scripted()
        return "【FakeLLM】这是一段确定性的文本响应。"

    def generate_json_sync(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.3,
    ) -> str:
        self.calls.append(FakeLLMCall("generate_json_sync", prompt, system_prompt, temperature))
        return self._respond(prompt, system_prompt)

    def generate_text_sync(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
    ) -> str:
        self.calls.append(FakeLLMCall("generate_text_sync", prompt, system_prompt, temperature))
        return "【FakeLLM】这是一段确定性的文本响应。"

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """与 LLMClient 对齐的粗略估算（测试里不需要 tiktoken 精度）。"""
        return max(1, len(text) // 2)

    # ------------------------------------------------------------
    # 内部分发
    # ------------------------------------------------------------

    async def _maybe_delay(self) -> None:
        """人为制造静默——用于验证「Pipeline 无推送时 SSE 心跳照发」（PR 10）。"""
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)

    def _next_scripted(self) -> str:
        if not self.responses:
            raise AssertionError(
                f"FakeLLM 的脚本已用尽，但被测代码又发起了第 {self.call_count} 次调用；"
                "请在 responses 里补足期望的响应数，或改用默认的 prompt 分发模式"
            )
        return self.responses.pop(0)

    def _respond(self, prompt: str, system_prompt: str) -> str:
        if self.responses is not None:
            return self._next_scripted()
        return self._dispatch(prompt, system_prompt)

    def _dispatch(self, prompt: str, system_prompt: str) -> str:
        """
        按 prompt 特征串选择预置响应。

        判断顺序即优先级：SafeParser 的修正 prompt 会把**原始非法 JSON 全文**
        贴进来，其中很可能含 `characters_found` 之类的特征串，
        因此修正分支必须排在最前面，否则会被误判成提取请求。
        """
        if MARKER_FIX in prompt or MARKER_FIX_SYSTEM in system_prompt:
            # 单镜头修正 vs 整份剧本修正
            if "Shot" in prompt:
                return json.dumps(make_valid_shot(), ensure_ascii=False)
            return make_valid_screenplay_json()

        if MARKER_MERGE_GROUPS in prompt:
            return json.dumps({"merge_groups": self.merge_groups}, ensure_ascii=False)

        if MARKER_SAME_PERSON in prompt:
            return json.dumps({"same_person": self.same_person})

        if MARKER_EXTRACTION in prompt:
            payload = self.extraction_payload or default_extraction_payload()
            return json.dumps(payload, ensure_ascii=False)

        raise AssertionError(
            "FakeLLM 收到无法识别的 prompt——说明被测代码新增了一条 LLM 调用路径，"
            "需要在 FakeLLM._dispatch 中补上对应分支。\n"
            f"prompt 前 300 字符：{prompt[:300]}"
        )
