"""
play_expression 工具 — AI 控制 L2D 角色表情

启动时从模型 JSON 文件解析可用表情列表，注入工具描述。
AI 根据对话内容自主选择合适的表情。
"""
import json
import logging
from pathlib import Path

from eu4_game_assistant.tools.base import BaseTool
from eu4_game_assistant.infrastructure.event_bus import EventBus
from eu4_game_assistant.domain.events import L2DActionEvent

logger = logging.getLogger(__name__)


def parse_expressions(model_json_path: Path) -> list[str]:
    """从模型 JSON 中提取表情名称列表（过滤掉非表情条目如物理文件）"""
    with open(model_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    expressions = data.get("FileReferences", {}).get("Expressions", [])
    names = []
    for exp in expressions:
        name = exp.get("Name", "")
        # 过滤掉物理文件等非表情条目
        if name and not name.endswith(".physics3"):
            names.append(name)
    return names


class PlayExpressionTool(BaseTool):
    """AI 控制角色表情"""

    def __init__(self, bus: EventBus, expressions: list[str]):
        self._bus = bus
        self._expressions = expressions

    @property
    def name(self) -> str:
        return "play_expression"

    @property
    def description(self) -> str:
        return (
            "切换角色表情，根据回复语气从可选值中自行选择匹配的表情。"
            "不要使用含义不明或无法理解的表达式。"
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": f"表情名称，可选值：{' / '.join(self._expressions)}",
                    "enum": self._expressions,
                },
            },
            "required": ["name"],
        }

    async def execute(self, name: str = "") -> str:
        if name not in self._expressions:
            return f"未知表情: {name}，可用: {', '.join(self._expressions)}"
        logger.info(f"[表情] AI 触发: {name}")
        await self._bus.publish("l2d_action", L2DActionEvent(action="expression", name=name))
        return f"表情已切换为: {name}"
