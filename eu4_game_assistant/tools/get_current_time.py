"""
get_current_time 工具 — 获取当前日期时间
"""
from datetime import datetime
from eu4_game_assistant.tools.base import BaseTool


class GetCurrentTimeTool(BaseTool):
    """获取当前日期和时间"""

    @property
    def name(self) -> str:
        return "get_current_time"

    @property
    def description(self) -> str:
        return (
            "获取当前日期和时间。"
            "当玩家问到'现在几点'、'今天几号'、日期、星期等问题时使用。"
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self) -> str:
        now = datetime.now()
        weekday_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
        return (
            f"现在是 {now.year}年{now.month}月{now.day}日 {weekday_cn} "
            f"{now.hour:02d}:{now.minute:02d}:{now.second:02d}"
        )
