# 性能优化计划

## 现状分析

### 当前性能瓶颈
1. **数据库**: 无索引、日志过多、连接池未优化
2. **爬虫**: 浏览器实例重复创建、缺少缓存
3. **AI调用**: 无限流、无重试、无缓存
4. **后台任务**: 无队列管理、任务可能丢失

---

## Phase 1: 快速优化 (1-2天)

### 1.1 数据库优化
**目标**: 查询速度提升 50%+

- [ ] 添加索引
  - `intelligence_items.url` (去重查询)
  - `intelligence_items.source_id` (关联查询)
  - `intelligence_items.created_at` (排序查询)
  - `contract_risks.task_id` (关联查询)

- [ ] 关闭生产环境SQL日志
  ```python
  # session.py
  engine = create_async_engine(
      settings.DATABASE_URL, 
      echo=False,  # 改为 False
      pool_size=20,
      max_overflow=10
  )
  ```

- [ ] 批量查询优化
  - 使用 `selectinload` 预加载关联数据
  - 减少 N+1 查询问题

**预期收益**: 
- 列表查询从 500ms → 100ms
- 去重检查从 200ms → 50ms

---

### 1.2 爬虫优化
**目标**: 爬取速度提升 3x

- [ ] 复用浏览器实例 (已部分实现,需完善)
  ```python
  # 全局浏览器池,避免重复启动
  class BrowserPool:
      _instance = None
      _browser = None
  ```

- [ ] 增加并发数
  ```python
  # endpoints.py
  semaphore = asyncio.Semaphore(5)  # 3 → 5
  ```

- [ ] 添加简单缓存
  ```python
  # 内存缓存已爬取的URL (24小时)
  from cachetools import TTLCache
  url_cache = TTLCache(maxsize=1000, ttl=86400)
  ```

**预期收益**:
- 单个信源处理时间从 2分钟 → 40秒
- 避免重复爬取相同URL

---

### 1.3 AI调用优化
**目标**: 降低延迟和成本

- [ ] 添加重试机制
  ```python
  from tenacity import retry, stop_after_attempt, wait_exponential
  
  @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
  async def call_deepseek(...):
      ...
  ```

- [ ] 并行处理合同chunks
  ```python
  # 当前是串行,改为并行
  results = await asyncio.gather(*[
      ai_engine.analyze_contract_clause(chunk) 
      for chunk in chunks[:3]
  ])
  ```

- [ ] 响应缓存 (可选)
  - 相同内容不重复调用AI

**预期收益**:
- 合同分析从 60秒 → 25秒
- 失败率从 5% → 1%

---

## Phase 2: 架构优化 (3-5天)

### 2.1 任务队列系统
**目标**: 可靠的后台任务处理

**方案选择**:
- **轻量级**: `arq` (基于Redis,Python原生)
- **重量级**: Celery (功能强大但复杂)

**推荐**: arq (适合MVP阶段)

```python
# 添加依赖
# requirements.txt
arq
redis

# 创建 app/worker.py
from arq import create_pool
from arq.connections import RedisSettings

async def process_source_task(ctx, source_id: str, url: str):
    # 原 process_source_background 逻辑
    ...

class WorkerSettings:
    functions = [process_source_task]
    redis_settings = RedisSettings(host='redis', port=6379)
```

**收益**:
- 任务不会丢失
- 支持重试和监控
- 可扩展到多worker

---

### 2.2 缓存层
**目标**: 减少重复计算

```python
# 添加 Redis 缓存
import aioredis

class CacheService:
    async def get_cached_extraction(self, url: str):
        # 缓存AI提取结果
        ...
    
    async def set_cached_extraction(self, url: str, data: dict):
        ...
```

**缓存策略**:
- URL → Markdown: 24小时
- AI提取结果: 7天
- 合同分析结果: 永久 (直到删除)

---

### 2.3 API限流
**目标**: 防止滥用和过载

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/intelligence/source")
@limiter.limit("10/minute")  # 每分钟最多10次
async def add_source(...):
    ...
```

---

## Phase 3: 高级优化 (1-2周)

### 3.1 分布式爬虫
- 多机器并行爬取
- 使用消息队列分发任务

### 3.2 AI批处理
- 合并多个请求到一个batch
- 降低API调用成本

### 3.3 数据库读写分离
- 主库写入,从库查询
- 适合高并发场景

### 3.4 CDN + 静态资源优化
- 前端资源CDN加速
- 图片懒加载

---

## 监控指标

### 关键指标
- 单个信源处理时间: 目标 < 30秒
- API响应时间 P95: 目标 < 500ms
- 数据库查询时间 P95: 目标 < 100ms
- AI调用成功率: 目标 > 99%

### 监控工具
- **日志**: 结构化日志 (JSON格式)
- **指标**: Prometheus + Grafana
- **追踪**: OpenTelemetry (可选)

---

## 成本优化

### AI调用成本
- 使用 DeepSeek Lite 做初筛 (便宜10x)
- 只对高价值内容用 Full 模型
- 缓存重复内容的分析结果

### 基础设施成本
- 使用低内存模式 (LOW_MEMORY_MODE=true)
- 按需启动浏览器实例
- 定期清理过期数据

---

## 实施优先级

### 🔥 立即执行 (本周)
1. 数据库索引
2. 关闭SQL日志
3. AI重试机制
4. 并行处理合同chunks

### ⚡ 短期 (2周内)
1. 任务队列 (arq)
2. Redis缓存
3. API限流
4. 浏览器池优化

### 🎯 中期 (1个月内)
1. 监控系统
2. 成本优化
3. 性能测试和压测

---

## 预期效果

### 性能提升
- 信源处理速度: **3x 提升**
- API响应速度: **2x 提升**
- 数据库查询: **5x 提升**

### 稳定性提升
- 任务成功率: 95% → 99.5%
- 系统可用性: 99% → 99.9%

### 成本优化
- AI调用成本: **降低 40%**
- 服务器资源: **降低 30%**
