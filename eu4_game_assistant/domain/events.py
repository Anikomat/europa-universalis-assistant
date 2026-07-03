"""
事件定义 — 所有事件类型的数据类
"""
import time
from dataclasses import dataclass, field


@dataclass
class TickEvent:
    """脉冲事件"""
    timestamp: float = field(default_factory=time.time)


@dataclass
class UserInputEvent:
    """用户输入事件"""
    message: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class DisplayMessageEvent:
    """发送到界面显示的消息"""
    text: str
    is_user: bool = False
    is_proactive: bool = False


@dataclass
class L2DActionEvent:
    """L2D 角色动作事件（AI 驱动的表情/动作控制）"""
    action: str         # "expression"
    name: str           # 表情名称（如 "生气""机智""QAQ"）
