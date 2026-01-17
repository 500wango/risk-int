from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# 性能优化: 关闭SQL日志、配置连接池
engine = create_async_engine(
    settings.DATABASE_URL, 
    echo=False,  # 生产环境关闭SQL日志
    pool_size=20,  # 连接池大小
    max_overflow=10,  # 最大溢出连接数
    pool_pre_ping=True,  # 连接健康检查
    pool_recycle=3600  # 1小时回收连接
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
