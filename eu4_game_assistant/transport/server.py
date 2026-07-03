"""
FastAPI + WebSocket 服务器
"""
import asyncio
import logging
import random
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from eu4_game_assistant.domain.events import UserInputEvent, DisplayMessageEvent, TickEvent, L2DActionEvent
from eu4_game_assistant.infrastructure.event_bus import EventBus

logger = logging.getLogger(__name__)


def create_app(
    bus: EventBus,
    l1_handler,
    l2_handler,
    pulse_interval_min: int = 30,
    pulse_interval_max: int = 90,
    l2d_model_path: str = "/models/huifeng/model0.json",
) -> FastAPI:
    """创建 FastAPI 应用，装配 WebSocket 和后台任务"""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 订阅事件
        bus.subscribe("user_input", l1_handler.handle)
        bus.subscribe("tick", l2_handler.handle)

        # 脉冲任务
        pulse_task = asyncio.create_task(_pulse_loop(bus, pulse_interval_min, pulse_interval_max))
        logger.info(f"脉冲任务已启动，间隔 {pulse_interval_min}-{pulse_interval_max}s")

        yield

        pulse_task.cancel()
        logger.info("服务器关闭")

    app = FastAPI(lifespan=lifespan)

    # WebSocket 端点
    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        logger.info("WebSocket 客户端已连接")

        # 下发前端配置
        await ws.send_json({
            "type": "config",
            "l2d_model_path": l2d_model_path,
        })

        # 订阅 display_message 事件 → 转发到前端
        async def on_display(msg: DisplayMessageEvent):
            try:
                await ws.send_json({
                    "type": "display_message",
                    "text": msg.text,
                    "is_user": msg.is_user,
                    "is_proactive": msg.is_proactive,
                })
            except Exception:
                pass

        # 订阅 l2d_action 事件 → 转发到前端（AI 表情控制）
        async def on_l2d_action(msg: L2DActionEvent):
            try:
                await ws.send_json({
                    "type": "l2d_action",
                    "action": msg.action,
                    "name": msg.name,
                })
            except Exception:
                pass

        bus.subscribe("display_message", on_display)
        bus.subscribe("l2d_action", on_l2d_action)

        try:
            while True:
                data = await ws.receive_json()
                msg_type = data.get("type", "")

                if msg_type == "user_input":
                    await bus.publish("user_input",
                        UserInputEvent(message=data.get("text", "")))
                elif msg_type == "ping":
                    await ws.send_json({"type": "pong"})

        except WebSocketDisconnect:
            logger.info("WebSocket 客户端断开")
        finally:
            # 无论正常断开还是异常，都清理本连接的订阅，避免泄漏叠加
            bus.unsubscribe("display_message", on_display)
            bus.unsubscribe("l2d_action", on_l2d_action)

    return app


async def _pulse_loop(bus: EventBus, interval_min: int, interval_max: int):
    """脉冲循环 — 启动后立即触发一次，之后随机间隔"""
    first = True
    while True:
        if first:
            first = False
            logger.info("[脉冲] 启动初始化 tick")
        else:
            interval = random.randint(interval_min, interval_max)
            await asyncio.sleep(interval)
        await bus.publish("tick", TickEvent())
