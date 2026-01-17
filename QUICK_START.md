# 快速开始 - 服务器部署优化

## 🎯 第一步: 找到项目目录

### 方式1: 使用查找脚本 (推荐)
```bash
# 1. 上传 find_project.sh 到服务器任意位置
# 2. 运行查找脚本
chmod +x find_project.sh
./find_project.sh
```

### 方式2: 手动查找
```bash
# 查找 docker-compose.yml
find /home -name "docker-compose.yml" 2>/dev/null
find /opt -name "docker-compose.yml" 2>/dev/null
find /root -name "docker-compose.yml" 2>/dev/null

# 或者查找正在运行的容器
docker ps
docker inspect <容器名> | grep -i "source"
```

### 方式3: 常见位置
```bash
# 检查这些常见位置
ls -la /home/*/risk*
ls -la /opt/risk*
ls -la /root/risk*
ls -la ~/risk*
```

---

## 🚀 第二步: 上传优化文件

找到项目目录后（假设是 `/opt/risk-system`），上传以下文件：

### 需要上传的文件
```
项目根目录/
├── quick_deploy.sh          # 快速部署脚本
├── optimize_safe.sh         # 安全部署脚本
├── app/
│   ├── db/
│   │   ├── migrations.py    # 新增
│   │   └── session.py       # 已修改
│   ├── services/
│   │   ├── cache_service.py # 新增
│   │   ├── crawler.py       # 已修改
│   │   └── ai_engine.py     # 已修改
│   ├── api/
│   │   └── endpoints.py     # 已修改
│   └── core/
│       └── performance.py   # 新增
├── requirements.txt         # 已修改
└── test_performance.py      # 新增
```

### 上传方式

#### 方式A: 使用 SCP (从本地上传)
```bash
# 假设项目在服务器的 /opt/risk-system
scp quick_deploy.sh user@server:/opt/risk-system/
scp optimize_safe.sh user@server:/opt/risk-system/
scp -r app user@server:/opt/risk-system/
scp requirements.txt user@server:/opt/risk-system/
scp test_performance.py user@server:/opt/risk-system/
```

#### 方式B: 使用 Git (推荐)
```bash
# 在服务器上
cd /opt/risk-system  # 你的项目目录
git pull origin main  # 拉取最新代码
```

#### 方式C: 使用 SFTP 工具
- WinSCP (Windows)
- FileZilla (跨平台)
- Cyberduck (Mac)

---

## ⚡ 第三步: 执行部署

```bash
# 1. 进入项目目录
cd /opt/risk-system  # 替换为你的实际路径

# 2. 确认文件已上传
ls -la quick_deploy.sh

# 3. 给脚本执行权限
chmod +x quick_deploy.sh

# 4. 执行部署
./quick_deploy.sh
```

---

## 📝 完整示例

```bash
# === 示例: 完整部署流程 ===

# 1. SSH 登录服务器
ssh user@your-server-ip

# 2. 查找项目目录
find /home -name "docker-compose.yml" 2>/dev/null

# 假设找到: /home/user/risk-intelligence-system

# 3. 进入项目目录
cd /home/user/risk-intelligence-system

# 4. 确认是正确的项目
ls -la
# 应该看到: docker-compose.yml, app/, requirements.txt 等

# 5. 备份当前代码 (可选)
cp -r app app.backup.$(date +%Y%m%d)

# 6. 上传新文件 (使用 git 或 scp)
git pull  # 如果使用 git

# 7. 执行部署
chmod +x quick_deploy.sh
./quick_deploy.sh

# 8. 查看结果
docker-compose logs -f app
```

---

## 🔍 验证部署

```bash
# 1. 检查服务状态
docker-compose ps

# 2. 检查索引
docker-compose exec db psql -U postgres -d risk_db -c "
SELECT indexname FROM pg_indexes 
WHERE schemaname = 'public' AND indexname LIKE 'idx_%';
"

# 3. 测试 API
curl http://localhost:8000/
curl http://localhost:8000/api/intelligence/list

# 4. 运行性能测试
docker-compose exec app python test_performance.py
```

---

## ❓ 常见问题

### Q1: 找不到项目目录？
```bash
# 查看所有 Docker 容器
docker ps -a

# 查看容器详情
docker inspect <容器名> | grep -i "source"

# 查看 Docker Compose 项目
docker-compose ls  # Docker Compose v2
```

### Q2: 没有 Git？
```bash
# 手动上传文件
# 使用 scp 或 SFTP 工具上传所有修改的文件
```

### Q3: 权限不足？
```bash
# 使用 sudo
sudo ./quick_deploy.sh

# 或切换到 root
sudo su -
cd /path/to/project
./quick_deploy.sh
```

### Q4: 如何只添加索引不重启？
```bash
# 只执行索引创建
docker-compose exec app pip install cachetools tenacity
docker-compose exec app python -m app.db.migrations

# 不执行重启，优化将在下次重启时生效
```

---

## 🆘 需要帮助？

如果遇到问题，收集以下信息：

```bash
# 1. 系统信息
uname -a
docker --version
docker-compose --version

# 2. 项目信息
pwd
ls -la

# 3. 容器状态
docker-compose ps
docker-compose logs --tail=50 app

# 4. 数据库状态
docker-compose exec db psql -U postgres -d risk_db -c "SELECT version();"
```

---

## 📞 联系方式

将上述信息发送给技术支持，以便快速定位问题。
