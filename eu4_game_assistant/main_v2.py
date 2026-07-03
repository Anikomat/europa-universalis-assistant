"""
EU4 Game Assistant — 主入口
装配容器 + 启动 FastAPI 服务器
"""
import os
import sys
import logging
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

from eu4_game_assistant.config.app_config import AppConfig, ModelConfig
from eu4_game_assistant.config.prompts import PromptManager
from eu4_game_assistant.domain.context import AgentContext
from eu4_game_assistant.infrastructure.event_bus import EventBus
from eu4_game_assistant.infrastructure.llm_client import LLMClient
from eu4_game_assistant.infrastructure.rag import RAGAdapter
from eu4_game_assistant.infrastructure.screenshot import ScreenshotAdapter
from eu4_game_assistant.tools.search_wiki import SearchWikiTool
from eu4_game_assistant.tools.capture_screen import CaptureScreenTool
from eu4_game_assistant.tools.play_expression import PlayExpressionTool, parse_expressions
from eu4_game_assistant.tools.get_current_time import GetCurrentTimeTool
from eu4_game_assistant.tools.system_stats import SystemStatsTool
from eu4_game_assistant.application.l1_handler import L1Handler
from eu4_game_assistant.application.l2_handler import L2Handler
from eu4_game_assistant.transport.server import create_app

logger = logging.getLogger(__name__)

CONTEXT_DB_PATH = Path(__file__).parent / "agent_context.db"


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


async def main():
    setup_logging()

    # ── 1. 配置 ──
    config_path = Path(__file__).parent / "config.yaml"
    if config_path.exists():
        config = AppConfig.from_yaml(config_path)
    else:
        logger.warning("config.yaml 不存在，使用默认配置")
        config = AppConfig()

    prompts = PromptManager()

    # ── 2. 基础设施 ──
    bus = EventBus()
    context = AgentContext(
        CONTEXT_DB_PATH,
        retention_hours=config.context.retention_hours,
        max_messages=config.context.max_messages,
        max_chars=config.context.max_chars,
    )

    # LLM 客户端（多模型）
    llm_router = LLMClient(config.models.get_router())
    llm_reply = LLMClient(config.models.get_reply())

    # RAG — 相对路径基于 config.yaml 所在目录解析
    rag_index_dir = (config_path.parent / config.rag.index_dir).resolve()
    rag = RAGAdapter(rag_index_dir, config.rag.embedding_model)

    # VLM（可选）
    vlm_config = config.models.get_vision()
    screenshot = ScreenshotAdapter(
        vlm_config or ModelConfig(),
        monitor=config.screenshot.monitor,
    )
    has_vlm = vlm_config is not None and screenshot.is_available

    # ── 3. 工具 ──
    l1_tools = [SearchWikiTool(rag), GetCurrentTimeTool(), SystemStatsTool()]
    l2_tools = [SearchWikiTool(rag), GetCurrentTimeTool(), SystemStatsTool()]
    if has_vlm:
        capture_tool = CaptureScreenTool(screenshot, prompts)
        l1_tools.append(capture_tool)
        l2_tools.append(capture_tool)

    # L2D 表情控制（可选开关，需模型表情名语义明确）
    if config.l2d.expression_control:
        model_json_path = (config_path.parent.parent / "frontend" / "public" /
                           config.l2d.model_path.lstrip("/")).resolve()
        try:
            expressions = parse_expressions(model_json_path)
            if expressions:
                expression_tool = PlayExpressionTool(bus, expressions)
                l1_tools.append(expression_tool)
                l2_tools.append(expression_tool)
                logger.info(f"  L2D 表情控制: 已加载 {len(expressions)} 个表情 ({', '.join(expressions[:5])}...)")
            else:
                logger.warning("  L2D 表情控制: 模型未包含可用表情")
        except Exception as e:
            logger.warning(f"  L2D 表情控制: 解析失败 ({e})")

    # ── 4. 处理器 ──
    # L1/L2 都用 router 做 ReAct 决策 + reply 做最终回复生成
    l1 = L1Handler(bus, llm_router, llm_reply, context, prompts, l1_tools)
    l2 = L2Handler(bus, llm_router, llm_reply, context, prompts, l2_tools)

    # ── 5. FastAPI ──
    app = create_app(bus, l1, l2,
                     pulse_interval_min=config.pulse.interval_min,
                     pulse_interval_max=config.pulse.interval_max,
                     l2d_model_path=config.l2d.model_path)

    logger.info("=" * 50)
    logger.info("EU4 Game Assistant 启动")
    logger.info(f"  路由模型: {config.models.get_router().model}")
    logger.info(f"  回复模型: {config.models.get_reply().model}")
    logger.info(f"  VLM: {'已配置' if has_vlm else '未配置'}")
    logger.info(f"  RAG: {'已加载' if rag.is_loaded else '未加载'} (共 {len(rag._indexes)} 域)")
    logger.info(f"  脉冲间隔: {config.pulse.interval_min}-{config.pulse.interval_max}s")
    logger.info(f"  上下文保留: {config.context.retention_hours}h")
    logger.info(f"  上下文数据库: {CONTEXT_DB_PATH}")
    logger.info(f"  L2D 模型: {config.l2d.model_path}")
    logger.info(f"  L2D 表情控制: {'已启用' if config.l2d.expression_control else '未启用'}")
    logger.info(f"  WebSocket: ws://localhost:8765/ws")
    logger.info("=" * 50)

    import uvicorn
    server_config = uvicorn.Config(app, host="127.0.0.1", port=8765, log_level="info")
    server = uvicorn.Server(server_config)
    await server.serve()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
