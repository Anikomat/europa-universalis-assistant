"""
system_stats 工具 — 获取系统资源占用（CPU、内存）
"""
import psutil
from eu4_game_assistant.tools.base import BaseTool


class SystemStatsTool(BaseTool):
    """获取系统 CPU 和内存占用"""

    @property
    def name(self) -> str:
        return "system_stats"

    @property
    def description(self) -> str:
        return (
            "获取当前电脑的 CPU 和内存占用情况。"
            "当玩家问到'电脑卡不卡'、'内存占用'、'CPU 使用率'等问题时使用。"
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self) -> str:
        cpu_percent = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        lines = [
            f"CPU 使用率: {cpu_percent:.1f}%",
            f"内存: {mem.used / (1024**3):.1f}G / {mem.total / (1024**3):.1f}G ({mem.percent:.1f}%)",
        ]
        if swap.total > 0:
            lines.append(
                f"虚拟内存: {swap.used / (1024**3):.1f}G / {swap.total / (1024**3):.1f}G ({swap.percent:.1f}%)"
            )
        return "\n".join(lines)
