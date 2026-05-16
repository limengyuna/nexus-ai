"""
阶段三端到端测试

验证三条路径：
1. 闲聊 → Fallback 节点（"你好"）
2. 工具 → Tool Agent → Skill 命中（"我想去北京旅行" / "计算 (123+456)*2"）
3. RAG  → 创建 KB + 上传文档 → 知识库问答（"NexusAI 用什么向量数据库？"）

每个场景都会打印 Router 决策、Agent 使用情况、思考过程链路。

用法（在 backend/ 目录下）::

    .\.venv\Scripts\python.exe scripts\test_agent_e2e.py
"""
import json
import sys
import time
from pathlib import Path

import requests

BASE_URL = "http://localhost:8002/api/v1"
USERNAME, PASSWORD = "admin", "admin123"
PLAN_MD = Path(__file__).parent.parent.parent / "plan.md"


def section(t):
    print(f"\n{'=' * 70}\n>>> {t}\n{'=' * 70}")


def login() -> dict:
    r = requests.post(
        f"{BASE_URL}/auth/login",
        data={"username": USERNAME, "password": PASSWORD},
    )
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


def chat(headers, session_id, message):
    r = requests.post(
        f"{BASE_URL}/chat/sessions/{session_id}/messages",
        json={"message": message},
        headers=headers,
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["data"]


def print_response(d):
    msg = d["message"]
    print(f"\n[Intent]       {d.get('intent', '')}")
    print(f"[RouteReason]  {d.get('route_reason', '')}")
    if d.get("skill_used"):
        print(f"[Skill]        {d['skill_used']}")
    if d.get("tool_calls"):
        print(f"[Tool Calls]   {len(d['tool_calls'])} 次")
        for tc in d["tool_calls"]:
            args = json.dumps(tc.get("arguments", {}), ensure_ascii=False)
            print(f"   - {tc.get('name')} args={args}")
    if d.get("retrieved_docs"):
        print(f"[Retrieved]    {len(d['retrieved_docs'])} 段")
        for i, doc in enumerate(d["retrieved_docs"][:2], 1):
            print(f"   #{i} score={doc['score']:.4f} | {doc['content'][:60].replace(chr(10), ' ')}...")
    # trace
    print(f"\n[Trace]")
    for step in d.get("execution_trace", []):
        print(f"   {step['node']:12s} | {step['elapsed_ms']:5d}ms | {step.get('output', {})}")
    # 最终回复
    print(f"\n[Answer]\n{msg['content']}\n")


def main():
    # 登录
    section("0. 登录")
    headers = login()
    print("Token OK")

    # ============================================================
    # 场景 1：闲聊（Fallback 路径）
    # ============================================================
    section("场景 1：闲聊（Fallback 路径）")
    r = requests.post(f"{BASE_URL}/chat/sessions", json={"title": "闲聊测试"}, headers=headers)
    sess_id_1 = r.json()["data"]["id"]
    print(f"会话 #{sess_id_1} 已创建")

    try:
        resp = chat(headers, sess_id_1, "你好，你是谁？")
        print_response(resp)
    finally:
        requests.delete(f"{BASE_URL}/chat/sessions/{sess_id_1}", headers=headers)

    # ============================================================
    # 场景 2A：Tool Agent → 旅行 Skill
    # ============================================================
    section("场景 2A：Tool Agent → 旅行 Skill")
    r = requests.post(f"{BASE_URL}/chat/sessions", json={"title": "旅行测试"}, headers=headers)
    sess_id_2 = r.json()["data"]["id"]
    try:
        resp = chat(headers, sess_id_2, "我想去杭州旅行，给我点建议")
        print_response(resp)
    finally:
        requests.delete(f"{BASE_URL}/chat/sessions/{sess_id_2}", headers=headers)

    # ============================================================
    # 场景 2B：Tool Agent → 数据分析 Skill
    # ============================================================
    section("场景 2B：Tool Agent → 数据分析 Skill")
    r = requests.post(f"{BASE_URL}/chat/sessions", json={"title": "计算测试"}, headers=headers)
    sess_id_3 = r.json()["data"]["id"]
    try:
        resp = chat(headers, sess_id_3, "帮我计算一下 (1+2+3+4+5) * 100 / 15 等于多少")
        print_response(resp)
    finally:
        requests.delete(f"{BASE_URL}/chat/sessions/{sess_id_3}", headers=headers)

    # ============================================================
    # 场景 3：RAG Agent
    # ============================================================
    section("场景 3：RAG Agent（先建KB+上传文档，再提问）")
    # 1. 建 KB
    kb_resp = requests.post(
        f"{BASE_URL}/knowledge-bases",
        json={
            "name": f"agent-test-{int(time.time())}",
            "chunk_strategy": "markdown",
            "chunk_size": 800,
            "chunk_overlap": 80,
        },
        headers=headers,
    ).json()["data"]
    kb_id = kb_resp["id"]
    print(f"KB #{kb_id} 已创建")

    try:
        # 2. 上传 plan.md
        with PLAN_MD.open("rb") as f:
            up = requests.post(
                f"{BASE_URL}/knowledge-bases/{kb_id}/documents",
                files={"file": ("plan.md", f, "text/markdown")},
                headers=headers,
            ).json()["data"]
        task_id = up["task"]["id"]

        # 3. 等任务完成
        print("等待文档处理...", end="", flush=True)
        for _ in range(60):
            s = requests.get(f"{BASE_URL}/tasks/{task_id}", headers=headers).json()["data"]
            if s["status"] == "success":
                print(f" 完成 ({s['progress']}%)")
                break
            if s["status"] == "failed":
                print(f" 失败: {s['error_msg']}")
                return
            print(".", end="", flush=True)
            time.sleep(1)

        # 4. 创建会话（带 kb_id）
        r = requests.post(
            f"{BASE_URL}/chat/sessions",
            json={"title": "RAG测试", "kb_id": kb_id},
            headers=headers,
        )
        sess_id_4 = r.json()["data"]["id"]

        # 5. 提问
        try:
            resp = chat(headers, sess_id_4, "NexusAI 项目用的是哪个向量数据库？为什么选它？")
            print_response(resp)
        finally:
            requests.delete(f"{BASE_URL}/chat/sessions/{sess_id_4}", headers=headers)
    finally:
        requests.delete(f"{BASE_URL}/knowledge-bases/{kb_id}", headers=headers)
        print("KB 已清理")

    print("\n" + "=" * 70)
    print("✓ 阶段三端到端测试完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
