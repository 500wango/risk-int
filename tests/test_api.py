"""
API 基础测试
"""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.mark.anyio
async def test_health_check():
    """测试 API 是否正常响应"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/source/list")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


@pytest.mark.anyio
async def test_intelligence_list():
    """测试情报列表接口"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/intelligence/list")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


@pytest.mark.anyio
async def test_contract_list():
    """测试合同列表接口"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/contract/list")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


@pytest.mark.anyio
async def test_add_source_validation():
    """测试添加信源参数验证"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 缺少 url 参数应该返回 422
        response = await client.post("/api/intelligence/source")
        assert response.status_code == 422
