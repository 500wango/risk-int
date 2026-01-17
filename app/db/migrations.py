"""
数据库索引优化脚本
运行: python -m app.db.migrations
"""
from sqlalchemy import text
from app.db.session import engine
import asyncio

async def add_indexes():
    """添加性能优化索引"""
    indexes = [
        # intelligence_items 表索引
        "CREATE INDEX IF NOT EXISTS idx_intelligence_items_url ON intelligence_items(url);",
        "CREATE INDEX IF NOT EXISTS idx_intelligence_items_source_id ON intelligence_items(source_id);",
        "CREATE INDEX IF NOT EXISTS idx_intelligence_items_created_at ON intelligence_items(created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_intelligence_items_publish_date ON intelligence_items(publish_date);",
        
        # intelligence_sources 表索引
        "CREATE INDEX IF NOT EXISTS idx_intelligence_sources_status ON intelligence_sources(status);",
        "CREATE INDEX IF NOT EXISTS idx_intelligence_sources_last_crawled ON intelligence_sources(last_crawled_at);",
        
        # contract_risks 表索引
        "CREATE INDEX IF NOT EXISTS idx_contract_risks_task_id ON contract_risks(task_id);",
        "CREATE INDEX IF NOT EXISTS idx_contract_risks_risk_level ON contract_risks(risk_level);",
        
        # contract_tasks 表索引
        "CREATE INDEX IF NOT EXISTS idx_contract_tasks_status ON contract_tasks(status);",
        "CREATE INDEX IF NOT EXISTS idx_contract_tasks_upload_time ON contract_tasks(upload_time DESC);",
    ]
    
    async with engine.begin() as conn:
        for idx_sql in indexes:
            print(f"Creating index: {idx_sql}")
            await conn.execute(text(idx_sql))
    
    print("✅ All indexes created successfully!")

if __name__ == "__main__":
    asyncio.run(add_indexes())
