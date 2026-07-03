"""
L2 脉冲事件处理器
"""
import logging

from eu4_game_assistant.domain.events import TickEvent, DisplayMessageEvent
from eu4_game_assistant.domain.context import AgentContext
from eu4_game_assistant.infrastructure.event_bus import EventBus
from eu4_game_assistant.infrastructure.llm_client import LLMClient
from eu4_game_assistant.config.prompts import PromptManager
from eu4_game_assistant.tools.base import BaseTool
from eu4_game_assistant.tools.capture_screen import CaptureScreenTool
from eu4_game_assistant.application.agent import ReActAgent

logger = logging.getLogger(__name__)

# LLM 无话可说时输出的统一信号
SKIP_SIGNAL = "[SKIP]"


class L2Handler:
    """处理定时脉冲（L2 常规脉冲）

    设计要点：
    - 只写入最终响应结果（[SKIP] / 空 / 与上次完全相同的不写入）
    - 写入 context 让 L2 能看历史脉冲，刻意避开重复 + 保持连贯
    - 多样性约束在 reply_l2 prompt 中硬性规定
    """

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
        # 从工具列表推断 VLM 能力，避免双路径判断
        self._has_vlm = any(isinstance(t, CaptureScreenTool) for t in tools)
        self._last_response: str = ""

    async def handle(self, event: TickEvent):
        logger.info("[L2] 脉冲触发 | tools=%s | has_vlm=%s",
                    [t.name for t in self._tools], self._has_vlm)

        # 1. 构建 Router Prompt（功能性，无人格）和 Reply Prompt（灰风人格）
        summary = await self._context.to_prompt_block()
        router_prompt = self._prompts.build_l2_router(summary, self._has_vlm)
        reply_prompt = self._prompts.build_l2_reply(summary)

        logger.info("[L2] Router Prompt 前 200 字符: %s", router_prompt[:200])

        # 2. ReAct（router 用功能 prompt 决策 + reply 用灰风人格 prompt 生成）
        agent = ReActAgent(self._llm_router, self._llm_reply, self._tools,
                           router_prompt, reply_prompt)
        logger.info("[L2] 开始 ReAct 推理...")
        response = await agent.run("定时状态检查。请按系统提示的步骤执行。")
        logger.info("[L2] ReAct 完成 | response=%s", (response or "")[:150])

        # 3. 信号过滤：[SKIP] 或空响应 → 不打扰用户，不写入
        if not response or not response.strip() or response.strip() == "[模型无响应]":
            return
        if response.strip().startswith(SKIP_SIGNAL):
            logger.info("[L2] 模型主动跳过（%s）", SKIP_SIGNAL)
            return

        # 4. 重复检测：与上一条完全相同 → 跳过（不推送也不写入，避免历史污染）
        if response.strip() == self._last_response.strip():
            logger.info("[L2] 输出与上一条完全相同，跳过")
            return
        self._last_response = response

        # 5. 只写入最终响应结果，让未来脉冲能看历史以避免重复
        await self._context.add_conversation(f"[脉冲]: {response}")
        logger.info("[L2] 发送主动消息到前端...")
        await self._bus.publish("display_message",
            DisplayMessageEvent(text=response, is_proactive=True))
