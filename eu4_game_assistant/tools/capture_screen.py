"""
capture_screen 工具 — VLM 截图分析（可选，L1/L2 均可用）
"""
import logging

from eu4_game_assistant.tools.base import BaseTool
from eu4_game_assistant.infrastructure.screenshot import ScreenshotAdapter
from eu4_game_assistant.config.prompts import PromptManager

logger = logging.getLogger(__name__)


class CaptureScreenTool(BaseTool):
    """截图 + VLM 分析游戏画面"""

    def __init__(self, screenshot: ScreenshotAdapter, prompts: PromptManager):
        self._ss = screenshot
        self._prompts = prompts

    @property
    def name(self) -> str:
        return "capture_screen"

    @property
    def description(self) -> str:
        return "截图并调用视觉模型分析当前游戏画面，返回画面描述。耗时约 1~3 秒。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {},
        }

    @property
    def is_available(self) -> bool:
        return self._ss.is_available

    async def execute(self) -> str:
        if not self._ss.is_available:
            return "[VLM 未配置，无法截图分析]"

        description = await self._ss.capture_and_describe(self._prompts.vlm_describe)
        if description:
            logger.info(f"[VLM] {description[:80]}...")
            return description
        return "[截图分析失败]"
