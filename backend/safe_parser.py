"""
安全解析与自我修正模块

Pydantic 校验 LLM 输出 + 失败自动重试。
LLM 偶尔会输出不合法的 JSON（枚举值错误、字段缺失、visual_prompt 过短）。
此模块在 Pydantic 校验失败时，将 ValidationError 详情喂回 LLM，触发自我修正。

设计原则：
- JSON in → Pydantic validate → pass / retry with error context
- 最多 3 次重试，保守的 temperature 爬升
- 失败不静默吞掉，抛出 SafeParseError 包含完整上下文
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import yaml
from pydantic import ValidationError

from backend.config import settings
from backend.llm_client import LLMClient
from backend.models import Screenplay, Shot


# ============================================================
# 异常
# ============================================================

class SafeParseError(RuntimeError):
    """安全解析失败（3 次重试后仍无法生成合法数据）"""

    def __init__(self, message: str, errors: list[dict] | None = None):
        super().__init__(message)
        self.errors = errors or []


# ============================================================
# 安全解析器
# ============================================================

class SafeParser:
    """
    Pydantic 校验 + LLM 自我修正循环。

    用法：
        parser = SafeParser(llm_client)
        screenplay = await parser.validate_and_retry(raw_json)
    """

    # 自我修正的 system prompt
    FIX_SYSTEM_PROMPT = """你是一个精确的 JSON 数据修正专家。

你的任务是接收一段有格式错误的 JSON 和对应的错误描述，
修正所有错误后输出合法 JSON。

修正规则：
1. 确保所有枚举字段使用合法值
2. 确保 visual_prompt 长度 >= 20 字符
3. 确保每个场景至少包含 1 个镜头
4. 确保所有 ID 格式正确（如 shot_id 为 "s01_01" 格式）
5. 只输出修正后的完整 JSON，不要包含任何额外说明"""

    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.max_retries = settings.max_retries

    # ============================================================
    # 公开接口
    # ============================================================

    async def validate_and_retry(
        self,
        raw_json: str,
        max_retries: int | None = None,
    ) -> Screenplay:
        """
        校验 JSON 并转换为 Screenplay，失败时自动重试。

        Args:
            raw_json: LLM 返回的原始 JSON 字符串
            max_retries: 最大重试次数（默认 3）

        Returns:
            通过 Pydantic 校验的 Screenplay 对象

        Raises:
            SafeParseError: 所有重试失败
        """
        retries = max_retries if max_retries is not None else self.max_retries

        # 第一轮
        try:
            return self._validate(raw_json)
        except ValidationError as e:
            errors = self._collect_errors(e)

        if retries == 0:
            raise SafeParseError(
                "首次校验失败且 max_retries=0。",
                errors=errors,
            )

        # 重试循环
        last_errors = errors
        for attempt in range(retries):
            try:
                fix_prompt = self._build_fix_prompt(raw_json, last_errors, attempt)
                fixed_json = await self.llm.generate_json(
                    prompt=fix_prompt,
                    system_prompt=self.FIX_SYSTEM_PROMPT,
                    temperature=0.2 + 0.1 * attempt,  # 逐步提高温度增加多样性
                )
                return self._validate(fixed_json)

            except ValidationError as e:
                last_errors = self._collect_errors(e)
                raw_json = fixed_json  # 下一轮基于修正后的 JSON

        raise SafeParseError(
            f"LLM 在 {retries} 次尝试后仍无法生成合法 Screenplay。",
            errors=last_errors,
        )

    async def validate_single_shot(self, raw_json: str) -> Shot:
        """
        单镜头校验（用于 Human-in-the-loop 重刷场景）。

        比完整 Screenplay 校验更轻量，速度快 3-5x。
        """
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            raise SafeParseError(f"JSON 解析失败: {e}")

        # 如果 LLM 返回的是完整 Screenplay，取第一个 shot
        if "shots" in data:
            data = data["shots"][0] if data["shots"] else data
        if "scenes" in data:
            scenes = data["scenes"]
            if scenes and "shots" in scenes[0]:
                data = scenes[0]["shots"][0]

        try:
            return Shot.model_validate(data)
        except ValidationError as e:
            # 单 shot 场景重试一次
            fix_prompt = self._build_single_shot_fix_prompt(data, e)
            fixed_json = await self.llm.generate_json(
                prompt=fix_prompt,
                system_prompt=self.FIX_SYSTEM_PROMPT,
                temperature=0.3,
            )
            fixed_data = json.loads(fixed_json)
            return Shot.model_validate(fixed_data)

    @staticmethod
    def screenplay_to_yaml(screenplay: Screenplay) -> str:
        """Screenplay → 干净合法的 YAML 字符串"""
        return yaml.dump(
            screenplay.model_dump(),
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            indent=2,
        )

    # ============================================================
    # 内部方法
    # ============================================================

    @staticmethod
    def _validate(raw_json: str) -> Screenplay:
        """JSON 字符串 → Pydantic Screenplay"""
        return Screenplay.model_validate_json(raw_json)

    @staticmethod
    def _collect_errors(e: ValidationError) -> list[dict]:
        """从 Pydantic ValidationError 中提取结构化错误列表"""
        errors = []
        for err in e.errors():
            errors.append({
                "location": " -> ".join(str(loc) for loc in err.get("loc", [])),
                "type": err.get("type", "unknown"),
                "message": err.get("msg", ""),
                "input": str(err.get("input", ""))[:100],  # 截断过长输入
            })
        return errors

    def _build_fix_prompt(
        self,
        original_json: str,
        errors: list[dict],
        attempt: int,
    ) -> str:
        """构建修正 prompt"""
        error_lines = []
        for i, e in enumerate(errors, 1):
            error_lines.append(
                f"{i}. 字段 `{e['location']}`: {e['message']} "
                f"(类型: {e['type']}, 当前值: {e['input']})"
            )

        return f"""以下 JSON 在 Pydantic 校验时出现了 {len(errors)} 个错误（第 {attempt + 1} 次尝试）：

错误详情：
{chr(10).join(error_lines)}

原始 JSON：
```json
{original_json[:3000]}
```

请修正以上所有错误，输出完整合法的 JSON。
只输出 JSON，不要包含任何其他内容。"""

    def _build_single_shot_fix_prompt(
        self,
        data: dict,
        e: ValidationError,
    ) -> str:
        """构建单 shot 修正 prompt"""
        errors = self._collect_errors(e)
        error_lines = []
        for i, err in enumerate(errors, 1):
            error_lines.append(
                f"{i}. 字段 `{err['location']}`: {err['message']}"
            )

        return f"""以下 Shot JSON 有 {len(errors)} 个错误：

{chr(10).join(error_lines)}

原始数据：
```json
{json.dumps(data, ensure_ascii=False, indent=2)}
```

请修正后只输出该 Shot 的合法 JSON。"""
