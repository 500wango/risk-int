# 生产环境性能优化部署指南 (Linux)

## 📋 部署前检查

### 1. 确认当前环境
```bash
# 检查服务状态
docker-compose ps

# 检查数据库连接
docker-compose exec db psql -U postgres -d risk_db -c "SELECT COUNT(*) FROM intelligence_items;"

# 检查磁盘空间
df -h
```

### 2. 确认备份策略
```bash
# 查看现有数据量
docker-compose exec db psql -U postgres -d risk_db -c "
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables 
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"
```

---

## 🚀 部署步骤

### 方式1: 使用安全部署脚本 (推荐)

```bash
# 1. 给脚本执行权限
chmod +x optimize_safe.sh

# 2. 运行安全部署
./optimize_safe.sh
```

脚本会：
- ✅ 自动备份数据库
- ✅ 安装新依赖
- ✅ 添加索引（不锁表）
- ✅ 询问是否重启（可选）

---

### 方式2: 手动分步部署 (更安全)

#### Step 1: 备份数据库 (强烈推荐)
```bash
# 创建备份目录
mkdir -p backups

# 备份数据库
docker-compose exec -T db pg_dump -U postgres risk_db > backups/backup_$(date +%Y%m%d_%H%M%S).sql

# 验证备份
ls -lh backups/
```

#### Step 2: 安装新依赖 (不影响运行)
```bash
# 进入容器安装依赖
docker-compose exec app pip install cachetools tenacity

# 或者重新构建镜像
docker-compose build app
```

#### Step 3: 添加数据库索引 (在线执行，不锁表)
```bash
# 方式A: 在容器内执行
docker-compose exec app python -m app.db.migrations

# 方式B: 如果有虚拟环境
source venv/bin/activate
python -m app.db.migrations
```

**⏱️ 预计耗时：**
- 数据量 < 1万条：5-10秒
- 数据量 1-10万条：30秒-2分钟
- 数据量 > 10万条：2-5分钟

**💡 注意：** 索引创建期间，查询仍然可以正常执行，只是可能稍慢。

#### Step 4: 更新代码并重启 (可选)
```bash
# 如果需要应用代码优化
docker-compose up -d --no-deps --build app

# 查看重启日志
docker-compose logs -f app
```

---

## 🔍 验证部署

### 1. 检查索引是否创建成功
```bash
docker-compose exec db psql -U postgres -d risk_db -c "
SELECT 
    tablename,
    indexname,
    indexdef
FROM pg_indexes 
WHERE schemaname = 'public' 
AND indexname LIKE 'idx_%'
ORDER BY tablename, indexname;
"
```

应该看到 10 个新索引：
- `idx_intelligence_items_url`
- `idx_intelligence_items_source_id`
- `idx_intelligence_items_created_at`
- `idx_intelligence_items_publish_date`
- `idx_intelligence_sources_status`
- `idx_intelligence_sources_last_crawled`
- `idx_contract_risks_task_id`
- `idx_contract_risks_risk_level`
- `idx_contract_tasks_status`
- `idx_contract_tasks_upload_time`

### 2. 检查服务状态
```bash
# 检查容器状态
docker-compose ps

# 检查应用日志
docker-compose logs --tail=50 app

# 测试API
curl http://localhost:8000/
curl http://localhost:8000/api/intelligence/list
```

### 3. 运行性能测试
```bash
# 在容器内运行
docker-compose exec app python test_performance.py

# 或者本地运行
python test_performance.py
```

---

## 📊 性能对比

### 测试查询性能
```bash
# 优化前后对比
docker-compose exec db psql -U postgres -d risk_db -c "
EXPLAIN ANALYZE 
SELECT * FROM intelligence_items 
WHERE source_id = (SELECT id FROM intelligence_sources LIMIT 1)
ORDER BY created_at DESC 
LIMIT 10;
"
```

查看 `Execution Time`，应该有明显下降。

---

## 🔄 回滚方案

如果出现问题，可以快速回滚：

### 回滚代码
```bash
# 回到之前的版本
git checkout HEAD~1

# 重新构建
docker-compose up -d --build app
```

### 回滚数据库 (如果需要)
```bash
# 恢复备份
docker-compose exec -T db psql -U postgres -d risk_db < backups/backup_YYYYMMDD_HHMMSS.sql
```

### 删除索引 (如果需要)
```bash
docker-compose exec db psql -U postgres -d risk_db -c "
DROP INDEX IF EXISTS idx_intelligence_items_url;
DROP INDEX IF EXISTS idx_intelligence_items_source_id;
DROP INDEX IF EXISTS idx_intelligence_items_created_at;
DROP INDEX IF EXISTS idx_intelligence_items_publish_date;
DROP INDEX IF EXISTS idx_intelligence_sources_status;
DROP INDEX IF EXISTS idx_intelligence_sources_last_crawled;
DROP INDEX IF EXISTS idx_contract_risks_task_id;
DROP INDEX IF EXISTS idx_contract_risks_risk_level;
DROP INDEX IF EXISTS idx_contract_tasks_status;
DROP INDEX IF EXISTS idx_contract_tasks_upload_time;
"
```

---

## ⚠️ 常见问题

### Q1: 索引创建时间过长怎么办？
**A:** 索引创建是在线操作，不会阻塞查询。可以等待完成，或者在低峰期执行。

### Q2: 重启会丢失正在处理的任务吗？
**A:** 
- 已完成的任务：不会丢失（已保存到数据库）
- 正在处理的任务：会中断，需要手动重试
- 建议：在低峰期或确认无任务运行时重启

### Q3: 如何确认优化生效？
**A:** 
```bash
# 查看缓存命中情况（重启后需要预热）
docker-compose logs app | grep "Cache hit"

# 查看查询时间
docker-compose logs app | grep "took"
```

### Q4: 内存使用会增加吗？
**A:** 
- 缓存会占用约 50-100MB 内存
- 索引会占用约 10-50MB 磁盘空间
- 连接池会占用约 20-40MB 内存
- 总体增加不超过 200MB

---

## 🎯 推荐部署时间

### 最佳时间窗口
- 🌙 **凌晨 2-5 点** (用户最少)
- 🌅 **周末早晨** (业务低峰)

### 预计停机时间
- **索引创建**: 0 秒停机（在线操作）
- **依赖安装**: 0 秒停机（不影响运行）
- **服务重启**: 5-10 秒停机

**总计**: 5-10 秒停机（仅在重启时）

---

## 📞 紧急联系

如果部署过程中遇到问题：

1. **立即停止部署**
   ```bash
   # 停止脚本: Ctrl+C
   ```

2. **检查服务状态**
   ```bash
   docker-compose ps
   docker-compose logs --tail=100 app
   ```

3. **回滚到备份**
   ```bash
   # 使用上面的回滚方案
   ```

---

## ✅ 部署检查清单

部署前：
- [ ] 已备份数据库
- [ ] 已确认磁盘空间充足
- [ ] 已通知相关人员
- [ ] 已选择低峰期时间

部署中：
- [ ] 依赖安装成功
- [ ] 索引创建成功
- [ ] 服务重启成功

部署后：
- [ ] 索引验证通过
- [ ] API 测试通过
- [ ] 性能测试通过
- [ ] 日志无异常

---

## 🎉 预期效果

部署成功后，你应该看到：

- ✅ 列表查询速度提升 3-5x
- ✅ 重复URL不再重复爬取
- ✅ AI调用失败率降低
- ✅ 合同分析速度提升 2x+
- ✅ 日志中出现 "Cache hit" 信息

祝部署顺利！🚀
