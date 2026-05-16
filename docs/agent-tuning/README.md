# 🧠 Agent 调优记录

> 记录 Agent 多轮对话、上下文管理、意图识别等方面的问题分析与优化方案。
> 每个问题包含：现象 → 根因分析 → 修复方案 → 效果验证。

---

## 索引

| # | 问题 | 涉及模块 | 日期 |
|---|------|----------|------|
| [1](#1-router-多轮对话意图误判--指代性表述被分类为闲聊) | Router 多轮对话意图误判：指代性表述被分类为闲聊 | Router 节点 | 2026-05-15 |
| [2](#2-rag-agent-多轮对话检索失准--指代性查询无法命中相关文档) | RAG Agent 多轮对话检索失准：指代性查询无法命中相关文档 | RAG Agent 节点 | 2026-05-15 |

---

## 1. Router 多轮对话意图误判：指代性表述被分类为闲聊

> **日期**：2026-05-15
> **涉及文件**：`backend/app/agent/nodes/router.py`、`backend/app/services/chat_service.py`

### 现象

用户在同一个会话中进行多轮对话：
- 第 1 轮："你看一下我的论文，明天答辩你觉得会大概率抽问我些什么方向的问题" → **正常走 RAG Agent**，成功检索知识库并回答
- 第 2 轮："那你觉得我这个项目怎么样" → **错误走 Chitchat/Fallback**，回复"你还没告诉我你的项目具体是什么呢"

前端显示第 2 轮回复来源为 `Router`（即 fallback），而非 `RAG Agent`。

### 根因分析

Router 节点在做意图分类时，**只看当前单条 `user_input`，不注入任何对话历史**：

```python
# router.py 修改前
raw = llm.complete(
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},  # 只有当前这一句
    ],
    ...
)
```

LLM 看到的仅仅是"那你觉得我这个项目怎么样"，完全不知道"这个项目"指的是上一轮聊过的论文，因此将其归类为 `chitchat`。

同时，`chat_service.py` 构造 `AgentState` 时，`summary` 字段依赖摘要压缩机制（阈值 20 条消息），在对话初期 summary 为空，导致即使 Router 想用也没有上下文可用。

### 修复方案

**两处改动**：

#### 1. `chat_service.py`：每轮对话拼接最近消息到上下文

在 `chat_once` 和 `chat_stream` 中，构造 `effective_summary` 时，无论是否触发过摘要压缩，都把最近 6 条历史消息拼接进去：

```python
effective_summary = session.summary or ""
recent_msgs = ChatService.list_messages(db, session.id)
history_msgs = recent_msgs[:-1] if recent_msgs else []  # 排除刚保存的当前消息
if history_msgs:
    recent_text = "\n".join(
        f"[{m.role.value}] {m.content[:200]}" for m in history_msgs[-6:]
    )
    if effective_summary:
        effective_summary += f"\n\n最近对话记录：\n{recent_text}"
    else:
        effective_summary = f"最近对话记录：\n{recent_text}"
```

#### 2. `router.py`：LLM 意图分类时注入对话历史

```python
# 构建 LLM 消息：注入对话历史上下文
summary = state.get("summary", "")
router_messages = [
    {"role": "system", "content": system_prompt},
]
if summary:
    router_messages.append({
        "role": "system",
        "content": f"以下是之前的对话上下文，请结合上下文判断用户意图：\n{summary}",
    })
router_messages.append({"role": "user", "content": user_input})
```

### 效果

修复后，Router 能看到上一轮聊了论文，正确将"这个项目怎么样"归类为 `rag`，走 RAG Agent 路径。

---

## 2. RAG Agent 多轮对话检索失准：指代性查询无法命中相关文档

> **日期**：2026-05-15
> **涉及文件**：`backend/app/agent/nodes/rag_agent.py`

### 现象

Router 修复后，第 2 轮提问"这个项目怎么样"正确走了 RAG Agent，但回答仍然不理想：

> "根据已有资料，我无法确认您提到的'这个项目'具体指什么……"

RAG Agent 虽然检索到了一些文档片段，但因为查询太模糊导致检索不精准，LLM 也无法理解指代关系。

### 根因分析

RAG Agent 有两层上下文缺失：

#### 问题 1：向量检索用原始模糊查询

```python
# 修改前：直接用 "这个项目怎么样" 做 embedding 搜索
query_vec = embedder.embed_query(user_input)
```

"这个项目怎么样"作为检索查询太模糊，embedding 向量无法精准匹配到论文相关的文档分块。

#### 问题 2：LLM 生成回答时无对话历史

```python
# 修改前：只有 system prompt + 检索结果 + 用户问题
messages=[
    {"role": "system", "content": _RAG_SYSTEM_PROMPT},
    {"role": "user", "content": user_prompt},
]
```

LLM 不知道之前聊了什么，无法将"这个项目"关联到论文。

### 修复方案

**三处改动**：

#### 1. 新增查询改写函数 `_rewrite_query`

结合对话历史，把模糊查询改写为包含具体实体的独立查询：

```python
_REWRITE_PROMPT = """你是查询改写器。结合以下对话历史，把用户的最新提问改写为一个包含完整上下文的独立检索查询。

规则：
1. 把代词、指代词替换为具体实体（如"这个项目"→具体项目名）
2. 保留用户的原始意图
3. 只输出改写后的查询，不要其他任何文字
4. 如果不需要改写，原样输出

对话历史：
{history}

用户最新提问：{query}"""
```

改写效果示例：`"这个项目怎么样"` → `"基于个性化推荐的找搭子系统设计与实现这个项目怎么样"`

#### 2. 向量检索使用改写后的查询

```python
search_query = _rewrite_query(llm, user_input, summary)
query_vec = embedder.embed_query(search_query)  # 用改写后的精确查询检索
```

#### 3. LLM 生成回答时注入对话历史

```python
rag_messages = [{"role": "system", "content": _RAG_SYSTEM_PROMPT}]
if summary:
    rag_messages.append({
        "role": "system",
        "content": f"以下是之前的对话上下文，可用于理解用户意图：\n{summary}",
    })
rag_messages.append({"role": "user", "content": user_prompt})
```

### 效果

修复后完整流程：
```
用户："这个项目怎么样"
  ↓
Router（看到历史：上一轮聊了论文）→ 判断 rag
  ↓
RAG Agent：
  1. 查询改写："这个项目" → "基于个性化推荐的找搭子系统"
  2. 用改写后的 query 向量检索 → 命中精准文档
  3. LLM 带上对话历史生成回答 → 理解上下文
  ↓
输出：针对论文项目的具体分析和评价
```

### 额外收益

查询改写（Query Rewriting）是 RAG 系统中的通用优化技术，不仅解决了指代问题，对以下场景也有帮助：
- 用户用口语化、简略的方式提问
- 多轮追问中省略了主语或宾语
- 用户换了说法但指的是同一个东西
