"""
search_wiki 工具 — RAG 检索 EU4 知识库
"""
from eu4_game_assistant.tools.base import BaseTool
from eu4_game_assistant.infrastructure.rag import RAGAdapter


class SearchWikiTool(BaseTool):
    """搜索 EU4 Wiki 知识库"""

    def __init__(self, rag: RAGAdapter):
        self._rag = rag

    @property
    def name(self) -> str:
        return "search_wiki"

    @property
    def description(self) -> str:
        return (
            "搜索 EU4 游戏 Wiki 知识库。"
            "当玩家问到具体国家、事件、任务、机制、成就等内容时使用。"
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，例如 '大明科技发展'、'彗星事件选项'",
                }
            },
            "required": ["query"],
        }

    async def execute(self, query: str) -> str:
        return self._rag.search(query)
