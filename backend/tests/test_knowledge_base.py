"""
知识库 API 单测（含多租户隔离 ★ 重点）

验证：
1. 已登录用户能创建 / 列出自己的 KB
2. **多租户隔离**：用户 B 看不到用户 A 的 KB
3. **多租户隔离**：用户 B 不能 GET 用户 A 的 KB 详情（返 404）
4. **多租户隔离**：用户 B 不能 DELETE 用户 A 的 KB
"""
import pytest
from unittest.mock import patch


@pytest.fixture
def mock_vector_store(monkeypatch):
    """Mock 掉 ChromaVectorStore，让 KB 创建不依赖外部 chroma 服务"""
    from app.rag import vector_store as vs_module

    class _StubStore:
        def ensure_collection(self, *a, **kw): pass
        def delete_collection(self, *a, **kw): pass
        def count(self, *a, **kw): return 0
        def list_by_metadata(self, *a, **kw): return []
        def delete_by_metadata(self, *a, **kw): pass
        def add_chunks(self, *a, **kw): pass
        def search(self, *a, **kw): return []

    stub = _StubStore()
    monkeypatch.setattr(vs_module, "_singleton_store", stub)
    monkeypatch.setattr(vs_module, "get_vector_store", lambda: stub)
    return stub


class TestKnowledgeBaseBasic:
    def test_create_and_list_kb(self, authed_client, mock_vector_store):
        """登录后创建 KB，能在列表里看到"""
        resp = authed_client.post(
            "/api/v1/knowledge-bases",
            json={"name": "我的论文库", "description": "测试用"},
        )
        assert resp.status_code in (200, 201)
        kb_id = resp.json()["data"]["id"]
        assert kb_id > 0

        resp = authed_client.get("/api/v1/knowledge-bases")
        assert resp.status_code == 200
        kbs = resp.json()["data"]
        assert len(kbs) == 1
        assert kbs[0]["name"] == "我的论文库"


class TestKnowledgeBaseMultiTenant:
    """多租户隔离：核心安全测试"""

    def test_user_b_cannot_see_user_a_kbs(
        self, authed_client, authed_client_b, mock_vector_store,
    ):
        """A 创建 KB，B 列表里应是空的"""
        # A 创建一个 KB
        resp = authed_client.post(
            "/api/v1/knowledge-bases",
            json={"name": "Alice 的私有 KB"},
        )
        assert resp.status_code in (200, 201)

        # B 列表应为空
        resp = authed_client_b.get("/api/v1/knowledge-bases")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_user_b_cannot_get_user_a_kb_detail(
        self, authed_client, authed_client_b, mock_vector_store,
    ):
        """B 直接访问 A 的 KB ID 应返 404（避免资源枚举）"""
        resp = authed_client.post(
            "/api/v1/knowledge-bases",
            json={"name": "Alice 私有"},
        )
        a_kb_id = resp.json()["data"]["id"]

        resp = authed_client_b.get(f"/api/v1/knowledge-bases/{a_kb_id}")
        assert resp.status_code == 404, "跨用户访问必须返 404 防 ID 枚举"

    def test_user_b_cannot_delete_user_a_kb(
        self, authed_client, authed_client_b, mock_vector_store,
    ):
        """B 不能删除 A 的 KB；删除后 A 仍能看到"""
        resp = authed_client.post(
            "/api/v1/knowledge-bases",
            json={"name": "Alice 不能被删"},
        )
        a_kb_id = resp.json()["data"]["id"]

        # B 尝试删除应失败
        resp = authed_client_b.delete(f"/api/v1/knowledge-bases/{a_kb_id}")
        assert resp.status_code == 404

        # A 仍能看到自己的 KB
        resp = authed_client.get("/api/v1/knowledge-bases")
        assert len(resp.json()["data"]) == 1
