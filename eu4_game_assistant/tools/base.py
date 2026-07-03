"""
工具基类 — 自描述，即插即用
"""
from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """所有工具的抽象基类

    每个工具自描述其 OpenAI Function Calling schema，
    Agent 遍历工具列表即可生成完整的 tools 参数。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述（会注入 LLM context）"""
        ...

    @property
    @abstractmethod
    def parameters(self) -> dict:
        """参数 JSON Schema"""
        ...

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """执行工具，返回结果文本"""
        ...

    @property
    def openai_schema(self) -> dict:
        """自动生成 OpenAI Function Calling schema"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
