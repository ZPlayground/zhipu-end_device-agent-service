# 🐳 Docker 快速启动指南

## 前提条件

确保您的系统已安装：
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/Mac)
- Docker Engine (Linux)

## 🚀 一键启动

### Windows 用户

```cmd
# 1. 打开命令提示符或 PowerShell
cd zhipu_end_device_agent_service

# 2. 启动轻量版服务（推荐）
scripts\docker.bat start-lite

# 3. 等待启动完成，然后验证
python scripts\test_deployment.py
```

### Linux/Mac 用户

```bash
# 1. 打开终端
cd zhipu_end_device_agent_service

# 2. 给脚本执行权限
chmod +x scripts/docker.sh

# 3. 启动轻量版服务（推荐）
./scripts/docker.sh start-lite

# 4. 等待启动完成，然后验证
python scripts/test_deployment.py
```

## 📋 启动选项

| 命令 | 说明 | 数据库 | 适用场景 |
|------|------|--------|----------|
| `start-lite` | 轻量版 | SQLite | 快速测试、演示 |
| `start` | 完整版 | PostgreSQL | 生产环境 |
| `start-dev` | 开发版 | PostgreSQL | 开发调试 |

## 🌐 服务地址

启动成功后，您可以访问：

- **主应用**: http://localhost:8000
- **API文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health
- **Flower监控**: http://localhost:5555 (仅完整版)

## 🧪 功能测试

### 1. 健康检查
```bash
curl http://localhost:8000/health
```

### 2. 用户注册
```bash
curl -X POST "http://localhost:8000/api/auth/register" \
     -H "Content-Type: application/json" \
     -d '{"username":"demo","email":"demo@example.com","password":"demo123"}'
```

### 3. 启动终端客户端
```bash
python src/user_interaction/terminal_client.py --server ws://localhost:8000
```

## 🔧 常用命令

```bash
# 查看服务状态
scripts/docker.sh status        # Linux/Mac
scripts\docker.bat status       # Windows

# 查看日志
scripts/docker.sh logs          # 所有服务日志
scripts/docker.sh logs app      # 只看应用日志

# 停止服务
scripts/docker.sh stop

# 重启服务
scripts/docker.sh restart

# 清理环境
scripts/docker.sh clean
```

## 🐛 故障排除

### 端口冲突
如果端口8000被占用，可以在 `docker-compose.yml` 中修改端口映射：
```yaml
ports:
  - "8001:8000"  # 将8000改为8001
```

### 容器启动失败
1. 查看详细日志：
   ```bash
   scripts/docker.sh logs
   ```

2. 检查 Docker 资源：
   ```bash
   docker system df
   docker system prune  # 清理无用资源
   ```

### 数据库连接问题
轻量版使用 SQLite，不需要外部数据库。如果使用完整版，确保 PostgreSQL 容器正常启动：
```bash
docker-compose ps postgres
```

## 💡 开发提示

### 1. 热重载开发
```bash
scripts/docker.sh start-dev
```
代码修改会自动重载，无需重启容器。

### 2. 进入容器调试
```bash
scripts/docker.sh shell
```

### 3. 自定义配置
编辑 `.env` 文件：
```env
OPENAI_API_KEY=your-actual-api-key
ANTHROPIC_API_KEY=your-actual-api-key
DEBUG=True
LOG_LEVEL=DEBUG
```

## 🎯 下一步

1. **体验终端客户端**：
   ```bash
   python src/user_interaction/terminal_client.py
   ```

2. **探索API文档**：
   访问 http://localhost:8000/docs

3. **集成您的Agent**：
   参考 `src/external_services/a2a_service.py`

4. **查看演示**：
   ```bash
   python scripts/demo.py
   ```

享受您的A2A Agent之旅！🚀
