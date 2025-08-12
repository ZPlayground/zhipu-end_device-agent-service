# A2A Agent Service - Docker 部署指南

## 🚀 快速启动

### 默认启动（SQLite 版本）
```bash
# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

### PostgreSQL 版本（可选）
```bash
# 使用 PostgreSQL 数据库
docker-compose -f docker-compose.postgres.yml up -d
```

## 📁 配置文件说明

### 主要配置文件
- `docker-compose.yml` - 默认配置（SQLite + Redis）
- `docker-compose.postgres.yml` - PostgreSQL版本配置
- `requirements.txt` - Python依赖文件
- `Dockerfile` - 应用容器构建文件
- `Dockerfile.worker` - Worker容器构建文件

### 服务组件
1. **Redis** - 消息队列，端口 6379
2. **App** - 主应用服务，端口 8000
3. **Worker** - Celery后台任务处理

## 🔧 环境变量

在启动前，你可以设置以下环境变量：

```bash
# LLM API 密钥（可选）
export OPENAI_API_KEY=your-openai-api-key
export ANTHROPIC_API_KEY=your-anthropic-api-key
```

## 📊 服务访问

启动成功后，可以访问：

- **主服务**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health

### 演示账户
- 用户名: `demo`
- 密码: `demo123`

## 🛠️ 常用命令

```bash
# 重新构建服务
docker-compose build

# 重启特定服务
docker-compose restart app

# 查看特定服务日志
docker-compose logs -f app

# 停止所有服务
docker-compose down

# 停止并删除卷
docker-compose down -v

# 进入容器调试
docker-compose exec app sh
```

## 🔄 数据持久化

- **SQLite数据库**: 存储在 `sqlite_data` 卷中
- **Redis数据**: 存储在 `redis_data` 卷中

## 📋 依赖说明

`requirements.txt` 包含了：
- 核心框架（FastAPI, Uvicorn）
- 数据库支持（SQLAlchemy, SQLite, PostgreSQL）
- 消息队列（Celery, Redis）
- LLM集成（OpenAI, Anthropic）
- 认证和安全组件

## ⚠️ 注意事项

1. 首次启动时会自动初始化数据库和创建演示数据
2. SQLite版本适合开发和小规模部署
3. PostgreSQL版本适合生产环境
4. 确保端口8000和6379未被占用
