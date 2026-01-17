"""
简单的内存缓存服务 (Phase 1)
后续可升级为 Redis
"""
from cachetools import TTLCache
from typing import Optional
import hashlib
import json

class CacheService:
    def __init__(self):
        # URL -> Markdown 缓存 (24小时)
        self.url_cache = TTLCache(maxsize=1000, ttl=86400)
        
        # AI提取结果缓存 (7天)
        self.extraction_cache = TTLCache(maxsize=500, ttl=604800)
    
    def get_url_content(self, url: str) -> Optional[str]:
        """获取缓存的URL内容"""
        return self.url_cache.get(url)
    
    def set_url_content(self, url: str, content: str):
        """缓存URL内容"""
        self.url_cache[url] = content
    
    def get_extraction(self, content_hash: str) -> Optional[dict]:
        """获取缓存的AI提取结果"""
        return self.extraction_cache.get(content_hash)
    
    def set_extraction(self, content_hash: str, data: dict):
        """缓存AI提取结果"""
        self.extraction_cache[content_hash] = data
    
    @staticmethod
    def hash_content(content: str) -> str:
        """生成内容哈希"""
        return hashlib.md5(content.encode()).hexdigest()
    
    def clear_all(self):
        """清空所有缓存"""
        self.url_cache.clear()
        self.extraction_cache.clear()

# 全局单例
cache_service = CacheService()
