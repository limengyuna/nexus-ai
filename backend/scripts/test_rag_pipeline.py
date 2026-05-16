"""
阶段二 RAG 管道端到端测试脚本

流程：
1. 登录获取 JWT
2. 创建知识库
3. 上传文档（用项目根目录的 README.md 当测试样本）
4. 轮询任务进度直到 SUCCESS
5. RAG 检索验证召回效果
6. 清理：删除测试知识库

用法（在 backend/ 目录下）::

    .\.venv\Scripts\python.exe scripts\test_rag_pipeline.py
"""
import sys
import time
from pathlib import Path

import requests

# 后端地址
BASE_URL = "http://localhost:8002/api/v1"

# 登录账号（与之前注册的一致）
USERNAME = "admin"
PASSWORD = "admin123"

# 测试用的文档路径：项目根的 plan.md（中文内容丰富，便于验证检索）
TEST_DOC_PATH = Path(__file__).parent.parent.parent / "plan.md"


def section(title: str):
    print(f"\n{'=' * 60}\n>>> {title}\n{'=' * 60}")


def main():
    if not TEST_DOC_PATH.exists():
        print(f"测试文档不存在: {TEST_DOC_PATH}")
        sys.exit(1)

    # ---------- 1. 登录 ----------
    section("1. 登录获取 Token")
    resp = requests.post(
        f"{BASE_URL}/auth/login",
        data={"username": USERNAME, "password": PASSWORD},
    )
    resp.raise_for_status()
    token = resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"✓ Token 获取成功（长度 {len(token)}）")

    # ---------- 2. 创建知识库 ----------
    section("2. 创建测试知识库（Markdown 分块策略）")
    kb_payload = {
        "name": f"测试KB-{int(time.time())}",
        "description": "RAG 管道端到端测试",
        "chunk_strategy": "markdown",
        "chunk_size": 800,
        "chunk_overlap": 80,
    }
    resp = requests.post(f"{BASE_URL}/knowledge-bases", json=kb_payload, headers=headers)
    resp.raise_for_status()
    kb = resp.json()["data"]
    kb_id = kb["id"]
    print(f"✓ 知识库已创建: id={kb_id} name={kb['name']} collection={kb['collection_name']}")

    try:
        # ---------- 3. 上传文档 ----------
        section(f"3. 上传文档: {TEST_DOC_PATH.name} ({TEST_DOC_PATH.stat().st_size} bytes)")
        with TEST_DOC_PATH.open("rb") as f:
            files = {"file": (TEST_DOC_PATH.name, f, "text/markdown")}
            resp = requests.post(
                f"{BASE_URL}/knowledge-bases/{kb_id}/documents",
                files=files,
                headers=headers,
            )
        resp.raise_for_status()
        upload_data = resp.json()["data"]
        doc_id = upload_data["document"]["id"]
        task_id = upload_data["task"]["id"]
        print(f"✓ 文档已上传: document_id={doc_id} task_id={task_id}")

        # ---------- 4. 轮询任务进度 ----------
        section("4. 轮询任务进度（最多 60 秒）")
        max_wait = 60
        for i in range(max_wait):
            resp = requests.get(f"{BASE_URL}/tasks/{task_id}", headers=headers)
            resp.raise_for_status()
            task = resp.json()["data"]
            print(f"  [{i+1:2d}s] status={task['status']:10s} progress={task['progress']:3d}%")

            if task["status"] == "success":
                print(f"✓ 任务完成！")
                break
            if task["status"] == "failed":
                print(f"✗ 任务失败：{task['error_msg']}")
                return
            time.sleep(1)
        else:
            print(f"✗ 超时未完成")
            return

        # ---------- 5. 查询文档信息（确认 chunk_count）----------
        section("5. 查询文档列表（确认 chunk_count）")
        resp = requests.get(f"{BASE_URL}/knowledge-bases/{kb_id}/documents", headers=headers)
        docs = resp.json()["data"]
        for d in docs:
            print(f"  - {d['file_name']}: status={d['status']} chunks={d['chunk_count']}")

        # ---------- 6. RAG 检索 ----------
        section("6. RAG 检索验证（3 个不同 query）")
        for query in [
            "什么是 MCP 协议？",
            "Agent 之间如何通信？",
            "使用哪种向量数据库？",
        ]:
            print(f"\n  Query: {query}")
            resp = requests.post(
                f"{BASE_URL}/knowledge-bases/{kb_id}/search",
                json={"query": query, "top_k": 3},
                headers=headers,
            )
            resp.raise_for_status()
            hits = resp.json()["data"]["hits"]
            for j, hit in enumerate(hits, 1):
                snippet = hit["content"][:80].replace("\n", " ")
                print(f"    #{j} score={hit['score']:.4f} | {snippet}...")

        print("\n" + "=" * 60)
        print("✓ 端到端测试全部通过！")
        print("=" * 60)

    finally:
        # ---------- 7. 清理 ----------
        section("7. 清理：删除测试知识库")
        resp = requests.delete(f"{BASE_URL}/knowledge-bases/{kb_id}", headers=headers)
        print(f"  删除结果: {resp.status_code} {resp.json().get('message', '')}")


if __name__ == "__main__":
    main()
