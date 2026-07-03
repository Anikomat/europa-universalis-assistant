# EU4 Game Assistant

面向《欧陆风云 IV》的智能助手系统。基于大语言模型与 ReAct 智能体模式，提供实时战略建议、游戏画面感知与人格化交互。

## 体系结构

```
transport/          FastAPI + WebSocket，前后端通信，事件转发
application/        业务逻辑，L1 对话处理、L2 定时脉冲、ReAct 双 LLM 智能体
tools/              可插拔工具集，Wiki 检索、截图分析、表情控制等
infrastructure/     基础设施，LLM 客户端、EventBus、RAG 向量检索、截图适配器
domain/             领域模型，对话上下文持久化、事件定义
config/             YAML 配置与 Prompt 管理
```

核心流程：用户输入或定时脉冲触发事件，经由 EventBus 分发至 L1/L2 Handler，驱动 ReAct 智能体进行推理-工具调用循环，最终生成回复并通过 WebSocket 推送至前端。

## 环境要求

- Python 3.13+
- Node.js 18+
- Rust（Tauri 2 编译需要）
- CUDA（可选，加速本地 Embedding 模型）

## 快速开始

### 1. 克隆仓库

```bash
git clone <repository-url>
cd eu4-game-assistant
```

### 2. 后端部署

#### 安装依赖

```bash
pip install -r requirements.txt
```

#### 配置文件

在项目根目录创建 `config.yaml`：

```yaml
llm:
  router:
    api_base: "https://api.deepseek.com/v1"
    api_key: "your-api-key"
    model: "deepseek-chat"
  reply:
    api_base: "https://api.deepseek.com/v1"
    api_key: "your-api-key"
    model: "deepseek-chat"
  vision:
    api_base: "https://api.openai.com/v1"
    api_key: "your-api-key"
    model: "gpt-4o"

screenshot:
  monitor: 0        # 显示器编号
  region: [0, 0, 1920, 1080]  # 截图区域 [left, top, width, height]

server:
  host: "127.0.0.1"
  port: 8765
```

#### 构建 RAG 知识库

将 EU4 Wiki 文本数据放入 `data/wiki/` 目录，运行索引构建脚本：

```bash
python scripts/build_rag_index.py
```

索引构建完成后将在 `rag_index/` 目录生成 FAISS 向量文件。

#### 启动服务

```bash
python main_v2.py
```

服务默认运行在 `http://127.0.0.1:8765`，WebSocket 端点 `/ws`。

### 3. 前端部署

#### 安装依赖

```bash
cd frontend
npm install
```

#### 开发模式运行

```bash
npm run tauri dev
```

#### 生产构建

```bash
npm run tauri build
```

## 使用说明

1. 启动后端服务
2. 启动前端 Tauri 应用
3. 前端自动连接后端 WebSocket 服务
4. 在游戏过程中与助手对话或等待定时建议推送

## 项目结构

```
eu4-game-assistant/
├── transport/               # FastAPI + WebSocket 通信层
├── application/             # 业务逻辑层
├── tools/                   # 可插拔工具集
├── infrastructure/          # 基础设施层
├── domain/                  # 领域模型
├── config/                  # 配置与 Prompt
├── data/wiki/               # EU4 Wiki 原始数据
├── rag_index/               # FAISS 向量索引
├── frontend/                # Tauri 前端
├── scripts/                 # 辅助脚本
├── main_v2.py               # 应用入口
├── config.yaml              # 配置文件
└── requirements.txt         # Python 依赖
```

## 常见问题

### 截图无法获取

检查 `config.yaml` 中的 `screenshot.monitor` 和 `screenshot.region` 配置是否正确匹配你的显示器设置。

### API 调用失败

确保 `llm` 配置项中的 `api_key` 有效且网络可访问对应的 API 端点。