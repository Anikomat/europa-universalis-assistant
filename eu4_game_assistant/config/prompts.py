"""
Prompt 管理器 — 从 prompts.yaml 加载并组装 System Prompt

Router prompt：给 llm_router 用的功能性 prompt，专注工具决策
Reply prompt：给 llm_reply 用的灰风人格 prompt，只在最终回复时使用
"""
import yaml
from pathlib import Path
from typing import Optional


class PromptManager:
    def __init__(self, path: Optional[Path] = None):
        path = path or Path(__file__).parent.parent / "prompts.yaml"
        with open(path, "r", encoding="utf-8") as f:
            self._p = yaml.safe_load(f)

    # ── L1 Router（工具决策） ──
    def build_l1_router(self, summary: str, has_vlm: bool = False) -> str:
        capture_line = "- capture_screen: 截图分析游戏画面，耗时 1~3 秒。当玩家询问当前局势或需要看画面时按需调用，不必每次都调。" if has_vlm else ""
        return self._p["router_l1"].format(
            context_block=self._p["context_block"].format(summary=summary),
            tools_block=self._p["tools_block"].format(capture_screen_line=capture_line),
        )

    # ── L1 Reply（最终回复，带灰风人格） ──
    def build_l1_reply(self, summary: str) -> str:
        return self._p["reply_l1"].format(
            context_block=self._p["context_block"].format(summary=summary),
            rules_block=self._p["rules_block"],
        )

    # ── L2 Router（脉冲工具决策） ──
    def build_l2_router(self, summary: str, has_vlm: bool) -> str:
        capture_line = "- capture_screen: 截图分析游戏画面，耗时 1~3 秒。在需要视觉信息时使用。" if has_vlm else ""
        return self._p["router_l2"].format(
            tools_block=self._p["tools_block"].format(capture_screen_line=capture_line),
        )

    # ── L2 Reply（脉冲最终回复，带灰风人格） ──
    def build_l2_reply(self, summary: str) -> str:
        return self._p["reply_l2"].format(
            context_block=self._p["context_block"].format(summary=summary),
            rules_block=self._p["rules_block"],
        )

    # ── VLM Prompt ──
    @property
    def vlm_describe(self) -> str:
        return self._p["vlm_describe"]
