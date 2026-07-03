"""
截图适配器 — MSS 截图 + VLM 分析
"""
import base64
import logging
from typing import Optional

from eu4_game_assistant.config.app_config import ModelConfig
from eu4_game_assistant.infrastructure.llm_client import LLMClient

logger = logging.getLogger(__name__)

try:
    import mss
    import mss.tools
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class ScreenshotAdapter:
    """截图 + VLM 分析"""

    def __init__(self, vlm_config: ModelConfig, monitor: int = 1):
        self._vlm_config = vlm_config
        self._vlm: Optional[LLMClient] = None
        self.monitor = monitor

    @property
    def is_available(self) -> bool:
        return HAS_MSS and bool(self._vlm_config.resolve_api_key())

    async def _get_vlm(self) -> LLMClient:
        if self._vlm is None:
            self._vlm = LLMClient(self._vlm_config)
        return self._vlm

    def capture(self) -> Optional[str]:
        """截图并返回 base64"""
        if not HAS_MSS:
            logger.warning("[截图] mss 未安装，无法截图")
            return None

        try:
            with mss.mss() as sct:
                logger.info(f"[截图] 可用显示器: {len(sct.monitors)} 个, 将截取第 {self.monitor} 个")
                monitor = sct.monitors[self.monitor]
                logger.info(f"[截图] 显示器 {self.monitor}: {monitor}")
                screenshot = sct.grab(monitor)
                png_bytes = mss.tools.to_png(screenshot.rgb, screenshot.size)
                b64 = base64.b64encode(png_bytes).decode("utf-8")
                logger.info(f"[截图] 成功 | 尺寸={screenshot.size} | PNG={len(png_bytes)}B | base64={len(b64)} 字符")
                return b64
        except Exception as e:
            logger.error(f"[截图] 失败: {e}")
            return None

    async def capture_and_describe(self, prompt: str) -> Optional[str]:
        """截图 + VLM 分析，返回自然语言描述"""
        if not self.is_available:
            logger.warning("[VLM] 截图适配器不可用 (mss=%s, key=%s)", HAS_MSS, bool(self._vlm_config.resolve_api_key()))
            return None

        b64 = self.capture()
        if not b64:
            logger.warning("[VLM] 截图返回空，跳过 VLM")
            return None

        vlm = await self._get_vlm()
        messages = [
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/png;base64,{b64}",
                }},
            ]},
        ]
        logger.info(f"[VLM] 发送请求到 {vlm._url} | model={self._vlm_config.model} | prompt={prompt[:60]}... | image_base64 长度={len(b64)}")

        try:
            text, _ = await vlm.chat(messages)
            logger.info(f"[VLM] 分析成功: {(text or '')[:(100)]}")
            return text
        except Exception as e:
            logger.error(f"VLM 分析失败: {e}")
            return None

    async def close(self):
        if self._vlm:
            await self._vlm.close()
