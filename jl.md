
**男 | 22岁 | 籍贯：泸州 | 成都工业学院 · 本科 · 软件工程（2022-2026）**
**电话/微信：19111915461 | 邮箱：heidaheiwa123@gmail.com**

## 实习经历

**成都灵动次方科技有限公司** · 全栈开发实习 `2025.07 - 2026.04`

- **AI智能问答助手**：基于 Coze 平台为公司网页产品搭建 AI 问答助手，完成对话流程编排与 Prompt 调优，实现 ETF 量化产品智能问答
- **ETF量化数据治理**：负责日频分时数据处理，包括历史行情采集、数据标准化、复权因子处理与多数据源一致性保障
- **核心业务全栈迭代**：作为主力开发独立完成大量前后端需求落地（登录链路重构、用户裂变系统等）；通过优化 SQL 查询与引入缓存策略，核心接口响应时间平均减少 30%

## 项目经历

**NexusAI —— 企业级智能知识库 + 多 Agent 协作平台（全栈开发）** `2026.04 - 2026.05`

**技术栈**：Python + FastAPI + LangGraph + ChromaDB + Celery + PostgreSQL + Redis + Vue 3 + TypeScript + TailwindCSS + Docker

**项目描述**：一个基于大模型驱动的 AI 中台，集成 RAG 检索增强生成、LangGraph 多 Agent 状态机编排、Skills 技能系统与 MCP 协议双向集成，支持私有知识问答、多步推理与外部工具调用，具备完整的可观测性与企业级安全加固。

- **LangGraph 多 Agent 状态机编排**：基于 LangGraph 有向图设计 Router → RAG Agent / Tool Agent / Fallback 三路分发架构，Router 先关键词预匹配 Skill 走快速路径（无 KB 场景下跳过 LLM 直接路由），匹配不到再调 LLM 分类；严格 TypedDict 状态贯穿全流程，支持 Fallback 降级与超时控制
- **完整 RAG 管道与 3 种分块策略**：实现"上传→解析→分块→Embedding→向量入库→检索→生成"全管道。策略模式封装 3 种分块：Recursive（通用）、Markdown Header（保留结构）、**Semantic Splitter**（基于 Embedding 余弦距离检测语义跳变点）；Celery 异步处理，前端实时展示进度
- **Skills 技能编排层（5 Skill / 4 种形态）**：设计 Tool → Skill → Agent 三层能力抽象，实现单 Tool 增强、LLM-Tool-LLM 三明治、纯 LLM 链式、multi-query RAG、多源综合调研 5 种编排形态
- **MCP 协议双向集成**：作为 Server 将 RAG + 知识库通过标准 MCP 协议暴露给 Claude Desktop / Cursor 等客户端；作为 Client 动态发现和调用外部 MCP Server 工具，实现"即插即用"扩展
- **流式响应 + 可观测性 + 企业级加固**：ASGI 异步 SSE 流式输出（5 种事件） + 前端打字机效果；execution_trace 记录完整推理链路并前端可视化；JWT + 多租户隔离 + slowapi 限流 + Prompt Injection 防护 + Docker Compose 6 服务一键部署

---

**找搭子 —— AI 驱动社交活动平台（全栈开发）** `2025.12 - 2026.03`

**技术栈**：uni-app + Vue3 + TypeScript，Spring Boot 3 + Spring Cloud + Spring AI + MySQL + Redis + Docker

- **AI 功能（Spring AI + DeepSeek）**：通过 Prompt Engineering + Structured Output 实现活动推荐、行程规划、内容润色等多场景 AI 能力，设计完善的大模型降级兜底策略
- **微服务架构**：Spring Cloud 拆分 5 个服务，Gateway + OpenFeign + Sentinel 熔断限流 + Zipkin 链路追踪，Docker Compose 编排部署

## 荣誉奖项

- 第十六届蓝桥杯 C/C++ 程序设计大学B组（四川）省三等奖（算法）
- 第九届华为 ICT 大赛实践赛省赛基础软件赛道高职组（四川）三等奖（综合）

## 专业技能

- **AI 应用**：熟悉 Prompt Engineering、RAG 检索增强生成架构；熟悉 LangGraph、CrewAI 等 AI 应用开发框架，熟悉向量数据库（Milvus/Chroma）、Embedding、Function Calling、MCP 协议、AI Agent 等核心概念；有 Coze 平台智能体搭建与知识库构建经验，熟练使用 Cursor、Antigravity（含 MCP 服务接入与 Skills 扩展）等 AI 辅助开发工具；在 Linux 服务器部署 OpenClaw AI Agent 辅助微服务部署与运维排障
- **后端**：熟悉 Python / FastAPI 异步开发与 Java / Spring Boot / Spring Cloud 微服务开发；熟悉SQLAlchemy、MyBatis-Plus、MySQL、Redis、Docker 容器化部署
- **前端**：熟悉 Vue 3、TypeScript、uni-app 跨端开发，熟悉 UnoCSS 原子化 CSS 方案