#!/bin/bash
# 查找项目根目录脚本

echo "🔍 查找项目根目录..."
echo ""

# 方法1: 查找包含 docker-compose.yml 的目录
echo "方法1: 查找 docker-compose.yml 文件"
echo "======================================"
find /home -name "docker-compose.yml" -type f 2>/dev/null | head -10
find /opt -name "docker-compose.yml" -type f 2>/dev/null | head -10
find /var -name "docker-compose.yml" -type f 2>/dev/null | head -10
find /root -name "docker-compose.yml" -type f 2>/dev/null | head -10

echo ""
echo "方法2: 查找包含 app/main.py 的目录"
echo "======================================"
find /home -name "main.py" -path "*/app/main.py" -type f 2>/dev/null | head -10
find /opt -name "main.py" -path "*/app/main.py" -type f 2>/dev/null | head -10
find /var -name "main.py" -path "*/app/main.py" -type f 2>/dev/null | head -10
find /root -name "main.py" -path "*/app/main.py" -type f 2>/dev/null | head -10

echo ""
echo "方法3: 查找正在运行的 Docker 容器"
echo "======================================"
if command -v docker &> /dev/null; then
    echo "Docker 容器列表:"
    docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
    
    echo ""
    echo "查找容器挂载的目录:"
    docker ps --format "{{.Names}}" | while read container; do
        if [[ $container == *"app"* ]] || [[ $container == *"risk"* ]]; then
            echo ""
            echo "容器: $container"
            docker inspect $container | grep -A 5 "Mounts" | grep "Source" | head -1
        fi
    done
fi

echo ""
echo "方法4: 查找最近修改的 Python 项目"
echo "======================================"
find /home -name "requirements.txt" -type f -mtime -30 2>/dev/null | head -10
find /opt -name "requirements.txt" -type f -mtime -30 2>/dev/null | head -10

echo ""
echo "======================================"
echo "💡 提示:"
echo "  1. 项目根目录应该包含: docker-compose.yml, app/, requirements.txt"
echo "  2. 如果找到多个，选择最近修改的那个"
echo "  3. 常见位置: /home/用户名/项目名, /opt/项目名, /root/项目名"
echo ""
