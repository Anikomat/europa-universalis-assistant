/**
 * EU4 Game Assistant — Web 前端
 *
 * 架构：
 *   WebSocket ←→ Python 后端 (FastAPI)
 *   PixiJS → L2D 角色渲染
 *   消息驱动：仅当后端推送时显示气泡
 */
import { getCurrentWindow } from "@tauri-apps/api/window";
import { invoke } from "@tauri-apps/api/core";

// ============================================================
//  配置
// ============================================================
const WS_URL = "ws://localhost:8765/ws";
const RECONNECT_DELAY = 3000;
const BUBBLE_TIMEOUT = 12000; // 气泡自动消失时间（ms）
const CHAT_ZONE_RATIO = 0.35;  // 窗口顶部 35% 区域启用穿透
const CLICK_THROUGH_PULSE = 250; // 穿透脉冲间隔（ms），到时短暂恢复事件捕获以检测鼠标位置

// 从后端下发的运行时配置（默认值仅在 WebSocket 未连接时使用）
let l2dModelPath = "/models/huifeng/model0.json";
let _configResolver = null;

// ============================================================
//  DOM 引用
// ============================================================
const chatArea    = document.getElementById("chat-area");
const inputArea   = document.getElementById("input-area");
const inputEl     = document.getElementById("message-input");
const sendBtn     = document.getElementById("send-btn");
const toggleBtn   = document.getElementById("input-toggle-btn");
const collapseBtn = document.getElementById("collapse-btn");
const statusDot   = document.getElementById("status-dot");

// ============================================================
//  Click-through 穿透逻辑
//  — 鼠标在窗口顶部对话区时，点击穿透到后方应用
//  — 鼠标在底部 L2D 区域时，正常捕获点击
//  策略：穿透后通过脉冲定时器短暂恢复事件捕获，以检测鼠标是否已离开穿透区
// ============================================================
let clickThroughActive = false;
let clickThroughTimer = null;

function pulseClickThrough() {
  // 穿透脉冲到期 → 短暂恢复窗口事件捕获
  clickThroughActive = false;
  invoke("set_click_through", { enabled: false }).catch(() => {});
  clickThroughTimer = null;
  // 如果鼠标仍在穿透区，下一次 mousemove 会重新激活穿透
}

function updateClickThrough(clientY) {
  // 输入区展开时不启用穿透
  if (inputArea.classList.contains("expanded")) {
    if (clickThroughActive) {
      clickThroughActive = false;
      if (clickThroughTimer) { clearTimeout(clickThroughTimer); clickThroughTimer = null; }
      invoke("set_click_through", { enabled: false }).catch(() => {});
    }
    return;
  }

  const inChatZone = clientY < window.innerHeight * CHAT_ZONE_RATIO;

  if (inChatZone) {
    if (!clickThroughActive) {
      clickThroughActive = true;
      invoke("set_click_through", { enabled: true }).catch(() => {});
    }
    // 重置脉冲定时器
    if (clickThroughTimer) clearTimeout(clickThroughTimer);
    clickThroughTimer = setTimeout(pulseClickThrough, CLICK_THROUGH_PULSE);
  } else {
    if (clickThroughActive) {
      clickThroughActive = false;
      invoke("set_click_through", { enabled: false }).catch(() => {});
    }
    if (clickThroughTimer) {
      clearTimeout(clickThroughTimer);
      clickThroughTimer = null;
    }
  }
}

// ============================================================
//  窗口定位 — 默认右下角
// ============================================================
async function positionWindow() {
  try {
    const win = getCurrentWindow();
    const monitor = await win.primaryMonitor();
    if (monitor) {
      const w = 420;
      const h = 650;
      await win.setPosition({
        x: monitor.size.width - w - 20,
        y: monitor.size.height - h - 40,
      });
      await win.setSize({ width: w, height: h });
      console.log(`[Window] 定位到右下角 (${monitor.size.width - w - 20}, ${monitor.size.height - h - 40})`);
    }
  } catch (e) {
    console.log("[Window] 非 Tauri 环境，跳过定位");
  }
}

// ============================================================
//  WebSocket
// ============================================================
let ws = null;
let reconnectTimer = null;

function setStatus(state) {
  statusDot.className = state;
  statusDot.title = state === "connected" ? "已连接" : state === "disconnected" ? "连接断开" : "连接中...";
}

function connect() {
  if (ws && ws.readyState === WebSocket.OPEN) return;

  // 每次连接创建新的 config Promise
  _configResolver = null;
  const configPromise = new Promise(resolve => { _configResolver = resolve; });

  setStatus("connecting");
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    console.log("[WS] 已连接");
    setStatus("connected");
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  };

  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      handleServerMessage(msg);
    } catch (e) {
      console.error("[WS] 消息解析失败:", e);
    }
  };

  ws.onclose = () => {
    console.log("[WS] 断开，3s 后重连...");
    setStatus("disconnected");
    ws = null;
    reconnectTimer = setTimeout(connect, RECONNECT_DELAY);
  };

  ws.onerror = (err) => {
    console.error("[WS] 错误:", err);
  };

  return configPromise;
}

// ============================================================
//  消息处理 — 仅显示 assistant 回复
// ============================================================
let bubbleTimer = null;

function handleServerMessage(msg) {
  switch (msg.type) {
    case "config":
      if (msg.l2d_model_path) l2dModelPath = msg.l2d_model_path;
      if (_configResolver) { _configResolver(); _configResolver = null; }
      console.log("[WS] 收到配置:", msg);
      break;

    case "display_message":
      if (!msg.is_user) {
        showBubble(msg.text);
      }
      break;

    case "l2d_action":
      if (msg.action === "expression" && live2dModel) {
        try {
          live2dModel.expression?.(msg.name);
          console.log("[L2D] AI 触发表情:", msg.name);
        } catch (_) {}
      }
      break;

    case "pong":
      break;

    default:
      console.log("[WS] 未知消息类型:", msg.type);
  }
}

// ============================================================
//  气泡渲染 — 始终只保留一条
// ============================================================
function showBubble(text) {
  if (bubbleTimer) clearTimeout(bubbleTimer);

  chatArea.innerHTML = "";

  const bubble = document.createElement("div");
  bubble.className = "chat-bubble";
  bubble.textContent = text;
  chatArea.appendChild(bubble);

  bubbleTimer = setTimeout(() => {
    if (chatArea.firstChild) {
      chatArea.firstChild.remove();
    }
  }, BUBBLE_TIMEOUT);
}

// ============================================================
//  输入区 折叠 / 展开
// ============================================================
function toggleInput() {
  const isCollapsed = inputArea.classList.contains("collapsed");
  if (isCollapsed) {
    expandInput();
  } else {
    collapseInput();
  }
}

function expandInput() {
  inputArea.classList.remove("collapsed");
  inputArea.classList.add("expanded");
  inputEl.focus();
}

function collapseInput() {
  inputArea.classList.remove("expanded");
  inputArea.classList.add("collapsed");
  inputEl.value = "";
  inputEl.blur();
}

// 点击外部 → 收起
document.addEventListener("click", (e) => {
  if (inputArea.classList.contains("expanded")) {
    if (!inputArea.contains(e.target)) {
      collapseInput();
    }
  }
});

// ============================================================
//  发送消息
// ============================================================
function sendMessage() {
  const text = inputEl.value.trim();
  if (!text) return;

  if (!ws || ws.readyState !== WebSocket.OPEN) {
    console.warn("[WS] 未连接，无法发送");
    return;
  }

  ws.send(JSON.stringify({ type: "user_input", text }));

  inputEl.value = "";
  collapseInput();
}

// ============================================================
//  事件绑定
// ============================================================
toggleBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  toggleInput();
});

collapseBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  collapseInput();
});

sendBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  sendMessage();
});

inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    sendMessage();
  }
});

// ============================================================
//  L2D 角色初始化（PixiJS 7 + pixi-live2d-display + Cubism 4）
// ============================================================
let live2dApp = null;
let live2dModel = null;
let live2dContainer = null;
let live2dOrigW = 0;   // 模型原始宽度（不受 scale 影响）
let live2dOrigH = 0;   // 模型原始高度
let resizeRAF = null;

/** 重新计算模型缩放与位置（窗口 resize 时调用，同一帧内防抖） */
function resizeLive2D() {
  if (resizeRAF) return;
  resizeRAF = requestAnimationFrame(() => {
    resizeRAF = null;
    if (!live2dApp || !live2dModel || !live2dContainer) return;
    const w = live2dContainer.clientWidth;
    const h = live2dContainer.clientHeight;
    live2dApp.renderer.resize(w, h);

    const scale = Math.min(
      (w * 0.85) / live2dOrigW,
      (h * 0.9) / live2dOrigH
    );
    live2dModel.scale.set(scale);
    live2dModel.x = w / 2;
    live2dModel.y = h - (live2dOrigH * scale) / 2;  // 锚定窗口底部
  });
}

async function initLive2D(modelPath) {
  try {
    const [PIXI, { Live2DModel }] = await Promise.all([
      import("pixi.js"),
      import("pixi-live2d-display/cubism4"),
    ]);

    window.PIXI = PIXI;

    live2dContainer = document.getElementById("live2d-container");
    const app = new PIXI.Application({
      width: live2dContainer.clientWidth,
      height: live2dContainer.clientHeight,
      backgroundAlpha: 0,
      antialias: true,
      resolution: window.devicePixelRatio || 1,
      autoDensity: true,
    });
    live2dApp = app;
    live2dContainer.appendChild(app.view);

    Live2DModel.registerTicker(app.ticker);

    const model = await Live2DModel.from(modelPath);
    live2dModel = model;
    // 记录原始尺寸（不受 scale 影响），用于 resize 时计算等比缩放
    live2dOrigW = model.internalModel.originalWidth;
    live2dOrigH = model.internalModel.originalHeight;
    model.anchor.set(0.5, 0.5);

    app.stage.addChild(model);
    resizeLive2D();

    // ResizeObserver — 窗口缩放时自动适配，保持角色比例
    const ro = new ResizeObserver(() => resizeLive2D());
    ro.observe(live2dContainer);

    // 鼠标跟随（模型内置 MouseTracking）
    let mouseX = 0, mouseY = 0;
    live2dContainer.addEventListener("mousemove", (e) => {
      const rect = live2dContainer.getBoundingClientRect();
      mouseX = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouseY = ((e.clientY - rect.top) / rect.height) * 2 - 1;
      updateClickThrough(e.clientY);
    });
    live2dContainer.addEventListener("mouseleave", () => {
      mouseX = 0; mouseY = 0;
      if (clickThroughActive) {
        clickThroughActive = false;
        if (clickThroughTimer) { clearTimeout(clickThroughTimer); clickThroughTimer = null; }
        invoke("set_click_through", { enabled: false }).catch(() => {});
      }
    });

    app.ticker.add(() => {
      if (model) model.pointer?.(mouseX, mouseY);
    });

    // 点击换装 — 利用模型的 HitArea 触发不同部位的切换
    live2dContainer.addEventListener("click", (e) => {
      try {
        if (!model) return;
        const rect = live2dContainer.getBoundingClientRect();
        const canvasX = e.clientX - rect.left;
        const canvasY = e.clientY - rect.top;
        model.tap(canvasX, canvasY);
      } catch (_) {}
    });

    window.__live2dReady = true;

    const hint = document.getElementById("live2d-hint");
    if (hint) hint.style.display = "none";
    console.log("[L2D] 灰风已就绪 | 点击不同身体部位可切换造型");

  } catch (e) {
    console.error("[L2D] 初始化失败:", e.message, e.stack);
    const hint = document.getElementById("live2d-hint");
    if (hint) hint.textContent = "L2D 加载失败: " + e.message;
  }
}

// ============================================================
//  启动
// ============================================================
document.addEventListener("DOMContentLoaded", async () => {
  positionWindow();
  // 先连接 WebSocket，等待后端下发配置后再加载 L2D 模型
  const configPromise = connect();
  // 超时保护：3 秒后无论是否收到配置都初始化
  const timeout = new Promise(r => setTimeout(r, 3000));
  await Promise.race([configPromise, timeout]);
  await initLive2D(l2dModelPath);
});

// 心跳
setInterval(() => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "ping" }));
  }
}, 15000);
