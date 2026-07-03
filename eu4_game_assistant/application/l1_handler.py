"""
L1 用户交互处理器
"""
import logging

from eu4_game_assistant.domain.events import UserInputEvent, DisplayMessageEvent
from eu4_game_assistant.domain.context import AgentContext
from eu4_game_assistant.infrastructure.event_bus import EventBus
from eu4_game_assistant.infrastructure.llm_client import LLMClient
from eu4_game_assistant.config.prompts import PromptManager
from eu4_game_assistant.tools.base import BaseTool
from eu4_game_assistant.tools.capture_screen import CaptureScreenTool
from eu4_game_assistant.application.agent import ReActAgent

logger = logging.getLogger(__name__)


class L1Handler:
    """处理用户输入（L1 交互）"""

    def __init__(self,
                 bus: EventBus,
                 llm_router: LLMClient,
                 llm_reply: LLMClient,
                 context: AgentContext,
                 prompts: PromptManager,
                 tools: list[BaseTool]):
        self._bus = bus
        self._llm_router = llm_router
        self._llm_reply = llm_reply
        self._context = context
        self._prompts = prompts
        self._tools = tools
        # 从工具列表推断 VLM 能力（与 L2Handler 一致）
        self._has_vlm = any(isinstance(t, CaptureScreenTool) for t in tools)

    async def handle(self, event: UserInputEvent):
        logger.info(f"[L1] 用户: {event.message}")

        # 1. 构建 Router Prompt（功能性，无人格）和 Reply Prompt（灰风人格）
        summary = await self._context.to_prompt_block()
        router_prompt = self._prompts.build_l1_router(summary, self._has_vlm)
        reply_prompt = self._prompts.build_l1_reply(summary)

        # 2. ReAct（router 用功能 prompt 决策 + reply 用灰风人格 prompt 生成）
        agent = ReActAgent(self._llm_router, self._llm_reply, self._tools,
                           router_prompt, reply_prompt)
        response = await agent.run(event.message)

        # 3. 保存对话（async 写入 + 自动过期清理，不阻塞事件循环）
        await self._context.add_conversation(f"玩家: {event.message}\n灰风: {response}")

        # 4. 输出到界面
        await self._bus.publish("display_message", DisplayMessageEvent(text=response))
