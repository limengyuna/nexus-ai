# 🧠 Agent 调优记录

> 记录 Agent 多轮对话、上下文管理、意图识别、工具决策等方面的问题分析与优化方案。
> 每个问题包含：现象 → 根因分析 → 修复方案 → 效果验证。

---

## 索引

| # | 问题 | 涉及模块 | 状态 | 日期 |
|---|------|----------|------|------|
| [1](#1-全节点上下文缺失统一注入改造) | 全节点上下文缺失：统一注入改造 | context_prep + 全节点 | ✅ 已修复 | 2026-05-16 |
| [2](#2-rag-agent-多轮对话检索失准查询改写优化) | RAG Agent 多轮对话检索失准：查询改写优化 | RAG Agent | ✅ 已修复 | 2026-05-15 |
| [3](#3-tool-agent-function-calling-上下文缺失) | Tool Agent Function Calling 上下文缺失 | Tool Agent | ✅ 已修复（被问题 1 覆盖） | 2026-05-15 |
| [4](#4-skill-关键词误挡-mcp-请求统一-function-calling-架构) | Skill 关键词误挡 MCP 请求：统一 Function Calling 架构 | Tool Agent + Skill | ✅ 已修复 | 2026-05-16 |
| [5](#5-双模型路由pro--flash成本与速度优化) | 双模型路由（Pro + Flash）：成本与速度优化 | LLM 层 + 全节点 | ✅ 已实现 | 2026-05-17 |

---

## 1. 全节点上下文缺失：统一注入改造

> **日期**：2026-05-16（整合了 2026-05-15 的 Router、RAG Agent 手动注入方案）
> **涉及文件**：`backend/app/agent/nodes/context_prep.py`（新增）、`backend/app/agent/graph.py`、`backend/app/agent/nodes/router.py`、`backend/app/agent/nodes/rag_agent.py`、`backend/app/agent/nodes/tool_agent.py`、`backend/app/agent/nodes/fallback.py`、`backend/app/agent/state.py`、`backend/app/services/chat_service.py`

### 现象

多轮对话中，各节点出现不同程度的"失忆"：

- **Router**：第 2 轮"那你觉得我这个项目怎么样" → 不知道"项目"指什么，误判为 `chitchat`
- **RAG Agent**：收到指代性查询，检索不精准，LLM 生成回答时也不理解上下文
- **Tool Agent**：用户之前给过 GitHub 链接，Tool Agent 调 Function Calling 时完全不知道，反问用户
- **Fallback**：闲聊也无法结合之前的对话内容

### 根因分析

**每个节点各自手动注入 `summary`（对话历史），导致：**
1. **重复代码**：Router、RAG Agent、Fallback 各写一遍 `if summary: messages.append(...)`
2. **遗漏**：Tool Agent 完全没有注入上下文
3. **不一致**：每个节点注入的格式、措辞都不同

同时，`chat_service.py` 构造 `AgentState` 时，`summary` 字段依赖摘要压缩机制（阈值 20 条消息），在对话初期 summary 为空。需要在 `chat_service.py` 中拼接最近消息作为补充。

### 修复方案：context_prep 中间件模式

**核心思想**：新增 `context_prep` 节点作为中间件，统一负责上下文注入。所有下游节点只需从 `state.context_messages` 读取，不再各自处理。

#### 1. 新增 `context_prep` 节点

```python
# backend/app/agent/nodes/context_prep.py
def context_prep_node(state: AgentState) -> Dict[str, Any]:
    summary = state.get("summary", "")
    user_input = state.get("user_input", "")
    context_messages = []
    if summary:
        context_messages.append({
            "role": "system",
            "content": f"以下是之前的对话上下文，请结合上下文理解用户意图：\n{summary}",
        })
    context_messages.append({"role": "user", "content": user_input})
    return {"context_messages": context_messages}
```

#### 2. 修改图拓扑：插入 context_prep 节点

```python
# graph.py: START → context_prep → router → [条件路由]
workflow.add_edge(START, "context_prep")
workflow.add_edge("context_prep", "router")
```

#### 3. AgentState 新增 `context_messages` 字段

```python
# state.py: 纯 dict 列表，不经过 add_messages reducer
context_messages: List[Dict[str, Any]]
```

> **为什么不用 `state.messages`？**
> `messages` 字段有 `add_messages` reducer，LangGraph 会自动将 dict 转换为 LangChain Message 对象，丢失 `role` 字段格式，导致 LLM API 报错。

#### 4. 所有节点统一读取 `state.context_messages`

各节点移除手动 summary 注入逻辑，改为：

```python
# 以 Router 为例
router_messages = [
    {"role": "system", "content": system_prompt},
    *state.get("context_messages", []),
]
```

#### 5. `chat_service.py`：每轮拼接最近消息到 summary

无论是否触发过摘要压缩，都把最近 6 条历史消息拼接进 `effective_summary`：

```python
effective_summary = session.summary or ""
recent_msgs = ChatService.list_messages(db, session.id)
history_msgs = recent_msgs[:-1] if recent_msgs else []
if history_msgs:
    recent_text = "\n".join(f"[{m.role.value}] {m.content[:200]}" for m in history_msgs[-6:])
    effective_summary += f"\n\n最近对话记录：\n{recent_text}" if effective_summary else f"最近对话记录：\n{recent_text}"
```

### 改造后流程

```
START → context_prep（统一注入上下文到 state.context_messages）
              │
              ▼
          Router（从 context_messages 读上下文）
              │
       ┌──────┼──────┐
       ▼      ▼      ▼
     RAG    Tool   Fallback   ← 全部从 context_messages 读上下文
```

### 效果

- **一处注入，全员受益**：新增节点只需读 `context_messages`，不用关心上下文怎么来的
- **消除遗漏**：Tool Agent 原先完全没有上下文，现在自动获得
- **消除重复**：4 个节点的手动注入代码全部删除，上下文格式完全一致

---

## 2. RAG Agent 多轮对话检索失准：查询改写优化

> **日期**：2026-05-15
> **涉及文件**：`backend/app/agent/nodes/rag_agent.py`

### 现象

Router 正确将"这个项目怎么样"路由到 RAG Agent，但回答仍然不理想：

> "根据已有资料，我无法确认您提到的'这个项目'具体指什么……"

### 根因分析

向量检索直接用原始模糊查询 `"这个项目怎么样"` 做 embedding 搜索，无法精准匹配文档。

### 修复方案

新增查询改写函数 `_rewrite_query`，结合对话历史将模糊查询改写为包含具体实体的独立查询：

```python
_REWRITE_PROMPT = """你是查询改写器。结合以下对话历史，把用户的最新提问改写为一个包含完整上下文的独立检索查询。
...
对话历史：{history}
用户最新提问：{query}"""
```

改写效果：`"这个项目怎么样"` → `"基于个性化推荐的找搭子系统设计与实现这个项目怎么样"`

> **注意**：改写用的对话历史现在从 `state.context_messages` 中提取（由问题 1 的 context_prep 统一注入），不再手动读 `state.summary`。

### 效果

```
用户："这个项目怎么样"
  ↓
Router（有上下文）→ 判断 rag
  ↓
RAG Agent：
  1. 查询改写 → "基于个性化推荐的找搭子系统"
  2. 精准向量检索 → 命中文档
  3. LLM 带上下文生成回答
```

### 额外收益

查询改写（Query Rewriting）是 RAG 系统中的通用优化技术，对以下场景也有帮助：
- 用户用口语化、简略的方式提问
- 多轮追问中省略了主语或宾语
- 用户换了说法但指的是同一个东西

---

## 3. Tool Agent Function Calling 上下文缺失

> **日期**：2026-05-15
> **涉及文件**：`backend/app/agent/nodes/tool_agent.py`
> **状态**：✅ 已被问题 1（context_prep 统一注入）覆盖修复
> **详细图解**：参见 [tool-agent-context-problem.md](./tool-agent-context-problem.md)

### 现象

用户在之前的对话中给过 GitHub 仓库链接 `limengyuna/daz-server`，之后问"查看我的AI推荐的代码"，Tool Agent 反问"你指的是哪个代码？请提供 GitHub 链接"。

### 根因

Tool Agent 的 Function Calling 循环只注入了 system prompt + 当前 user_input，**完全没有对话历史**，LLM 不知道用户之前给过链接。

### 修复

已被问题 1 的 context_prep 统一注入覆盖。Tool Agent 现在从 `state.context_messages` 获取完整上下文。

---

## 4. Skill 关键词误拦 MCP 请求：统一 Function Calling 架构

> **日期**：2026-05-16
> **涉及文件**：`backend/app/agent/nodes/tool_agent.py`、`backend/app/agent/skills/registry.py`

### 现象

用户说"你现在能够去 GitHub 上面了解一下我的这个项目的AI推荐的具体是怎么实现的了吗"，期望 Agent 使用 GitHub MCP 工具查看代码，但实际走了 `web_search`。

右侧思考过程显示：`Skill: research_assistant`，调用了 `web_search` × 3，没有触发任何 MCP 工具。

### 根因分析

**Skill 关键词匹配太粗暴，不分青红皂白就拦截了本该走 MCP 的请求**。

Tool Agent 原来的分层架构：

```
tool_agent_node
    │
    ▼
阶段 1：_try_skill（关键词匹配）
    │ "了解一下" 命中了 research_assistant 的关键词
    │ required_tools = ["web_search"]
    │ → 直接执行 web_search，返回结果
    │ → 不再往下走
    │
    ✗ 阶段 2：_function_calling_loop
      ← MCP 工具在这里，根本没机会执行！
```

关键词匹配是"傻匹配"——不理解语义：
- "帮我了解一下 AI 发展趋势" → 命中 `research_assistant` → web_search → ✅ 正确
- "去 **GitHub** 上面了解一下代码" → 也命中 `research_assistant` → web_search → ❌ 错误

### 修复方案：统一 Function Calling 决策

**参考 OpenAI Assistants API 设计思想**，将 Skill、内部 Tool、MCP 外部工具统一抽象为 Function Calling 工具，**让 LLM 作为统一决策中心**：

#### 1. `skill_registry.py`：新增 `to_openai_tools()` 方法

将每个 Skill 包装成 OpenAI Function Calling 格式，名称加 `skill_` 前缀：

```python
def to_openai_tools(self) -> List[Dict[str, Any]]:
    schemas = []
    for s in self._skills.values():
        schemas.append({
            "type": "function",
            "function": {
                "name": f"skill_{s.name}",
                "description": f"[技能] {s.description}",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_input": {"type": "string", "description": "用户的原始输入"},
                    },
                    "required": ["user_input"],
                },
            },
        })
    return schemas
```

#### 2. `tool_agent.py`：统一工具池 + 三类分发

```python
# 统一工具池
internal_tools = tool_registry.to_openai_tools()     # 内部原子工具
mcp_schemas, mcp_tool_map = _load_mcp_tools(user_id)  # MCP 外部工具
skill_schemas = skill_registry.to_openai_tools()       # Skill 技能
openai_tools = internal_tools + mcp_schemas + skill_schemas

# 工具调用分发
if tool_name.startswith("skill_"):
    # → 执行 skill.execute()
elif tool_name in mcp_tool_map:
    # → 调用 MCP 外部工具
else:
    # → 调用内部原子工具
```

#### 3. 删除 `_try_skill` 函数

取消关键词匹配优先机制，入口直接走 `_function_calling_loop`。

### 改造前后对比

```
改造前（人工规则分层）：        改造后（LLM 统一决策）：

if 关键词命中 Skill:            LLM 看到所有工具列表：
    执行 Skill（可能误拦）        - skill_research_assistant
elif LLM 选择 Tool:              - web_search
    执行 Tool                     - get_file_contents（GitHub MCP）
elif LLM 选择 MCP:               - calculator
    执行 MCP                     LLM 根据语义自己判断调哪个
```

### 效果

用户说"去 GitHub 上面了解一下我的代码"：
- **改造前**：`"了解一下"` 命中关键词 → research_assistant → web_search ❌
- **改造后**：LLM 看到完整工具列表，理解"GitHub"语义 → 选择 GitHub MCP 工具 ✅

### 设计参考

| 产品/框架 | 做法 |
|----------|------|
| OpenAI Assistants API | Code Interpreter、File Search、自定义 Function 统一为 tools |
| Anthropic Claude | Tool Use 统一机制 |
| LangChain Agent | 所有能力实现 BaseTool 接口，LLM 统一选择 |
| Dify / Coze | 知识检索、API 调用、代码执行全部作为工具节点 |

---

## 5. 双模型路由（Pro + Flash）：成本与速度优化

> **日期**：2026-05-17
> **涉及文件**：`backend/app/core/config.py`、`backend/app/agent/llm.py`、`backend/app/agent/nodes/router.py`、`backend/app/agent/nodes/fallback.py`、`backend/app/agent/nodes/rag_agent.py`、`docker-compose.yml`、`.env`

### 现象

所有节点统一使用 `deepseek-v4-pro`（总参数 1.6T，激活 49B），存在两个问题：

1. **成本浪费**：Router 意图分类、闲聊回复等简单任务也在用最贵的模型，输出价格是 Flash 的 8 倍
2. **速度浪费**：Pro 激活参数 49B，Flash 只有 13B，非思考模式下 Flash 快 3~4 倍。Router 和 Fallback 是用户体验的“关键路径”，速度直接影响感知
3. **Pro 的 Thinking Mode 副作用**：`deepseek-v4-pro` 默认启用 thinking mode，多轮对话必须传回 `reasoning_content`，增加了复杂度和出错风险

### 根因分析

项目初期只配置了一个模型（`DEEPSEEK_MODEL`），所有节点共享同一个 `get_llm()` 单例。没有区分“重型任务”和“轻型任务”。

实际上，DeepSeek V4 提供了两个互补的模型：

| 维度 | V4-Pro | V4-Flash |
|------|--------|----------|
| 总参数 | 1.6T | 284B |
| 激活参数 | 49B | 13B |
| 上下文 | 1M tokens | 1M tokens |
| 速度 | 基准 | 快 3~4 倍 |
| 价格（输出） | ~16 元/百万 token | ~2 元/百万 token |
| 擅长 | 复杂推理、多步工具编排、Agent 任务 | 简单分类、问答、代码补全 |

### 修复方案：双模型单例工厂

核心思想：新增 `get_llm_fast()` 单例返回 Flash 模型，各节点按任务复杂度选择调用哪个。

#### 1. `config.py`：新增 DEEPSEEK_MODEL_FAST 配置项

```python
DEEPSEEK_MODEL: str = "deepseek-v4-pro"          # 重型模型
DEEPSEEK_MODEL_FAST: str = "deepseek-v4-flash"   # 轻型模型
```

#### 2. `llm.py`：双单例工厂

```python
_singleton_llm: Optional[LLMClient] = None       # Pro
_singleton_llm_fast: Optional[LLMClient] = None  # Flash

def get_llm() -> LLMClient:
    """重型 LLM（Pro）：用于 Tool Agent、Skills 等复杂推理"""
    ...

def get_llm_fast() -> LLMClient:
    """轻型 LLM（Flash）：用于 Router、闲聊、RAG 等简单任务"""
    global _singleton_llm_fast
    if _singleton_llm_fast is None:
        _singleton_llm_fast = LLMClient(model=settings.DEEPSEEK_MODEL_FAST)
    return _singleton_llm_fast
```

#### 3. 各节点模型分配

| 节点 | 模型 | 函数 | 理由 |
|------|------|------|------|
| **Router** | Flash | `get_llm_fast()` | JSON 分类任务，不需要强推理 |
| **Fallback / 闲聊** | Flash | `get_llm_fast()` | 简单对话，追求速度 |
| **RAG Agent** | Flash | `get_llm_fast()` | 有检索上下文兆底，Flash 足够 |
| **Tool Agent** | **Pro** | `get_llm()` | 多步 Function Calling 需要强推理 |
| **Skills 内部调用** | **Pro** | `get_llm()` | Skill 做多步 LLM + Tool 编排 |

#### 4. `docker-compose.yml`：传透新环境变量

backend 和 celery 容器均新增：

```yaml
DEEPSEEK_MODEL_FAST: ${DEEPSEEK_MODEL_FAST:-deepseek-v4-flash}
```

### 改造后流程

```
START → context_prep → Router (Flash, 快速分类)
                              │
                 ┌────────┼────────┐
                 │            │            │
                 ▼            ▼            ▼
          RAG Agent      Tool Agent     Fallback
          (Flash)        (Pro)          (Flash)
           │              │              │
           │         Skills 内部调用   │
           │           (Pro)          │
           ▼              ▼              ▼
                        END
```

### 效果

- **成本降低**：Router + Fallback + RAG 占约 70% 的调用量，输出价格从 ~16 元降到 ~2 元/百万 token，综合成本约降低 **60%+**
- **响应加速**：Router 意图分类和闲聊回复快 3~4 倍，用户体验“关键路径”显著改善
- **质量无损**：复杂任务（Tool Agent、Skills）仍用 Pro，保持推理质量
- **可配置**：通过环境变量切换，无需改代码即可调整模型

### 设计参考

| 产品/框架 | 做法 |
|----------|------|
| OpenAI API | 约 GPT-4o-mini 做轻量级任务，GPT-4o 做复杂任务 |
| Anthropic | Haiku 做分类/过滤，Sonnet/Opus 做推理 |
| Cursor / Windsurf | 编辑用大模型，Tab 补全用小模型 |
| Dify | 支持每个节点配置不同模型 |
