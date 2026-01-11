# 部署指南

## 服务器要求

- Linux (Ubuntu 20.04+ 推荐) 或 Windows Server
- Python 3.10+
- PostgreSQL 14+
- 2GB+ RAM
- 开放端口: 8000 (API) 或 80/443 (Nginx反代)

## 一、准备工作

### 1. 安装系统依赖 (Ubuntu)

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Python 3.10
sudo apt install python3.10 python3.10-venv python3-pip -y

# 安装 PostgreSQL
sudo apt install postgresql postgresql-contrib -y

# 安装 Playwright 依赖 (用于动态网页爬取)
sudo apt install libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 -y
```

### 2. 配置 PostgreSQL

```bash
# 切换到 postgres 用户
sudo -u postgres psql

# 创建数据库和用户
CREATE DATABASE risk_db;
CREATE USER risk_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE risk_db TO risk_user;
\q
```

## 二、部署应用

### 1. 上传代码

```bash
# 创建应用目录
sudo mkdir -p /opt/risk_intel
cd /opt/risk_intel

# 上传代码 (使用 scp/rsync/git)
# 方式1: scp
scp -r /path/to/local/project/* user@server:/opt/risk_intel/

# 方式2: git (如果有仓库)
git clone https://your-repo-url.git .
```

### 2. 创建虚拟环境

```bash
cd /opt/risk_intel
python3.10 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium
```

### 3. 配置环境变量

```bash
# 创建 .env 文件
cat > .env << 'EOF'
# 数据库
DATABASE_URL=postgresql+asyncpg://risk_user:your_secure_password@localhost:5432/risk_db

# DeepSeek API
DEEPSEEK_API_KEY=your_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
EOF

# 保护配置文件
chmod 600 .env
```

### 4. 测试运行

```bash
source venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

访问 `http://服务器IP:8000` 测试是否正常。

## 三、生产环境配置

### 1. 创建 Systemd 服务

```bash
sudo cat > /etc/systemd/system/risk-intel.service << 'EOF'
[Unit]
Description=Risk Intelligence Platform
After=network.target postgresql.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/risk_intel
Environment="PATH=/opt/risk_intel/venv/bin"
ExecStart=/opt/risk_intel/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 设置目录权限
sudo chown -R www-data:www-data /opt/risk_intel

# 启动服务
sudo systemctl daemon-reload
sudo systemctl enable risk-intel
sudo systemctl start risk-intel

# 查看状态
sudo systemctl status risk-intel
```

### 2. 配置 Nginx 反向代理

```bash
sudo apt install nginx -y

sudo cat > /etc/nginx/sites-available/risk-intel << 'EOF'
server {
    listen 80;
    server_name your-domain.com;  # 替换为你的域名或IP

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    location /static {
        alias /opt/risk_intel/static;
        expires 7d;
    }
}
EOF

# 启用站点
sudo ln -s /etc/nginx/sites-available/risk-intel /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 3. 配置 HTTPS (可选但推荐)

```bash
# 安装 Certbot
sudo apt install certbot python3-certbot-nginx -y

# 获取证书
sudo certbot --nginx -d your-domain.com

# 自动续期
sudo systemctl enable certbot.timer
```

## 四、维护命令

```bash
# 查看日志
sudo journalctl -u risk-intel -f

# 重启服务
sudo systemctl restart risk-intel

# 停止服务
sudo systemctl stop risk-intel

# 更新代码后重启
cd /opt/risk_intel
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart risk-intel
```

## 五、Docker 部署 (可选)

如果服务器支持 Docker，可以使用容器化部署：

```bash
# 构建镜像
docker build -t risk-intel .

# 运行容器
docker run -d \
  --name risk-intel \
  -p 8000:8000 \
  -e DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/risk_db \
  -e DEEPSEEK_API_KEY=your_key \
  -v $(pwd)/config:/app/config \
  risk-intel
```

## 六、常见问题

### 1. Playwright 浏览器启动失败
```bash
# 安装缺失的依赖
sudo apt install -y libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libgbm1
playwright install-deps chromium
```

### 2. 数据库连接失败
```bash
# 检查 PostgreSQL 状态
sudo systemctl status postgresql

# 检查连接
psql -h localhost -U risk_user -d risk_db
```

### 3. 端口被占用
```bash
# 查看端口占用
sudo lsof -i :8000
# 或
sudo netstat -tlnp | grep 8000
```

## 七、备份

```bash
# 备份数据库
pg_dump -U risk_user risk_db > backup_$(date +%Y%m%d).sql

# 恢复数据库
psql -U risk_user risk_db < backup_20260111.sql
```


## 八、CI/CD 自动化部署

项目已配置 GitHub Actions 和 GitLab CI，支持自动化测试和部署。

### GitHub Actions 配置

#### 1. 配置 Secrets

在 GitHub 仓库 Settings → Secrets and variables → Actions 中添加：

| Secret 名称 | 说明 |
|------------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 |
| `SERVER_HOST` | 服务器 IP 或域名 |
| `SERVER_USER` | SSH 用户名 |
| `SERVER_SSH_KEY` | SSH 私钥 |

#### 2. 配置 Variables

在 Settings → Environments → production 中添加：

| Variable 名称 | 说明 |
|--------------|------|
| `DEPLOY_URL` | 部署后的访问地址，如 `https://your-domain.com` |

#### 3. 工作流程

```
push to main → 代码检查 → 运行测试 → 构建镜像 → 推送到 GHCR → SSH 部署到服务器
```

### GitLab CI 配置

#### 1. 配置 CI/CD Variables

在 Settings → CI/CD → Variables 中添加：

| Variable 名称 | 说明 | Protected |
|--------------|------|-----------|
| `STAGING_SSH_KEY` | 测试服务器 SSH 私钥 | ✓ |
| `STAGING_HOST` | 测试服务器地址 | |
| `STAGING_USER` | 测试服务器用户 | |
| `STAGING_URL` | 测试环境 URL | |
| `PROD_SSH_KEY` | 生产服务器 SSH 私钥 | ✓ |
| `PROD_HOST` | 生产服务器地址 | ✓ |
| `PROD_USER` | 生产服务器用户 | ✓ |
| `PROD_URL` | 生产环境 URL | |

#### 2. 工作流程

```
push to main → 代码检查 → 运行测试 → 构建镜像 → 手动部署测试环境 → 手动部署生产环境
```

### 服务器准备

在目标服务器上执行：

```bash
# 1. 安装 Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# 2. 安装 Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 3. 创建应用目录
sudo mkdir -p /opt/risk_intel
sudo chown $USER:$USER /opt/risk_intel

# 4. 创建 docker-compose.yml
cat > /opt/risk_intel/docker-compose.yml << 'EOF'
version: '3.8'
services:
  app:
    image: ghcr.io/your-username/your-repo:latest  # 替换为实际镜像地址
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/risk_db
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
    depends_on:
      - db
    restart: unless-stopped

  db:
    image: postgres:14
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
      - POSTGRES_DB=risk_db
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

volumes:
  postgres_data:
EOF

# 5. 创建环境变量文件
echo "DEEPSEEK_API_KEY=your_api_key" > /opt/risk_intel/.env

# 6. 登录容器仓库 (GitHub)
docker login ghcr.io -u your-username

# 7. 首次启动
cd /opt/risk_intel
docker-compose up -d
```

### 手动触发部署

**GitHub Actions:**
- 推送到 main 分支自动触发
- 或在 Actions 页面手动运行 workflow

**GitLab CI:**
- 推送到 main 分支后，在 CI/CD → Pipelines 中手动点击部署按钮
