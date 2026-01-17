"""
性能监控工具
"""
import time
import functools
import logging
from typing import Callable

logger = logging.getLogger(__name__)

def measure_time(func_name: str = None):
    """装饰器: 测量函数执行时间"""
    def decorator(func: Callable):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            name = func_name or func.__name__
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start
                logger.info(f"⏱️ {name} took {elapsed:.2f}s")
                return result
            except Exception as e:
                elapsed = time.time() - start
                logger.error(f"❌ {name} failed after {elapsed:.2f}s: {e}")
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            name = func_name or func.__name__
            start = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start
                logger.info(f"⏱️ {name} took {elapsed:.2f}s")
                return result
            except Exception as e:
                elapsed = time.time() - start
                logger.error(f"❌ {name} failed after {elapsed:.2f}s: {e}")
                raise
        
        # 判断是否是异步函数
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


class PerformanceStats:
    """性能统计"""
    def __init__(self):
        self.stats = {
            "crawl_count": 0,
            "crawl_total_time": 0.0,
            "ai_call_count": 0,
            "ai_total_time": 0.0,
            "cache_hits": 0,
            "cache_misses": 0,
        }
    
    def record_crawl(self, duration: float):
        self.stats["crawl_count"] += 1
        self.stats["crawl_total_time"] += duration
    
    def record_ai_call(self, duration: float):
        self.stats["ai_call_count"] += 1
        self.stats["ai_total_time"] += duration
    
    def record_cache_hit(self):
        self.stats["cache_hits"] += 1
    
    def record_cache_miss(self):
        self.stats["cache_misses"] += 1
    
    def get_summary(self) -> dict:
        """获取性能摘要"""
        crawl_avg = (
            self.stats["crawl_total_time"] / self.stats["crawl_count"]
            if self.stats["crawl_count"] > 0 else 0
        )
        ai_avg = (
            self.stats["ai_total_time"] / self.stats["ai_call_count"]
            if self.stats["ai_call_count"] > 0 else 0
        )
        cache_hit_rate = (
            self.stats["cache_hits"] / (self.stats["cache_hits"] + self.stats["cache_misses"])
            if (self.stats["cache_hits"] + self.stats["cache_misses"]) > 0 else 0
        )
        
        return {
            "crawl": {
                "count": self.stats["crawl_count"],
                "total_time": round(self.stats["crawl_total_time"], 2),
                "avg_time": round(crawl_avg, 2),
            },
            "ai": {
                "count": self.stats["ai_call_count"],
                "total_time": round(self.stats["ai_total_time"], 2),
                "avg_time": round(ai_avg, 2),
            },
            "cache": {
                "hits": self.stats["cache_hits"],
                "misses": self.stats["cache_misses"],
                "hit_rate": round(cache_hit_rate * 100, 2),
            }
        }
    
    def reset(self):
        """重置统计"""
        self.stats = {
            "crawl_count": 0,
            "crawl_total_time": 0.0,
            "ai_call_count": 0,
            "ai_total_time": 0.0,
            "cache_hits": 0,
            "cache_misses": 0,
        }

# 全局统计实例
perf_stats = PerformanceStats()
