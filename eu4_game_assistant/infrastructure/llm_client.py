"""
async LLM 客户端 — 多模型支持 + Function Calling
"""
import asyncio
import json
import logging
from typing import Optional

import httpx

from eu4_game_assistant.config.app_config import ModelConfig

logger = logging.getLogger(__name__)


class LLMClient:
    """异步 LLM 客户端，支持 OpenAI 兼容 API + Function Calling"""

    def __init__(self, config: ModelConfig):
        self.config = config
        self._client = httpx.AsyncClient(timeout=config.timeout)
        self._api_key = config.resolve_api_key()
        if not self._api_key:
            logger.warning(f"模型 [{config.model}] 未配置 API Key")

    @property
    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

    @property
    def _url(self) -> str:
        return self.config.api_base.rstrip("/") + "/chat/completions"

    async def chat(
        self,
        messages: list,
        tools: Optional[list] = None,
    ) -> tuple[Optional[str], list[dict]]:
        """发送对话，返回 (text_content, tool_calls)"""
        body = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        last_error = None
        for attempt in range(self.config.max_retries):
            try:
                resp = await self._client.post(
                    self._url, headers=self._headers, json=body
                )
                resp.raise_for_status()
                raw = resp.json()

                choice = raw["choices"][0]
                msg = choice.get("message", {})
                text = msg.get("content")
                tool_calls = msg.get("tool_calls", [])

                if choice.get("finish_reason") == "tool_calls" and tool_calls:
                    text = None

                return text, tool_calls

            except httpx.HTTPStatusError as e:
                last_error = e
                # 尝试读取错误响应体
                try:
                    err_body = e.response.text[:500] if e.response else "无响应体"
                except Exception:
                    err_body = "无法读取"
                logger.warning(
                    f"LLM 请求失败 (attempt {attempt + 1}/{self.config.max_retries}): {e} | body={err_body}"
                )
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
            except Exception as e:
                last_error = e
                logger.error(f"LLM 请求异常: {e}")
                break

        err_msg = f"[LLM错误: {last_error}]"
        logger.error(err_msg)
        return None, []

    async def chat_complete(self, messages: list) -> str:
        """同步获取文本响应（不使用工具）"""
        text, _ = await self.chat(messages)
        return text or ""

    async def close(self):
        await self._client.aclose()
