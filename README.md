# 终端设备 A2A Agent 服务

一个基于 FastAPI 的智能终端设备 A2A (Agent-to-Agent) 协议代理服务，专注于终端设备接入、多模态意图识别和智能任务路由。

[![A2A Protocol](https://img.shields.io/badge/A2A_Protocol-Latest-blue)](https://github.com/modelcontextprotocol/spec)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green)](https://fastapi.tiangolo.com/)
[![WebSocket](https://img.shields.io/badge/WebSocket-Supported-purple)](#websocket-连接管理)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue)](https://www.docker.com/)

## 快速启动

```bash
# 1. 克隆项目
git clone <repository-url> && cd zhipu_end_device_agent_service

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入您的 API 密钥

# 3. 安装依赖
pip install -r requirements.txt

# 4. 初始化数据库
python scripts/init_db.py

# 5. 启动服务
python main.py

# 访问服务
# API文档: http://localhost:8000/docs
# 健康检查: http://localhost:8000/health
# Agent Card: http://localhost:8000/.well-known/agent-card.json
```

## 项目结构

```
├── src/
│   ├── core_application/         # 核心应用逻辑
│   │   ├── terminal_device_manager.py     # 终端设备管理
│   │   ├── event_stream_manager.py        # Redis Streams 数据流管理
│   │   ├── multimodal_llm_agent.py        # 多模态LLM意图识别
│   │   ├── a2a_receiver.py                # A2A协议接收器
│   │   └── a2a_intent_router.py           # A2A智能路由器
│   ├── user_interaction/         # API 接口层
│   │   ├── main_simple.py                 # 主应用和A2A API
│   │   ├── terminal_device_api.py         # 终端设备管理API
│   │   └── agent_registry_api.py          # Agent注册管理API
│   ├── external_services/        # 外部服务集成
│   │   ├── llm_service.py                 # LLM服务(OpenAI/智谱)
│   │   ├── mcp_client.py                  # MCP协议客户端
│   │   ├── zhipu_a2a_server.py           # A2A服务器实现
│   │   └── zhipu_a2a_client.py           # A2A客户端实现
│   ├── async_execution/          # 异步任务处理
│   │   ├── worker_manager.py              # Celery Worker管理
│   │   ├── message_queue.py               # 消息队列路由
│   │   └── tasks.py                       # 异步任务定义
│   ├── data_persistence/         # 数据持久化
│   │   ├── models.py                      # 数据模型
│   │   ├── database.py                    # 数据库连接
│   │   └── repositories.py               # 数据访问层
│   └── config/                   # 配置管理
│       ├── agent_config.py                # Agent配置管理
│       └── agent_card_manager.py          # Agent Card管理
├── config/
│   ├── settings.py              # 应用配置
│   ├── agents.json              # 外部Agent注册表
│   └── agent_card.json          # Agent Card配置
├── docs/                        # 文档
├── scripts/                     # 工具脚本
└── mcp_test_server.py          # MCP测试服务器
```

## 核心特性

### A2A 协议支持
- **官方 A2A SDK 集成**: 基于官方 A2A SDK 完整实现
- **Agent Card 动态生成**: 根据终端设备能力动态生成代理卡
- **JSON-RPC 2.0 通信**: 标准化的代理间通信协议
- **多传输协议支持**: HTTP、WebSocket 传输层
- **外部Agent发现**: 自动发现和管理外部A2A Agent

### 智能终端设备管理
- **设备注册管理**: 支持多种终端设备类型注册和能力管理
- **MCP 工具集成**: 集成 Model Context Protocol 工具调用能力
- **WebSocket 连接管理**: 实时连接状态监控和重连机制
- **多模态数据支持**: 支持文本、图像、音频、视频等多种数据类型
- **设备健康检查**: 自动心跳检测和连接状态管理

### 多模态 LLM 智能路由
- **意图识别引擎**: 基于多模态 LLM 的智能意图分析
- **智能任务路由**: 根据设备能力和任务类型自动路由
- **多LLM支持**: OpenAI GPT 和 智谱 GLM 模型支持
- **意图关键词匹配**: 基于关键词的快速意图识别

### 高性能数据流处理
- **Redis Streams 管理**: 高性能的数据流处理和自动清理
- **大文件混合存储**: 小文件存储在Redis，大文件存储在文件系统
- **异步任务处理**: Celery 支持长时间运行的复杂任务
- **事件流监控**: 实时监控数据流状态和性能指标

## API 接口

### A2A 协议接口
```
POST   /api/a2a                    # A2A消息处理(SendMessage/GetTasks等)
POST   /api/a2a/notifications      # A2A通知接收
GET    /.well-known/agent-card.json # Agent Card获取
```

### 终端设备管理接口
```
POST   /api/terminal-devices/register              # 设备注册
GET    /api/terminal-devices/                      # 获取设备列表
GET    /api/terminal-devices/{device_id}           # 获取设备详情
PUT    /api/terminal-devices/{device_id}           # 更新设备信息
DELETE /api/terminal-devices/{device_id}           # 删除设备
POST   /api/terminal-devices/{device_id}/heartbeat # 设备心跳
```

### MCP 工具调用接口
```
POST   /api/terminal-devices/{device_id}/mcp-call     # 直接调用MCP工具
POST   /api/terminal-devices/mcp-call-by-intent      # 按意图调用MCP工具
GET    /api/terminal-devices/mcp-tools/config        # 获取MCP工具配置
POST   /api/terminal-devices/{device_id}/mcp-test    # 测试MCP连接
```

### Agent 注册管理接口
```
POST   /api/agents/                        # 注册外部Agent
GET    /api/agents/list                    # 获取Agent列表
DELETE /api/agents/{agent_id}              # 删除Agent
PUT    /api/agents/{agent_id}/enable       # 启用Agent
PUT    /api/agents/{agent_id}/disable      # 禁用Agent
GET    /api/agents/summary                 # 获取Agent摘要
```

### 系统监控接口
```
GET    /health                                    # 健康检查
GET    /api/workers/status                        # Worker状态
POST   /api/workers/restart                       # 重启Worker
GET    /api/tasks/{task_id}/status                # 任务状态查询
GET    /api/terminal-devices/websocket/status     # WebSocket状态
GET    /api/terminal-devices/streams/status       # 数据流状态
```

### WebSocket 接口
```
WS     /api/terminal-devices/ws/{device_id}       # 设备WebSocket连接
```

## 配置说明

### 环境变量配置

核心配置 (必需):
```bash
# 数据库
DATABASE_URL=sqlite+aiosqlite:///./data/a2a_agent.db

# Redis (消息队列)
REDIS_URL=redis://localhost:6379

# 安全配置
SECRET_KEY=your-secret-key-here
A2A_WEBHOOK_SECRET=your-webhook-secret-here
```

LLM配置 (可选，启用智能路由):
```bash
# OpenAI
OPENAI_API_KEY=your-openai-api-key

# 智谱 AI
ZHIPU_API_KEY=your-zhipu-api-key
```

Agent配置 (可选，高级配置):
```bash
# Worker配置
AGENT_DEFAULT_WORKER_COUNT=4
AGENT_WORKER_CONCURRENCY=3

# 外部Agent配置
AGENT_AUTOGLM_AGENT_URL=http://your-agent-url
```

## Docker 部署

### 基础部署 (SQLite)
```bash
docker-compose up -d
```

### 生产部署 (PostgreSQL)
```bash
docker-compose -f docker-compose.postgres.yml up -d
```

详细Docker部署说明请参考 [DOCKER.md](DOCKER.md)

## 测试与开发

### 启动MCP测试服务器
```bash
# 启动模拟的MCP设备服务器
python mcp_test_server.py
```

### 运行系统测试
```bash
# 运行完整的系统测试
python examples/comprehensive_system_test_example.py
```

### 数据库管理
```bash
# 初始化数据库(包含演示数据)
python scripts/init_db.py --with-demo-data

# 仅初始化数据库结构
python scripts/init_db.py
```

## 集成示例

### 设备注册示例
```python
import requests

# 注册智能摄像头设备
device_data = {
    "device_id": "camera_001",
    "name": "智能摄像头",
    "device_type": "camera",
    "mcp_server_url": "http://localhost:9001/mcp",
    "description": "办公室智能摄像头",
    "mcp_tools": ["capture_image", "analyze_scene"],
    "intent_keywords": ["拍照", "图像", "场景"]
}

response = requests.post(
    "http://localhost:8000/api/terminal-devices/register",
    json=device_data
)
```

### A2A消息发送示例
```python
# A2A消息格式 (JSON-RPC 2.0)
message = {
    "jsonrpc": "2.0",
    "method": "SendMessage",
    "params": {
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": "请帮我拍一张照片"}]
        }
    },
    "id": "msg_001"
}

response = requests.post(
    "http://localhost:8000/api/a2a",
    json=message
)
```

## 技术栈

### 核心框架
- **FastAPI**: 现代化的 Python Web 框架
- **SQLAlchemy**: ORM 和数据库抽象层
- **Celery**: 分布式任务队列
- **Redis**: 内存数据库和消息代理

### A2A 生态
- **A2A SDK**: 官方 Agent-to-Agent 协议 SDK
- **MCP**: Model Context Protocol 工具调用协议

### AI 服务
- **OpenAI GPT**: 意图识别和智能路由
- **智谱 GLM**: 中文优化的大语言模型

### 数据存储
- **SQLite**: 开发和轻量级部署
- **PostgreSQL**: 生产环境推荐

## 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开 Pull Request

## 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情

## 相关链接

- [A2A Protocol 规范](https://github.com/modelcontextprotocol/spec)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [Celery 文档](https://docs.celeryproject.org/)

## 支持

如有问题或建议，请通过以下方式联系：

- 提交 [Issue](https://github.com/your-repo/issues)
- 查看 [文档](./docs/)
- 参考 [API 文档](http://localhost:8000/docs) (服务运行时)

### 高级连接管理
- **WebSocket 重连机制**: 指数退避算法的自动重连
- **连接状态监控**: 实时连接状态追踪和统计
- **故障恢复**: 自动故障检测和恢复策略
## 系统架构

```
终端设备层 ←→ A2A 代理服务 ←→ 外部 Agent 网络
     ↑             ↑                ↑
  设备管理      智能路由            专业服务
(MCP/WebSocket) (LLM意图识别)    (代码生成/数据分析)
```

### 分层架构

#### 用户交互层 (`src/user_interaction/`)
- **main_simple.py**: FastAPI 应用程序主入口 (1576 行)
- **terminal_device_api.py**: 终端设备注册和管理 API (583 行)
- **websocket_reconnector.py**: WebSocket 重连管理器 (502 行)

#### 核心应用层 (`src/core_application/`)
- **multimodal_llm_agent.py**: 多模态 LLM 意图识别代理 (898 行)
- **terminal_device_manager.py**: 终端设备管理器 (355 行)
- **websocket_data_manager.py**: WebSocket 数据流管理 (416 行)
- **event_stream_manager.py**: Redis Streams 事件流管理器 (414 行) - 新增
- **a2a_intent_router.py**: A2A 意图路由器
- **a2a_receiver.py**: A2A 消息接收处理器

#### 外部服务层 (`src/external_services/`)
- **zhipu_a2a_server.py**: 官方 A2A SDK 服务器实现 (1485 行) - 重构简化
- **llm_service.py**: LLM 服务集成 (OpenAI/ZhipuAI)
- **zhipu_a2a_client.py**: A2A 客户端实现

#### 数据持久层 (`src/data_persistence/`)
- **models.py**: 数据库模型定义
- **repositories.py**: 数据访问仓储模式
- **database.py**: 数据库连接管理

#### 配置管理层 (`config/`)
- **redis_config.py**: Redis Streams 配置管理 (60 行) - 新增
- **settings.py**: 应用全局配置

## A2A 协议支持

### Agent Card (标准发现协议)
```json
{
  "name": "终端设备A2A服务",
  "protocolVersion": "0.3.0",
  "description": "智能终端设备代理服务，支持多设备终端管理与意图路由",
  "url": "http://localhost:8000/api/a2a",
  "preferredTransport": "JSONRPC",
  "additionalInterfaces": [
    {
      "url": "http://localhost:8000/docs",
      "transport": "HTTP"
    },
    {
      "url": "ws://localhost:8000/ws",
      "transport": "WEBSOCKET"
    }
  ],
  "capabilities": {
    "streaming": true,
    "pushNotifications": true,
    "stateTransitionHistory": false
  },
  "skills": [
    {
      "id": "terminal_device_management",
      "name": "终端设备管理",
      "description": "管理终端设备，支持多种设备类型和MCP工具调用",
      "tags": ["terminal", "device", "mcp", "management"]
    },
    {
      "id": "intelligent_intent_routing",
      "name": "智能意图路由",
      "description": "使用大语言模型进行智能意图识别和任务路由"
    }
  ]
}
```

### JSON-RPC 2.0 通信示例
```json
{
  "jsonrpc": "2.0",
  "method": "message/send",
  "params": {
    "message": {
      "messageId": "uuid-001",
      "parts": [{"kind": "text", "text": "你好，请帮我分析数据"}],
      "kind": "message"
    }
  },
  "id": "request-001"
}
```

## 技术栈

- **Web 框架**: FastAPI + Uvicorn ASGI
- **A2A 协议**: 官方 A2A SDK 0.2.6
- **数据流管理**: Redis Streams + 混合文件存储
- **数据库**: SQLite/PostgreSQL + SQLAlchemy ORM
- **LLM 集成**: OpenAI API, ZhipuAI (zai-sdk)
- **实时通信**: WebSocket + 自动重连机制
- **异步处理**: asyncio + Redis Streams
- **容器化**: Docker + Docker Compose

## 快速启动

### 使用 Docker Compose (推荐)

```bash
# 克隆项目
git clone <repository-url>
cd zhipu_end_device_agent_service

# 启动 SQLite 版本
docker-compose -f docker-compose.sqlite.yml up -d

# 或启动完整 PostgreSQL 版本
docker-compose up -d

# 查看运行状态
docker-compose ps
```

### 本地开发部署

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件设置 API 密钥

# 初始化数据库
python scripts/init_db.py

# 启动服务
python main.py
```

## 服务端点

启动后可通过以下地址访问：

- **主服务**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health
- **A2A Agent Card**: http://localhost:8000/.well-known/agent.json
- **WebSocket 端点**: ws://localhost:8000/ws/terminal

## 环境配置

### 核心配置项

```bash
# LLM 服务配置
OPENAI_API_KEY=your_openai_key
ZHIPU_API_KEY=your_zhipu_key

# 数据库配置
DATABASE_URL=sqlite:///data/app.db
# 或 PostgreSQL: postgresql://user:pass@localhost/dbname

# Redis 配置 (数据流管理)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your_redis_password  # 可选
REDIS_MAX_SIZE_MB=1  # 文件存储阈值

# 文件存储配置
FILE_STORAGE_DIR=data/device_files  # 大文件存储目录
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
REDIS_MAX_SIZE_MB=1
FILE_STORAGE_DIR=data/device_files
REDIS_DATA_RETENTION_HOURS=24

# A2A 服务配置
A2A_SERVER_URL=http://localhost:8000/api/a2a
A2A_AGENT_NAME=zhipu-terminal-agent

# 服务器配置
HOST=0.0.0.0
PORT=8000
```
- `GET /api/messages` - 获取消息历史
- `GET /api/messages/sync` - 增量消息同步
- `POST /api/messages/{message_id}/read` - 标记消息为已读
- `GET /api/messages/inbox` - 获取收件箱消息

**WebSocket端点：**
- `WS /ws/{user_id}` - WebSocket实时通信连接

**系统监控：**
- `GET /health` - 健康检查
- `GET /` - 服务根路径

### A2A终端客户端（推荐）

使用符合A2A协议标准的终端客户端进行交互：

```bash
# 启动A2A协议客户端
python examples/enhanced_terminal_client.py --server http://localhost:8000

# 可用命令:
/help      - 显示帮助信息
/card      - 获取Agent Card（代理能力信息）
/send      - 发送消息到A2A代理
/devices   - 列出已注册的终端设备
/status    - 查看服务状态
/quit      - 退出客户端
```

### 数据流管理 (Redis Streams)

服务使用Redis Streams进行数据流管理，支持混合存储策略：

```python
# 查看设备数据流信息
GET /api/streams/{device_id}/info

# 添加数据到流（支持文件上传）
POST /api/streams/{device_id}/data
Content-Type: multipart/form-data

# 存储策略：
# - 小文件(≤1MB): 存储在Redis Stream
# - 大文件(>1MB): 存储在文件系统 data/device_files/
```

## 使用指南

### 终端设备注册

```bash
# 注册终端设备
curl -X POST http://localhost:8000/api/terminal/devices/register \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "terminal-001",
    "name": "开发终端",
    "device_type": "desktop",
    "mcp_server_url": "http://localhost:3000",
    "mcp_capabilities": ["file_operations", "code_execution"],
    "websocket_endpoint": "ws://localhost:3001/ws"
  }'
```

### A2A协议通信示例

```bash
# 获取Agent Card
curl http://localhost:8000/.well-known/agent-card.json

# JSON-RPC 2.0 消息发送
curl -X POST http://localhost:8000/api/a2a \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"type": "text", "text": "请帮我分析数据"}],
        "messageId": "uuid-001",
        "kind": "message"
      }
    },
    "id": "request-001"
  }'

# 查询任务状态
curl -X POST http://localhost:8000/api/a2a \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0", 
    "method": "tasks/get",
    "params": {"id": "task-uuid-123"},
    "id": "request-002"
  }'
```

### 数据流和文件管理

```bash
# 查看设备数据流信息
curl http://localhost:8000/api/streams/terminal-001/info

# 上传文件到设备流 (大文件会自动存储到文件系统)
curl -X POST http://localhost:8000/api/streams/terminal-001/data \
  -F "content_binary=@large_file.mp4" \
  -F "metadata={\"type\":\"video\",\"description\":\"演示视频\"}"

# 发送文本数据到流
curl -X POST http://localhost:8000/api/streams/terminal-001/data \
  -H "Content-Type: application/json" \
  -d '{
    "content_text": "设备状态正常", 
    "metadata": {"type": "status", "priority": "normal"}
  }'
```

### WebSocket 终端连接

```javascript
// JavaScript 终端设备客户端示例
const ws = new WebSocket('ws://localhost:8000/ws/terminal/terminal-001');

ws.onopen = () => {
    console.log('终端WebSocket连接已建立');
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('收到终端数据:', data);
};

// 发送终端设备数据
ws.send(JSON.stringify({
    type: 'data',
    device_id: 'terminal-001',
    data_type: 'sensor',
    content: {'temperature': 25.6, 'humidity': 60},
    timestamp: new Date().toISOString()
}));
```

### A2A 协议客户端

```bash
# 启动 A2A 协议客户端
python examples/enhanced_terminal_client.py --server http://localhost:8000

# 可用命令:
/help      - 显示帮助信息
/card      - 获取 Agent Card
/send      - 发送消息到A2A代理
/devices   - 列出终端设备
/status    - 查看服务状态
/quit      - 退出客户端
## 智能路由机制

### 意图识别流程
```
用户输入 → 多模态LLM分析 → 设备能力匹配 → 路由决策
    ↓
本地处理 ← 基础查询 (confidence < 0.5)
    ↓
外部 Agent ← 专业任务 → 异步处理 → 状态跟踪
```

### 支持的任务类型
- **代码生成**: 自动路由到代码生成 Agent
- **数据分析**: 连接数据分析专家 Agent
- **文件处理**: 文档和文件操作 Agent
- **时间查询**: 调用时间服务 Agent
- **MCP 工具调用**: 调用终端设备的 MCP 工具
- **基础对话**: 本地 LLM 直接处理

## 测试与验证

```bash
# 运行综合系统测试（已移至根目录）
python comprehensive_system_test_example.py

# 启动MCP测试服务器
python mcp_test_server.py

# 服务健康检查（通过API）
curl http://localhost:8000/health
```

## Docker 部署选项

### 开发环境
```bash
# SQLite 轻量版
docker-compose -f docker-compose.sqlite.yml up -d

# 开发版本 (PostgreSQL)
docker-compose -f docker-compose.dev.yml up -d
```

### 生产环境
```bash
# 完整生产部署
docker-compose up -d

# 查看服务状态和日志
docker-compose ps
docker-compose logs -f app
```
## 相关文档

- [A2A 协议规范](docs/a2a_protocol.md) - 完整的 A2A 协议说明
- [终端设备使用指南](docs/TERMINAL_DEVICE_USAGE_GUIDE.md) - 详细接入指南
- [WebSocket 重连指南](WEBSOCKET_RECONNECTION_GUIDE.md) - 连接管理说明
- [详细使用场景](docs/DETAILED_USAGE_SCENARIOS.md) - 各种使用场景示例

## 开发指南

### 添加新的终端设备类型
1. 在 `src/data_persistence/models.py` 中扩展设备模型
2. 更新 `src/core_application/terminal_device_manager.py` 管理逻辑
3. 在 `src/user_interaction/terminal_device_api.py` 中添加 API 支持

### 扩展 LLM 意图识别
1. 修改 `src/core_application/multimodal_llm_agent.py` 中的提示词
2. 更新意图分类逻辑
3. 添加新的路由规则

### 集成新的 Agent
1. 在 `src/config/agent_registry.py` 中注册 Agent
2. 更新 `src/core_application/a2a_intent_router.py` 路由逻辑
3. 添加相应的测试用例

## 故障排查

### 常见问题解决

**服务启动失败**
```bash
# 检查端口占用
netstat -tulpn | grep 8000

# 查看详细启动日志
python main.py --log-level debug
```

**WebSocket 连接问题**
```bash
# 测试 WebSocket 连接
python examples/terminal_client.py

# 检查重连统计
curl http://localhost:8000/api/websocket/stats
```

**A2A 协议问题**
```bash
# 验证 Agent Card
curl http://localhost:8000/.well-known/agent.json

# 测试 A2A 端点
python examples/a2a_sdk_test_client.py
```

## 性能优化

### 批量处理优化
- EventStream 数据缓存
- Agent 能力信息缓存
- 批量 LLM 调用减少延迟

### 连接管理优化
- WebSocket 连接池
- 指数退避重连算法
- 连接状态监控和统计

## 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

## 技术支持

- **详细文档**: 查看 `docs/` 目录下的完整文档
  - [API参考文档](docs/API_REFERENCE.md) - 完整的API端点和使用示例
  - [A2A SDK客户端指南](A2A_SDK_CLIENT_GUIDE.md) - A2A协议集成指南
  - [终端代理使用指南](TERMINAL_AGENT_GUIDE.md) - 终端设备管理
  - [详细使用场景](docs/DETAILED_USAGE_SCENARIOS.md) - 典型应用场景
  - [终端设备使用指南](docs/TERMINAL_DEVICE_USAGE_GUIDE.md) - 设备接入指南
- **在线文档**: 访问 http://localhost:8000/docs 查看交互式API文档
- **Issues**: 使用 GitHub Issues 报告问题
- **健康检查**: 访问 http://localhost:8000/health

---

**终端设备 A2A Agent 服务** - 让智能终端设备无缝接入 Agent 网络。
    
    async def route_intent(self, message: str) -> str:
        # 添加新任务的路由逻辑
        if self.match_intent(message, "your_new_task"):
            return "your_new_task"
        # ... 其他逻辑
```

2. **在任务处理器中实现任务逻辑：**

```python
# src/async_execution/tasks.py
@celery.task
def process_your_new_task(message_data: dict):
    """处理新任务类型"""
    try:
        # 实现新任务的处理逻辑
        result = handle_new_task_logic(message_data)
        return {
            "status": "success",
            "result": result,
            "task_type": "your_new_task"
        }
    except Exception as e:
        logger.error(f"New task processing failed: {e}")
        return {"status": "error", "error": str(e)}
```

3. **注册新的A2A Agent（如需要）：**

```python
# 在external_services中注册专门处理新任务的Agent
from src.external_services import A2AAgentService

a2a_service = A2AAgentService()
a2a_service.register_agent(
    name="new-task-agent",
    endpoint_url="http://localhost:8003",
    capabilities=["your_new_task"],
    skills=[{"id": "new_task", "name": "新任务处理"}]
)
```

### 扩展LLM支持

1. **继承LLM提供者基类：**

```python
# src/external_services/llm_service.py
class CustomLLMProvider(LLMProvider):
    def __init__(self, api_key: str, base_url: str = None):
        self.api_key = api_key
        self.base_url = base_url
        
    async def generate_response(self, prompt: str, **kwargs) -> str:
        """实现自定义LLM的响应生成"""
        # 调用您的自定义LLM API
        response = await self.call_custom_llm_api(prompt, **kwargs)
        return response.text
        
    async def analyze_intent(self, message: str) -> str:
        """实现意图分析"""
        prompt = f"分析以下消息的意图: {message}"
        response = await self.generate_response(prompt)
        return self.extract_intent(response)
```

2. **在LLM服务中注册新提供者：**

```python
# 在LLMService类中添加新提供者
class LLMService:
    def __init__(self):
        self.providers = {}
        self.register_provider("openai", OpenAIProvider())
        self.register_provider("custom", CustomLLMProvider())  # 注册新提供者
        
    def register_provider(self, name: str, provider: LLMProvider):
        self.providers[name] = provider
```

### A2A Agent开发示例

#### 创建新的A2A Agent服务

```python
# examples/custom_a2a_agent.py
from fastapi import FastAPI
from src.external_services.zhipu_a2a_server import A2AProtocol

app = FastAPI()

@app.get("/.well-known/agent.json")
async def get_agent_card():
    return {
        "name": "自定义A2A Agent",
        "protocolVersion": "0.2.6",
        "description": "专门处理特定任务的A2A Agent",
        "skills": [
            {
                "id": "custom_processing",
                "name": "自定义处理",
                "description": "处理特定领域的任务"
            }
        ],
        "capabilities": {
            "streaming": True,
            "stateTransitionHistory": True
        }
    }

@app.post("/api/a2a")
async def handle_a2a_request(request_data: dict):
    """处理A2A协议请求"""
    if not A2AProtocol.validate_request(request_data):
        return A2AProtocol.create_error_response(
            request_data.get("id"), -32600, "Invalid Request"
        )
    
    method = request_data["method"]
    params = request_data["params"]
    request_id = request_data["id"]
    
    if method == "message/send":
        # 处理消息发送
        message = params["message"]
        result = await process_custom_message(message)
        
        return A2AProtocol.create_response(
            request_id=request_id,
            result=result
        )
    
    return A2AProtocol.create_error_response(
        request_id, -32601, f"Method not found: {method}"
    )

async def process_custom_message(message: dict) -> dict:
    """自定义消息处理逻辑"""
    text = message["parts"][0]["text"]
    
    # 实现您的处理逻辑
    response_text = f"处理结果: {text}"
    
    return {
        "messageId": message["messageId"] + "-response",
        "parts": [{"kind": "text", "text": response_text}],
        "kind": "message"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
```

#### 注册和发现Agent

```python
# examples/agent_registration_example.py
import requests
import asyncio
from src.external_services.zhipu_a2a_client import ZhipuA2AClient

async def register_agent_example():
    """Agent注册示例"""
    
    # 1. 注册新的终端Agent
    agent_data = {
        "name": "测试Agent",
        "agent_type": "terminal_device",
        "capabilities": ["data_processing", "file_analysis"],
        "endpoint_url": "http://localhost:8003",
        "metadata": {
            "version": "1.0.0",
            "description": "用于测试的Agent"
        }
    }
    
    response = requests.post(
        "http://localhost:8000/api/terminal-agents/register",
        json=agent_data
    )
    
    if response.status_code == 200:
        agent_info = response.json()
        print(f"Agent注册成功: {agent_info}")
        
        # 2. 发送心跳
        agent_id = agent_info["id"]
        heartbeat_response = requests.post(
            f"http://localhost:8000/api/terminal-agents/{agent_id}/heartbeat"
        )
        print(f"心跳响应: {heartbeat_response.json()}")
        
        # 3. 通过A2A客户端发送消息
        client = ZhipuA2AClient("http://localhost:8000/api/a2a")
        
        message = {
            "messageId": "test-001",
            "parts": [{"kind": "text", "text": "Hello from registered agent!"}],
            "kind": "message"
        }
        
        result = await client.send_message(message)
        print(f"A2A消息结果: {result}")

if __name__ == "__main__":
    asyncio.run(register_agent_example())
```

## 监控和运维

### 服务状态检查

```bash
# 检查服务健康状态
curl http://localhost:8000/health
# 响应: {"status":"healthy","timestamp":"2025-07-30T06:08:27.428893","services":{"database":"connected","llm":"available","a2a_sdk":"available"}}

# 访问完整API文档
http://localhost:8000/docs

# 获取Agent能力信息
curl http://localhost:8000/.well-known/agent.json

# 运行综合健康检查
python system_health_check.py
```

### 日志管理

日志级别可在 `.env` 文件中配置：
```env
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
```

查看日志：
```bash
# 查看应用日志
tail -f logs/app.log

# 查看Worker日志
tail -f logs/worker.log

# Docker环境查看日志
docker-compose logs -f app
docker-compose logs -f worker
```

### 数据库备份

```bash
# PostgreSQL备份
pg_dump a2a_agent_db > backup_$(date +%Y%m%d).sql

# 恢复数据库
psql a2a_agent_db < backup_20250730.sql

# SQLite备份
cp a2a_agent.db backup/a2a_agent_$(date +%Y%m%d).db
```

### 性能监控

```bash
# 监控Redis状态
redis-cli info stats

# 监控数据库连接
SELECT count(*) FROM pg_stat_activity WHERE state = 'active';

# 监控API响应时间
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:8000/health
```

## 路线图

### 已完成功能
- [x] **A2A协议v0.2.6完整支持** - JSON-RPC 2.0、Agent Card、任务生命周期
- [x] **实时双向通信** - WebSocket长连接、消息推送、连接管理
- [x] **消息收件箱数据库** - 持久化存储、读取状态、元数据管理
- [x] **断线重连消息同步** - 增量同步、离线恢复、时间戳精确查询
- [x] **终端设备管理** - Agent注册、发现、状态监控、生命周期管理
- [x] **智能意图识别与路由** - 基于LLM的智能消息处理和任务分发
- [x] **5层架构设计** - 用户交互、核心应用、异步执行、数据持久、外部服务
- [x] **标准化API文档** - Swagger/OpenAPI 3.1规范、交互式文档
- [x] **多Agent协调** - 复杂任务编排和工作流支持
- [x] **错误处理与验证** - 符合JSON-RPC 2.0标准的错误处理
- [x] **Docker容器化部署** - 开发、测试、生产环境支持
- [x] **健康检查系统** - 100%测试覆盖、性能监控

### 计划中功能
- [ ] **Agent负载均衡** - 智能任务分发、故障转移、性能优化
- [ ] **Web管理界面** - Agent管理、监控面板、配置界面
- [ ] **自动Agent发现** - 网络扫描、服务注册、动态路由
- [ ] **分布式多节点** - 集群部署、数据同步、高可用架构
- [ ] **实时监控面板** - Grafana集成、性能指标、告警系统
- [ ] **工作流可视化** - Agent间协作流程图、任务依赖管理
- [ ] **安全增强** - OAuth2.0、JWT认证、API密钥管理
- [ ] **消息加密** - 端到端加密、数字签名、安全传输
- [ ] **插件系统** - 动态加载、热更新、第三方扩展

### 远期规划
- [ ] **AI驱动的Agent编排** - 自动工作流生成、智能任务优化
- [ ] **边缘计算支持** - IoT设备集成、边缘节点部署
- [ ] **多语言SDK** - Java、Go、Rust、JavaScript客户端
- [ ] **区块链集成** - 去中心化Agent注册、智能合约执行
- [ ] **联邦学习支持** - 分布式模型训练、隐私保护计算

## 适用场景

- **IoT设备管理**: 智能设备的统一管理和协调
- **多Agent系统**: 复杂AI Agent生态系统的协调中心
- **实时通信应用**: 需要低延迟双向通信的应用
- **消息中心**: 可靠的消息持久化和同步服务
- **企业AI协作**: 多个AI Agent协同工作的企业应用

## 技术创新点

- **智能意图路由**: 基于LLM的智能消息路由和处理
- **断线重连同步**: 基于时间戳的精确消息同步机制
- **A2A协议集成**: 与标准A2A生态系统的无缝对接
- **实时+持久化**: 实时通信与数据持久化的完美结合

## 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 技术支持

如有问题或建议，请通过以下方式联系：
- 创建 GitHub Issue
- 发送邮件至技术支持团队

---

**智谱实习生项目 - A2A Agent Service Framework**
*基于A2A协议v0.2.6的智能终端设备协调中心*
*系统状态: 健康 (100%测试通过) | 生成时间: 2025-07-30*
