"""
pytest 全局 fixtures

设计：
- 用 SQLite in-memory 替代 PostgreSQL，测试不依赖外部服务
- 每个测试函数有独立的 db session（自动 rollback）
- 提供 client（FastAPI TestClient）+ authed_client（已登录的 client）
"""
import os
import sys
from pathlib import Path

# 让测试能 import 到 app/
sys.path.insert(0, str(Path(__file__).parent.parent))

# 关键：在 import 任何 app 模块之前设置测试环境变量
os.environ["DATABASE_URL"] = "sqlite:///:memory:?cache=shared"
os.environ["JWT_SECRET"] = "test-secret-key-for-pytest-only"
os.environ["DEEPSEEK_API_KEY"] = "sk-test-fake-key"
os.environ["DASHSCOPE_API_KEY"] = "sk-test-fake-key"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["EMBEDDING_PROVIDER"] = "mock"
os.environ["ENV"] = "test"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.models.user import User  # noqa: F401（确保表注册）
from app.models.knowledge_base import KnowledgeBase  # noqa: F401
from app.models.document import Document  # noqa: F401
from app.models.chat import ChatSession, ChatMessage  # noqa: F401
from app.models.task import TaskRecord  # noqa: F401
from app.models.mcp_server import MCPServerConfig  # noqa: F401


# ---------- 数据库 fixture ----------
@pytest.fixture(scope="function")
def db_engine():
    """每个测试函数独立的 in-memory SQLite 引擎"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # 关键：所有 connection 共享同一个内存数据库
    )
    # SQLite 默认不支持外键约束
    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_con, _):
        dbapi_con.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(db_engine):
    """每个测试一个 db session"""
    SessionLocal = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ---------- FastAPI 客户端 fixture ----------
@pytest.fixture(scope="function")
def client(db_engine):
    """注入测试 DB 的 FastAPI TestClient（绕过限流便于测试）"""
    from main import app

    # 覆盖 get_db 依赖
    SessionLocal = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)

    def _override_get_db():
        s = SessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_get_db

    # 关闭 slowapi 限流（测试需要快速连发）
    if hasattr(app.state, "limiter"):
        app.state.limiter.enabled = False

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


# ---------- 已注册/登录用户 fixture ----------
@pytest.fixture
def test_user_credentials():
    return {"username": "alice", "password": "testpass123"}


@pytest.fixture
def test_user_credentials_b():
    return {"username": "bob", "password": "testpass456"}


@pytest.fixture
def authed_client(client, test_user_credentials):
    """已登录的 client（注入 Authorization header）"""
    # 注册
    client.post("/api/v1/auth/register", json=test_user_credentials)
    # 登录拿 token（form-data）
    resp = client.post(
        "/api/v1/auth/login",
        data=test_user_credentials,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200, f"测试登录失败: {resp.text}"
    token = resp.json()["data"]["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest.fixture
def authed_client_b(client, test_user_credentials_b):
    """另一个已登录用户（用于多租户隔离测试）"""
    client.post("/api/v1/auth/register", json=test_user_credentials_b)
    resp = client.post(
        "/api/v1/auth/login",
        data=test_user_credentials_b,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token = resp.json()["data"]["access_token"]
    # 注意：不能直接覆盖 client.headers（与 authed_client 冲突）
    # 这里返回一个简单包装，提供 get/post 等方法时带上 bob 的 token
    class _UserBClient:
        def __init__(self, inner, headers):
            self._c = inner
            self._h = headers

        def _merge(self, kw):
            h = dict(kw.get("headers") or {})
            h.update(self._h)
            kw["headers"] = h
            return kw

        def get(self, url, **kw): return self._c.get(url, **self._merge(kw))
        def post(self, url, **kw): return self._c.post(url, **self._merge(kw))
        def patch(self, url, **kw): return self._c.patch(url, **self._merge(kw))
        def delete(self, url, **kw): return self._c.delete(url, **self._merge(kw))

    return _UserBClient(client, {"Authorization": f"Bearer {token}"})
