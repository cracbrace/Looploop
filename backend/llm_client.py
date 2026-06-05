"""
LLM API 客户端

统一封装对 DeepSeek（兼容 OpenAI SDK）的调用。
提供同步/异步接口，内置重试、token 估算、JSON 强制输出。
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Optional

import httpx
from openai import AsyncOpenAI, OpenAI

from backend.config import settings


class LLMClient:
    """
    大模型 API 客户端。

    使用 OpenAI SDK，兼容 DeepSeek API（只需改 base_url 和 api_key）。

    使用方式：
        client = LLMClient()
        json_str = await client.generate_json("请输出一个 JSON 对象...")
        text = await client.generate_text("请总结以下文本...")
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or settings.llm_api_key
        self.base_url = base_url or settings.llm_base_url
        self.model = model or settings.llm_model

        if not self.api_key:
            raise ValueError(
                "LLM API Key 未设置。请在 .env 文件中设置 LLM_API_KEY，"
                "或设置环境变量 LOOPLOOP_LLM_API_KEY。"
            )

        # 异步客户端（推荐）
        self._async_client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=httpx.Timeout(120.0, connect=10.0),
        )

        # 同步客户端（用于线程池并发场景）
        self._sync_client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=httpx.Timeout(120.0, connect=10.0),
        )

    # ============================================================
    # 异步接口（推荐）
    # ============================================================

    async def generate_json(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.3,
        max_retries: int = 2,
    ) -> str:
        """
        调用 LLM 并强制输出 JSON 字符串。

        Args:
            prompt: 用户提示
            system_prompt: 系统提示（角色设定）
            temperature: 温度参数（0-2），越低越确定。Schema 生成用 0.3
            max_retries: 网络错误重试次数

        Returns:
            LLM 返回的原始 JSON 字符串
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                response = await self._async_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content
                if content is None:
                    raise ValueError("LLM 返回为空")

                # 验证是否为合法 JSON
                json.loads(content)
                return content

            except (json.JSONDecodeError, ValueError) as e:
                # JSON 解析失败 → 重试
                last_error = e
                if attempt < max_retries:
                    messages.append({
                        "role": "user",
                        "content": (
                            f"上一轮输出不是合法 JSON，错误：{e}。"
                            f"请确保只输出合法 JSON 字符串，不要包含额外说明。"
                        ),
                    })
                    # 提高温度以增加多样性
                    temperature = min(temperature + 0.2, 1.0)

            except Exception as e:
                # 网络错误 → 重试
                last_error = e
                if attempt < max_retries:
                    wait = 2 ** attempt  # 指数退避
                    await asyncio.sleep(wait)

        raise RuntimeError(
            f"LLM 在 {max_retries + 1} 次尝试后仍失败。"
            f"最后一次错误：{last_error}"
        )

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_retries: int = 2,
    ) -> str:
        """
        通用文本生成（非 JSON 场景：角色消歧、文本总结等）。

        Args:
            prompt: 用户提示
            system_prompt: 系统提示
            temperature: 温度参数。创意任务用 0.7-1.0
            max_retries: 重试次数

        Returns:
            LLM 返回的文本
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                response = await self._async_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                )
                content = response.choices[0].message.content
                if content is None:
                    raise ValueError("LLM 返回为空")
                return content

            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)

        raise RuntimeError(
            f"LLM 在 {max_retries + 1} 次尝试后仍失败。"
            f"最后一次错误：{last_error}"
        )

    # ============================================================
    # 同步接口（用于 ThreadPoolExecutor 并发场景）
    # ============================================================

    def generate_json_sync(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.3,
    ) -> str:
        """同步版 generate_json"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self._sync_client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("LLM 返回为空")
        json.loads(content)  # 验证 JSON
        return content

    def generate_text_sync(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
    ) -> str:
        """同步版 generate_text"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self._sync_client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
        )
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("LLM 返回为空")
        return content

    # ============================================================
    # 工具方法
    # ============================================================

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """用 tiktoken 精准计算 token 数（cl100k_base 编码器）"""
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            return max(1, len(text) // 2)
