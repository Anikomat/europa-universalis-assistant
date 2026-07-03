"""
双 LLM ReAct Agent — 决策与生成分阶段

- llm_router: 工具决策阶段（低温度，指令遵循好），带 tools 调用
- llm_reply:  最终回复生成（高温度，多样性），不带 tools 自由生成

流程：
1. router 用 router_prompt（功能性，无人格）决策是否调工具
2. 调工具则执行并回传结果，继续循环
3. router 决策不调工具 → 转交 reply，切换到 reply_prompt（灰风人格）生成最终回复
4. 达到 max_rounds → 同样切换 reply_prompt 生成
"""
import json
import logging
from typing import Optional, Callable, Awaitable

from eu4_game_assistant.tools.base import BaseTool
from eu4_game_assistant.infrastructure.llm_client import LLMClient

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5
MAX_TOOL_RESULT = 3000


class ReActAgent:
    """双 LLM ReAct Agent — router 与 reply 使用不同的 system prompt"""

    def __init__(self,
                 llm_router: LLMClient,
                 llm_reply: LLMClient,
                 tools: list[BaseTool],
                 system_prompt_router: str,
                 system_prompt_reply: str,
                 max_rounds: int = MAX_TOOL_ROUNDS):
        self._llm_router = llm_router
        self._llm_reply = llm_reply
        self._tools = {t.name: t for t in tools}
        self._tool_schemas = [t.openai_schema for t in tools]
        self._system_prompt_router = system_prompt_router
        self._system_prompt_reply = system_prompt_reply
        self._max_rounds = max_rounds

    async def run(self, user_message: str,
                  on_tool_call: Optional[Callable[[str, str], Awaitable[None]]] = None
                  ) -> str:
        """执行 ReAct 循环，返回最终回复"""
        messages = [
            {"role": "system", "content": self._system_prompt_router},
            {"role": "user", "content": user_message},
        ]

        for turn in range(self._max_rounds):
            # 决策阶段：router 带 tools 决策（使用 router 专属 prompt）
            logger.info(f"  [ReAct] 第 {turn + 1} 轮 — router 决策 (tools={len(self._tool_schemas)})")
            text, tool_calls = await self._llm_router.chat(messages, tools=self._tool_schemas)
            logger.info(f"  [ReAct] 第 {turn + 1} 轮 — text={str(text)[:100]} tool_calls={len(tool_calls)}")

            # 无工具调用 → 决策结束，切换到 reply prompt 生成最终回复
            if not tool_calls:
                if not text:
                    logger.warning(f"  [ReAct] 第 {turn + 1} 轮 — router 返回空 (无 text 也无 tool_calls)")
                    return "[模型无响应]"
                logger.info("  [ReAct] 决策结束，切换 reply prompt 生成最终回复")
                return await self._generate_final_reply(messages)

            # 处理工具调用
            for tc in tool_calls:
                func = tc["function"]
                name = func["name"]
                args = json.loads(func["arguments"]) if isinstance(func["arguments"], str) else func["arguments"]

                tool = self._tools.get(name)
                if not tool:
                    logger.warning(f"未知工具: {name}")
                    result = f"[未知工具: {name}]"
                else:
                    logger.info(f"  [Tool] {name}: {str(args)[:80]}")
                    result = await tool.execute(**args)
                    if on_tool_call:
                        await on_tool_call(name, result)

                messages.append({
                    "role": "assistant",
                    "content": text,
                    "tool_calls": [tc],
                })
                # 截断超长工具结果，并追加标记让 LLM 知道内容被截断
                truncated = result[:MAX_TOOL_RESULT]
                if len(result) > MAX_TOOL_RESULT:
                    truncated += "...[已截断]"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": truncated,
                })

        # 超过最大轮次 → 切换 reply prompt 生成最终回复
        logger.warning("达到最大工具调用轮次，切换 reply prompt 生成最终回复")
        return await self._generate_final_reply(messages)

    async def _generate_final_reply(self, messages: list) -> str:
        """用 reply 模型 + 灰风人格 prompt 生成最终回复

        丢弃 router 在决策阶段的草稿 text，替换 system prompt 为 reply prompt，
        让 reply 基于完整工具结果和灰风人格设定自由生成。
        """
        final_messages = [{"role": "system", "content": self._system_prompt_reply}]
        # 跳过 router 的 system prompt（messages[0]），从用户消息开始拼接
        final_messages.extend(messages[1:])
        final_messages.append({"role": "user", "content": "请基于以上信息直接回复玩家。"})
        text, _ = await self._llm_reply.chat(final_messages)
        return text or "[推理超时]"
