# NexusAI — 企业级智能知识库 + 多Agent协作平台

## 1. 项目背景与目标
本项目旨在打造一个基于大模型（LLM）驱动的企业级 AI 中台。系统采用**前后端分离**架构，结合 RAG（检索增强生成）技术与基于 LangGraph 的多 Agent 协作工作流。支持灵活配置的知识库解析、长期会话记忆压缩，并通过多 Agent 智能路由协同完成问答、数据分析及外部工具调用任务。同时引入 **Skills（技能编排层）** 与 **MCP（Model Context Protocol）协议层**，实现 Agent 能力的标准化暴露与外部 MCP Server 的即插即用集成，全面展示 AI 应用开发能力与前沿架构视野。

---

## 2. 核心技术架构选型

### 2.1 基础架构
- **系统架构**: 前后端分离 (Monorepo 模式管理)
- **后端框架**: FastAPI (Python 3.10+，支持异步与高并发，适合 SSE 流式输出)
- **前端框架**: Vue 3 + Vite + TailwindCSS + Headless UI
- **状态管理**: Pinia (Vue 3 官方推荐)
- **认证方案**: JWT + 用户名/密码基础认证
- **异步任务**: Celery + Redis（文档处理等重度 IO 异步化）

### 2.2 AI & 大模型组件
- **核心推理大模型**: DeepSeek API (极高性价比与强大的推理能力)
- **Embedding 模型**: 阿里通义 `text-embedding-v3` API (中文支持极佳，无需本地部署消耗资源)
- **Agent 工作流框架**: LangGraph (状态机驱动，可控性极强，告别不可控的 AgentExecutor)
- **Agent 会话记忆机制**: 基于 LLM 的对话历史摘要压缩（Summary Memory），兼顾上下文理解与 Token 节省
- **Skills 技能系统**: 多 Tool + Prompt 模板的组合编排层，比原子 Tool 更高一级的能力抽象
- **MCP 协议层**: 基于 Model Context Protocol 标准，同时实现 Server（暴露能力）+ Client（调用外部 MCP Server）

### 2.3 存储方案
- **关系型数据库**: PostgreSQL (企业级标准配置) + SQLAlchemy (ORM) + Alembic (迁移)
- **向量数据库**: ChromaDB (轻量高效，Python原生，支持复杂查询与持久化)
- **消息队列 / 缓存**: Redis (Celery Broker + 结果后端 + 可选缓存层)

---

## 3. 核心功能与机制设计

### 3.1 知识库数据管道 (Data Pipeline) 与 动态分块策略
支持多模态文档接入（PDF, Docx, MD, TXT），并在后台支持**动态可配置的分块（Chunking）策略**：
- **通用策略 (默认)**: `RecursiveCharacterTextSplitter` (支持管理员配置 `chunk_size` 和 `chunk_overlap`)。
- **结构化策略 (针对 Markdown)**: `MarkdownHeaderTextSplitter`，严格按照标题层级拆分，保留文档结构语义。
- **异步处理**: 文档上传后由 Celery 异步执行"解析→分块→Embedding→入库"全流程，前端通过轮询 `TaskRecord` 获取进度。

### 3.2 LangGraph 多 Agent 协作引擎
核心基于 LangGraph 的有向图设计：
1. **Router Agent (路由中枢)**: 接收输入，进行意图识别，匹配 Skill 或分发给专业 Agent。
2. **RAG Agent (知识引擎)**: 连接 Chroma 提取相关文本，进行上下文组装生成回答。
3. **Tool/Task Agent (执行引擎)**: 挂载外部 Tools（如：基金查询、旅游天气等），调用后整合信息。
4. **Graph State**: 定义严谨的 TypedDict 状态，贯穿全局流程，记录会话摘要、中间步骤、工具调用结果与**执行链路追踪**。
5. **容错与人机协作**: Fallback 降级节点 + 节点超时控制 + `interrupt_before` 人工审批（Human-in-the-loop）。

### 3.3 Skills 技能系统
Skills 是**比 Tool 更高层级的能力抽象**，一个 Skill 封装了多个 Tool 的编排逻辑 + 专用 Prompt 模板：
- **BaseSkill**: 技能基类，定义标准接口（name, description, required_tools, prompt_template, execute）。
- **SkillRegistry**: 技能注册中心，支持动态注册/发现/按意图匹配。
- **示例技能**:
  - `TravelPlannerSkill`: 天气Tool + 景点Tool → 生成旅行规划
  - `DataAnalystSkill`: 数据查询Tool + 计算Tool → 生成分析报告
- Router Agent 优先匹配 Skill，匹配不到再降级到单 Tool 调用。

### 3.4 MCP 协议层（Model Context Protocol）
基于 Anthropic 发布的 MCP 开放标准，实现**双向集成**：

#### MCP Server 端（暴露自身能力）
将平台内部能力通过标准 MCP 协议对外暴露，任何 MCP 兼容客户端（如 Cursor、Claude Desktop）都能直接接入：
- **Resources**: 暴露知识库列表、文档元数据等为标准 MCP Resource。
- **Tools**: 暴露 RAG 检索、知识库问答等为标准 MCP Tool。
- **Prompts**: 暴露可复用的问答/分析 Prompt 模板为标准 MCP Prompt。

#### MCP Client 端（调用外部能力）
Agent 内置 MCP Client，可动态发现和调用外部 MCP Server 提供的工具：
- 管理员可在后台配置外部 MCP Server 连接信息（传输方式: stdio / SSE）。
- Tool Agent 在运行时通过 MCP Client 获取外部工具列表并按需调用。
- 实现"即插即用"扩展——无需改代码，配置一个 MCP Server 即可为 Agent 增加新能力。

### 3.5 可观测性（Observability）
- Agent 执行链路追踪：在 `GraphState.execution_trace` 中记录每个节点的入参、出参、耗时、Token 消耗。
- 前端"思考过程"面板：实时展示 Agent 的推理链路（Router 决策 → Agent 执行 → Tool 调用详情）。
- 可选接入 LangSmith 进行生产级别的 LLM 调用追踪。

---

## 4. 目录结构设计 (Monorepo)

```text
ag1/                                # 项目根目录
├── plan.md                         # 项目规划文档（本文件）
├── backend/                        # FastAPI 后端项目
│   ├── app/
│   │   ├── api/                    # REST API 及 SSE 路由接口
│   │   │   ├── auth.py             # 登录/注册接口
│   │   │   ├── chat.py             # 对话接口 (SSE 流式)
│   │   │   ├── knowledge_base.py   # 知识库 CRUD
│   │   │   └── task.py             # 异步任务状态查询
│   │   ├── core/                   # 配置管理、JWT安全认证、数据库连接
│   │   │   ├── config.py           # 环境变量与配置
│   │   │   ├── security.py         # JWT 令牌签发/校验
│   │   │   └── database.py         # SQLAlchemy 引擎与 Session
│   │   ├── models/                 # SQLAlchemy 关系型数据表模型
│   │   ├── schemas/                # Pydantic 校验模型
│   │   ├── services/               # 核心业务逻辑
│   │   ├── rag/                    # RAG 模块
│   │   │   ├── parser.py           # 文档解析器（PDF/Docx/MD/TXT）
│   │   │   ├── splitter.py         # 动态分块策略（策略模式）
│   │   │   ├── embedder.py         # Embedding 接口封装（通义 API）
│   │   │   └── vector_store.py     # 向量存储抽象层 + Chroma 实现
│   │   ├── agent/                  # LangGraph 多 Agent 引擎
│   │   │   ├── graph.py            # LangGraph 主图编排
│   │   │   ├── state.py            # AgentState (TypedDict) 定义
│   │   │   ├── nodes/              # Agent 节点实现
│   │   │   │   ├── router.py       # Router Agent：意图识别与分发
│   │   │   │   ├── rag_agent.py    # RAG Agent：检索+生成
│   │   │   │   └── tool_agent.py   # Tool Agent：工具/MCP调用
│   │   │   ├── tools/              # 原子工具层
│   │   │   │   ├── registry.py     # 工具注册中心
│   │   │   │   ├── weather.py      # 天气查询工具
│   │   │   │   └── fund_query.py   # 基金查询工具
│   │   │   └── skills/             # 技能编排层（多Tool组合）
│   │   │       ├── base.py         # BaseSkill 技能基类
│   │   │       ├── registry.py     # 技能注册中心
│   │   │       ├── travel_planner.py
│   │   │       └── data_analyst.py
│   │   ├── mcp/                    # MCP 协议层
│   │   │   ├── server.py           # MCP Server 主入口
│   │   │   ├── client.py           # MCP Client（调用外部 MCP Server）
│   │   │   ├── resources/          # MCP Resources 定义
│   │   │   │   └── knowledge_base.py
│   │   │   ├── tools/              # MCP Tools 定义
│   │   │   │   └── rag_search.py
│   │   │   └── prompts/            # MCP Prompts 定义
│   │   │       └── qa_template.py
│   │   └── tasks/                  # Celery 异步任务
│   │       ├── celery_app.py       # Celery 实例配置
│   │       └── document_tasks.py   # 文档处理异步任务
│   ├── alembic/                    # 数据库迁移
│   ├── requirements.txt
│   └── main.py
├── frontend/                       # Vue 3 前端项目
│   ├── src/
│   │   ├── api/                    # Axios 请求封装
│   │   ├── views/                  # 视图页面
│   │   │   ├── ChatView.vue        # 对话界面（含思考过程面板）
│   │   │   ├── KBManageView.vue    # 知识库管理
│   │   │   ├── MCPConfigView.vue   # MCP Server 配置管理
│   │   │   └── LoginView.vue       # 登录页
│   │   ├── components/             # 公共组件
│   │   │   ├── MessageBubble.vue   # 消息气泡（支持 Markdown 渲染）
│   │   │   ├── ThinkingTrace.vue   # Agent 思考过程展示
│   │   │   └── FileUploader.vue    # 文档上传组件
│   │   └── store/                  # Pinia 状态管理
│   ├── package.json
│   └── vite.config.ts
└── docs/                           # 架构文档、接口说明
```

---

## 5. 核心数据库表设计预览 (PostgreSQL)

### 用户与认证
- **User**: `(id, username, hashed_password, role, created_at, updated_at)`

### 知识库与文档
- **KnowledgeBase**: `(id, name, description, chunk_strategy, chunk_size, chunk_overlap, created_by, created_at)`
- **Document**: `(id, kb_id, file_name, file_type, file_size, chunk_count, status, error_msg, created_at)`

### 对话与消息
- **ChatSession**: `(id, user_id, kb_id, title, summary, created_at, updated_at)`
  > `summary` 字段存储 LLM 摘要压缩后的历史上下文，作为给 LLM 的精简记忆。
- **ChatMessage**: `(id, session_id, role, content, agent_source, tool_calls_json, token_usage, created_at)`
  > `agent_source` 标记由哪个 Agent 产出（router/rag/tool），`tool_calls_json` 记录工具调用详情。

### 异步任务
- **TaskRecord**: `(id, type, related_id, status, progress, error_msg, created_at, finished_at)`
  > 追踪文档处理等 Celery 异步任务的状态与进度。

### MCP 外部连接
- **MCPServerConfig**: `(id, name, description, transport_type, connection_uri, is_active, created_by, created_at)`
  > 管理员配置的外部 MCP Server 连接信息（stdio / SSE 传输方式）。

---

## 6. 面试核心亮点（高价值话术准备）

1. **架构选型的深度思考**: "为了保证 Agent 执行的绝对可控，我放弃了早期的 LangChain AgentExecutor，转而使用 LangGraph 的状态机编排。这让系统不仅支持复杂的条件分支，还能通过 `interrupt_before` 实现关键决策的人工审批 (Human-in-the-loop)。"

2. **Tool 与 Skill 的分层设计**: "我把工具能力分成了两层——原子 Tool 和组合 Skill。Skill 是多个 Tool + 专用 Prompt 的智能编排，Router 根据意图优先匹配 Skill，匹配不到再降级到单个 Tool。这使系统在不改代码的情况下就能快速扩展复杂的组合能力。"

3. **MCP 双向集成的前沿视野**: "我在平台中实现了 MCP 协议层——一方面作为 MCP Server 将内部的知识库和工具能力通过标准协议暴露，任何 MCP 兼容客户端（如 Cursor、Claude Desktop）都能直接接入；另一方面，Agent 内置 MCP Client，可以动态发现和调用外部 MCP Server 的工具，实现了真正的'即插即用'扩展，体现了开放架构思维。"

4. **高级 RAG 优化**: "在文档处理上，我设计了**策略模式**，支持后台动态配置分块策略。例如对于 Markdown 文件，采用 Header 分块最大程度保留语义。整个处理流程通过 Celery 异步化，不会阻塞用户请求。"

5. **资源与效能的平衡**: "将重度的 Embedding 和推理都交给了第三方高性能 API (通义/DeepSeek)，不仅降低了服务器资源消耗，而且利用 LLM 进行历史消息总结压缩（Summary Memory），大幅降低了多轮对话的长文本 Token 开销。"

6. **可观测性**: "在 Agent 系统中加入了执行链路追踪，前端有专门的'思考过程'面板，可以清楚看到 Router 如何决策、每个 Agent 节点的推理过程、工具调用详情和 Token 消耗，这对生产环境的排错和成本优化至关重要。"

---

## 7. 实施路线图 (Development Roadmap)

### 阶段一：基础设施与基座搭建  ✅
- [x] 初始化 Monorepo 项目结构（后端 FastAPI，前端 Vue 3 + Pinia + TailwindCSS）。
- [x] 搭建 PostgreSQL 数据库，使用 SQLAlchemy 编写全部表结构（User, KnowledgeBase, Document, ChatSession, ChatMessage, TaskRecord, MCPServerConfig）。
- [x] 配置 Alembic 数据库迁移。
- [x] 实现 JWT 登录鉴权 + 全局异常处理 + 统一响应格式。
- [x] 搭建 Celery + Redis 异步任务基础设施。

### 阶段二：知识库与 RAG 管道建设  ✅
- [x] 封装 Embedding 接口 (调用阿里通义 `text-embedding-v3` API)。
- [x] 编写文档解析器（PDF/Docx/MD/TXT）与多种文本分块策略（策略模式）。
- [x] 接入 ChromaDB 向量存储（抽象 VectorStore 接口）。
- [x] 实现 Celery 异步任务：完整的"文档上传→解析→切分→向量化→入库"管道。
- [x] 实现 TaskRecord 状态追踪接口（前端轮询进度）。
- [x] **超出原计划**：新增第三种切分策略 `SemanticSplitter`（基于 Embedding 余弦距离的语义跳变点检测）。

### 阶段三：LangGraph 多 Agent 引擎 + Skills + MCP  ✅
- [x] 接入 DeepSeek API，封装 LLM 调用层。
- [x] 定义 `AgentState`（含 execution_trace），实现 RAG Agent 节点。
- [x] 增加对话记忆（LLM 摘要压缩机制）。
- [x] 开发 Router Agent 节点，实现意图路由（优先匹配 Skill，降级到 Tool）。
- [x] 编写原子 Tool：`calculate` / `get_weather` + Tool 注册中心。
- [x] 实现 Skills 技能系统：BaseSkill + SkillRegistry + **5 个 Skill**（超出原计划的 2 个）。
- [x] 实现 Fallback 降级节点 + 节点超时控制。
- [x] 实现 MCP Server（将 RAG 检索 + 知识库暴露为标准 MCP Resources/Tools/Prompts）。
- [x] 实现 MCP Client（Agent 动态发现和调用外部 MCP Server 工具）。
- [x] **超出原计划**：MCP 连接测试 API（创建前验证） + 2 个新 Tool（`rag_search` / `web_search`）。

### 阶段四：前端开发与大联调  ✅
- [x] 对话界面开发：SSE 流式接口对接 + 打字机效果 + Markdown 渲染 + 代码高亮。
- [x] Agent 思考过程面板（ThinkingTrace 组件）：实时展示推理链路。
- [x] 管理后台：知识库管理、文档上传（含进度展示）、分块策略配置。
- [x] MCP Server 配置管理页面（MCPConfigView）。
- [x] 整体联调、测试与 Bug 修复。
- [x] **超出原计划**：18+ 项用户体验优化（Toast/重命名/快捷键/暗色模式/骨架屏/锁屏页等）。

### 阶段五：企业化加固（原计划之外的提升） ✅
- [x] SSE 流式响应（后端 `chat_stream` 异步生成器 + 前端 fetch + ReadableStream）。
- [x] 多租户数据隔离（所有 KB/Document/MCP 接口过滤 `created_by`）。
- [x] Rate Limiting（slowapi，按 JWT-sub 限流，防 LLM token 滥用）。
- [x] Prompt Injection 轻量防护（关键词检测 + system prompt 加固，不硬阻断）。
- [x] Docker 化：backend / frontend Dockerfile + nginx 反代（SSE 不缓冲） + 完整 `docker-compose.yml`。
- [x] 根 README 重写（Mermaid 架构图 + Features 卡片 + 一键启动）。

---

## 8. 技术架构全景图

```
┌─────────────────────────────────────────────────────────────────┐
│                        Vue 3 Frontend                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐   │
│  │ ChatView │  │ KBManage │  │  Login   │  │  MCPConfig    │   │
│  │ +Trace   │  │ +Upload  │  │          │  │  管理页面     │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └───────┬───────┘   │
│       │ SSE         │ REST        │ REST            │ REST      │
└───────┼─────────────┼─────────────┼─────────────────┼───────────┘
        │             │             │                 │
┌───────┴─────────────┴─────────────┴─────────────────┴───────────┐
│                      FastAPI Backend                             │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   API Layer (路由)                        │   │
│  └──────────────────────┬───────────────────────────────────┘   │
│                         │                                        │
│  ┌──────────────────────┴───────────────────────────────────┐   │
│  │                Service Layer (业务逻辑)                   │   │
│  └──┬──────────────┬──────────────┬─────────────────────────┘   │
│     │              │              │                               │
│  ┌──┴───┐   ┌──────┴──────┐   ┌──┴──────────────────────────┐  │
│  │ RAG  │   │   Agent     │   │       MCP 协议层             │  │
│  │ 管道 │   │  ┌────────┐ │   │  ┌─────────┐ ┌───────────┐  │  │
│  │      │   │  │ Router │ │   │  │ Server  │ │  Client   │  │  │
│  │ 解析 │   │  │ RAG Ag │ │   │  │(暴露能力)│ │(调外部MCP)│  │  │
│  │ 分块 │   │  │ Tool Ag│ │   │  └─────────┘ └───────────┘  │  │
│  │ 向量 │   │  ├────────┤ │   └──────────────────────────────┘  │
│  └──┬───┘   │  │ Skills │ │                                      │
│     │       │  │ Tools  │ │                                      │
│     │       │  └────────┘ │                                      │
│     │       └──────┬──────┘                                      │
│  ┌──┴───┐   ┌──────┴──────┐   ┌──────────┐   ┌──────────┐      │
│  │Chroma│   │  DeepSeek   │   │ PostgreSQL│   │  Redis   │      │
│  │ DB   │   │  API        │   │ + Alembic │   │ + Celery │      │
│  └──────┘   └─────────────┘   └──────────┘   └──────────┘      │
└──────────────────────────────────────────────────────────────────┘

---

## 9. 实际实现成果总览

### 9.1 代码体量

| 维度 | 数值 |
|------|-----:|
| 总代码行数（不含依赖）| ~9,500 行 |
| 后端 Python 文件 | 70+ |
| 前端 Vue / TS 文件 | 25+ |
| REST API 路由 | 35+ |
| 数据库表 | 7 张 + 7 个 Alembic 迁移 |
| Skills | **5 个**（4 种不同编排形态）|
| Tools | **4 个**（calculate / get_weather / rag_search / web_search）|
| 分块策略 | **3 种**（recursive / markdown / **semantic**）|

### 9.2 完成的 35+ 个 API 路由

| 模块 | 路由 |
|------|------|
| **认证** | POST `/auth/register`、POST `/auth/login`、GET `/auth/me` |
| **健康检查** | GET `/health` |
| **知识库** | GET/POST/PATCH/DELETE `/knowledge-bases[/{id}]` |
| **文档** | POST 上传 / GET 列表 / DELETE 删除 / GET `/{id}/chunks` 预览 / POST `/{id}/reprocess` 重处理 / POST `/search` 检索 |
| **任务** | GET `/tasks/{id}` 进度查询 |
| **对话** | GET/POST/PATCH/DELETE `/chat/sessions[/{id}]`、GET messages、POST messages（同步）、**POST messages/stream（SSE）** |
| **MCP** | GET/POST/DELETE `/mcp/servers`、POST `/test` 测试连接、GET `/{id}/tools`、POST `/{id}/invoke` |
| **Skills** | GET `/skills` 列出、POST `/skills/{name}/test` 直接执行 |

### 9.3 5 个 Skills 的编排形态对比

| Skill | Tool 数 | LLM 调用 | 编排形态 | 业务场景 |
|------|:------:|:--------:|---------|---------|
| `travel_planner` | 1 | 1 | **单 Tool 增强** | 旅行规划 = 天气查询 + LLM 综合建议 |
| `data_analyst` | 1 | 2 | **LLM-Tool-LLM 三明治** | 数学计算 = LLM 抽表达式 + Tool 求值 + LLM 解读 |
| `email_drafter` | **0** | 2 | **纯 LLM 链式推理** | 邮件起草 = LLM 抽元素 + LLM 生成 |
| `document_summarizer` | 3+ | 2 | **multi-query RAG** | 知识库摘要 = 拆解查询 + 多次检索 + 综合 |
| `research_assistant` | 6+ | 2 | **多源综合（web + RAG）** | 综合调研 = web 搜索 + 内部知识库 + LLM 综合 |

### 9.4 前端 4 个核心页面

| 路由 | 页面 | 核心功能 |
|------|------|---------|
| `/chat` | 💬 智能对话 | SSE 流式 + 思考链路 + 会话重命名/搜索/滚动/重生成/复制 |
| `/knowledge` | 📚 知识库 | KB CRUD + 文档上传/预览/重新处理 + 3 种分块策略 + 批量统计 |
| `/skills` | ✨ Skills | 5 个 Skill 详情 + **测试执行（自动选 KB）** + 调用链路可视化 |
| `/mcp` | 🔌 MCP 配置 | 外部 Server 增删改 + 测试连接 + 工具清单 |

### 9.5 18+ 项前端用户体验优化

- Toast 通知系统（vue-sonner）+ 全局 ConfirmDialog（替代 alert/confirm）
- 会话重命名（双击/铅笔 inline edit）+ 会话搜索
- 消息复制按钮 / 时间戳 / 重新生成 / 滚到底部浮动按钮
- 登录页 Loading 旋转 + 密码可见切换 + 输入框图标
- 全局快捷键（Ctrl+K 新建对话 / Ctrl+/ 切换思考面板 / Esc 关闭弹窗）
- 文档分块预览弹窗 / 文档重新处理 / 文档搜索 / 批量上传统计
- MCP 测试连接（创建前先验证延迟与工具数）
- 页面标题动态变化 + 404 页面 + 加载骨架屏
- **暗色模式**（useTheme + 8 个组件全部 dark 适配 + 跟随系统）
- 侧边栏 hover 浮层展开（不挤压主内容）

### 9.6 6 项企业级加固

| 维度 | 实现 |
|------|------|
| **流式响应** | 后端 `ChatService.chat_stream` 异步生成器 + 5 种 SSE 事件 + 前端 fetch+ReadableStream 解析 |
| **多租户隔离** | 服务层加 `user_id` 参数；KB/Document/MCP 所有 list/get/delete 接口按 `created_by` 过滤；404 替代 403 防资源枚举 |
| **限流** | slowapi 按 JWT-sub 限流：LLM 30/min · 登录 10/min · 上传 20/min |
| **Prompt 防护** | 10+ 高置信度关键词检测 + 命中时给 system prompt 追加加固指令（软防护，不误伤）|
| **Docker 化** | 6 服务编排（postgres/redis/chroma/backend/celery/frontend）+ nginx SSE 不缓冲 + 健康检查 + 自动 alembic migrate |
| **数据持久化** | 3 个 Docker named volume，重启电脑/重建容器都不丢数据 |

---

## 10. 面试故事线（5 个高价值话术）

### 故事 1：为什么是 LangGraph 而不是 LangChain AgentExecutor？

> "早期我也用过 LangChain 的 `AgentExecutor`，但它本质是'让 LLM 自己决定下一步'，**执行路径完全不可控**，调试和成本控制都很难。LangGraph 是状态机驱动的有向图——每个节点的入参出参都明确定义，分支条件可以是代码逻辑（不一定靠 LLM 决策）。
>
> 我设计的图结构：**Router → (RAG / Tool / Fallback)**，Router 节点先用关键词预匹配 Skill 走快速路径，匹配不到才调 LLM 分类。这样**70% 的请求节省了一次 LLM 调用**，且每个分支都可独立测试。"

### 故事 2：三层架构 Tools / Skills / Agents 的设计取舍

> "如果只靠 LLM 的 Function Calling 让模型自己选工具，存在 3 个问题：稳定性差（同问题不同答）、复杂业务不可复用、出错难定位。
>
> 我抽出了 **Tool → Skill → Agent 三层**：
> - **Tool** = 原子能力，单一职责（如 calculator）
> - **Skill** = 业务工作流，编排多个 Tool + 专用 Prompt（如 document_summarizer = 拆解查询 + 多次 RAG + 综合）
> - **Agent** = 智能路由层，根据意图分发到不同 Skill / Tool
>
> 我实现了 **5 个 Skill 覆盖 4 种编排形态**：单 Tool 增强、三明治、纯 LLM 链式、multi-query RAG、多源综合。其中 `document_summarizer` 用的就是业界 RAG 进阶常用的 multi-query 模式——LLM 先把宽问题拆 3 个子查询，分别检索去重，再综合写带 `[1][3]` 引用的摘要。"

### 故事 3：RAG 的"3 种分块策略"性价比权衡

> "分块策略直接影响 RAG 质量，我做了三种策略以策略模式抽象，让用户按场景选：
>
> | 策略 | 速度 | 成本 | 质量 | 适用 |
> |------|:----:|:----:|:----:|------|
> | recursive | 极快 | 0 | 中 | 通用兜底 |
> | markdown | 极快 | 0 | 高 | 技术文档（保留标题层级）|
> | **semantic** | 慢 | 调 N 次 Embedding | **最高** | 高质量场景 |
>
> Semantic Splitter 是我重点做的：先按句号切句子，每句单独 embed，计算相邻句子余弦距离，取 95 分位数作为'语义跳变阈值'，在跳变点切分。这是业界 2024 年开始流行的方法（Greg Kamradt 提出）。"

### 故事 4：SSE 流式响应的"准流式 + 真元事件"设计

> "对话不流式是用户最不能接受的——所有 AI 面试官都会问。我用 ASGI 异步生成器实现了 SSE：
>
> 后端定义 5 种事件：`status`（状态变化）/ `meta`（Router 决策）/ `chunk`（字符流）/ `done`（完整 trace）/ `error`。前端用 fetch + ReadableStream + TextDecoder 解析（比 EventSource 灵活，能带 Authorization header）。
>
> **关键设计**：LangGraph invoke 是同步的，但我把整图运行放到 `asyncio.to_thread`，**不阻塞事件循环**；拿到答案后按 4 字符 + 15ms 间隔 yield 字符，实现打字机效果；同时**思考过程面板在打字开始前就显示了 Router 决策**，因为 `meta` 事件先于 `chunk` 发出。"

### 故事 5：从"个人作品"到"企业级"的最后一公里

> "Demo 能跑只是第一步，企业级还有 5 个硬指标：
>
> 1. **多租户隔离**：服务层加 `user_id` 参数，所有查询带 `WHERE created_by = user`；查询不到时返 404 而不是 403，避免资源 ID 枚举攻击
> 2. **限流**：slowapi 按 JWT-sub 限流，LLM 30 次/分钟防 token 滥用，登录 10 次/分钟防暴力
> 3. **Prompt Injection 轻量防护**：用 10 个高置信度正则检测常见模式（"忽略你的指令"/"act as DAN"等），命中时给 system prompt 追加加固指令——**不硬阻断**（容易误伤普通用户）
> 4. **可观测性**：每次对话的 `execution_trace` 完整记录每个节点的耗时、入参、出参，前端思考过程面板实时可视化，生产环境排错效率提升 10x
> 5. **一键部署**：完整 `docker-compose.yml` 6 服务编排（数据 3 个 + 应用 3 个），nginx 反代且 **SSE 配 `proxy_buffering off`**（很多教程都漏了这点导致流式失效），面试官 `docker compose up -d` 一行命令就能跑"

---

## 11. 可选扩展（未做但可加，按面试 ROI 排序）

| 优先级 | 项 | 工作量 | 说明 |
|:----:|------|------:|------|
| 🔥 高 | **pytest 单元测试**（minimal 版）| ~1h | 15 个关键测试覆盖认证/隔离/Prompt防护/Router 路由；用 SQLite in-memory，CI 秒跑 |
| 🔥 高 | **GitHub Actions CI**（lint + 跑测试）| ~30min | 配合上面的 pytest，自动化质量门 |
| ⭐ 中 | **Token 成本统计 Dashboard** | ~40min | 每用户/会话 token 累加，前端展示月度用量 |
| ⭐ 中 | **WebSocket 实时通知** | ~1h | 文档处理完成自动推送（替代轮询）|
| ⭐ 中 | **RBAC 角色权限**（admin/user 区分）| ~30min | User 表已有 `role` 字段，加路由依赖即可 |
| ⭐ 中 | **真正的 LLM Token-by-Token 流式** | ~1.5h | 当前是"准流式"（图执行完后按字符 yield），改成真流式要重构 LLM 调用层 |
| 低 | **Ragas 评测脚本** | ~1h | RAG 召回率/答案准确度评估，体现 LLM 质量保障意识 |
| 低 | **Sentry 异常上报** | ~20min | 生产级可观测性 |
| 低 | **导出会话为 Markdown** | ~30min | 实用小功能 |
| 低 | **真正的可视化 Skill 编排器** | 8h+ | Dify/LangFlow 风格，超出当前项目定位 |

> 面试时被问到"还有什么可以做的"，按以上列表挑 2-3 个回答，并明确说"我评估过 ROI，先把核心功能做扎实"。
