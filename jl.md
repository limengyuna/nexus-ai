
**男 | 22岁 | 籍贯：泸州 | 成都工业学院 · 本科 · 软件工程（2022-2026）**
**电话/微信：19111915461 | 邮箱：heidaheiwa123@gmail.com**

## 实习经历

**成都灵动次方科技有限公司** · 全栈开发实习 `2025.07 - 2026.04`

- **AI智能问答助手**：基于 Coze 平台为公司网页产品搭建 AI 问答助手，完成对话流程编排与 Prompt 调优，实现 ETF 量化产品智能问答
- **ETF量化数据治理**：负责日频分时数据处理，包括历史行情采集、数据标准化、复权因子处理与多数据源一致性保障
- **核心业务全栈迭代**：作为主力开发独立完成大量前后端需求落地（登录链路重构、用户裂变系统等）；通过优化 SQL 查询与引入缓存策略，核心接口响应时间平均减少 30%

## 项目经历

**NexusAI —— 基于 LangGraph 的 RAG 多智能体平台（全栈开发）** `2026.04 - 2026.05`

**技术栈**：Python + FastAPI + LangGraph + ChromaDB + Celery + PostgreSQL + Redis + Vue 3 + TypeScript + TailwindCSS + Docker

**项目描述**：基于 LLM 驱动的多智能体平台，集成 RAG 双路召回（向量 + BM25）、LangGraph 状态机编排、三层记忆体系（对话摘要 + 语义事实记忆 + RAG 知识库）、Skills 技能系统与 MCP 协议双向集成，支持私有知识问答、多步推理与外部工具调用，具备完整的可观测性与安全加固。

- **LangGraph 多 Agent 状态机编排**：基于 LangGraph 有向图设计 Router → RAG Agent / Tool Agent / Fallback 三路分发架构，Router 通过 LLM 统一分类同时输出 Skill 推荐，Tool Agent 强制执行推荐 Skill 防止参数幻觉；TypedDict 状态贯穿全流程，统一 context_prep 节点注入上下文，支持 Fallback 降级与超时控制
- **RAG 双路召回 + 检索增强**：向量语义检索 + 自实现 BM25 关键词检索，RRF 融合排名；Contextual Embedding 注入章节路径提升标题类召回率；Query Rewrite 消歧指代；LLM 引用标注 + 前端高亮采纳 chunk
- **3 种分块策略 + 结构化解析**：策略模式封装 Recursive、Markdown Header、Semantic Splitter（余弦距离检测语义跳变 + 动态阈值）；改造 Word 解析器识别 Heading 样式转 Markdown 并过滤 TOC 噪音；Celery 异步处理，前端实时展示进度
- **Skills 技能编排层（5 Skill / 4 种形态）**：设计 Tool → Skill → Agent 三层能力抽象，实现单 Tool 增强、LLM-Tool-LLM 三明治、纯 LLM 链式、multi-query RAG 检索总结、Map-Reduce 长文档全文总结 5 种编排形态
- **L2 语义事实记忆系统**：设计三层记忆体系（L1 对话摘要 / L2 语义事实 / L3 RAG 知识库），LLM 异步抽取错误教训、环境约束、用户偏好等结构化事实存入 PostgreSQL + ChromaDB；每轮对话即时抽取高价值信息（身份/指令/纠正）+ 摘要压缩时批量抽取，语义去重防止冗余；按 user_id + kb_id 范围过滤防上下文污染，时间衰减自动淘汰 + 容量上限兖底
- **MCP 协议双向集成**：作为 Server 将 RAG + 知识库通过标准 MCP 协议暴露给 Claude Desktop / Cursor 等客户端；作为 Client 动态发现和调用外部 MCP Server 工具，实现"即插即用"扩展
- **流式 SSE + 可观测性 + 安全加固**：同步 LangGraph 桥接异步 SSE 实现逐 token 流式输出；execution_trace 全链路追踪并前端可视化；JWT + 多租户隔离 + 限流 + Prompt Injection 防护 + Docker Compose 一键部署

---

**找搭子 —— AI 驱动社交活动平台（全栈开发）** `2025.12 - 2026.03`

**技术栈**：uni-app + Vue3 + TypeScript，Spring Boot 3 + Spring Cloud + Spring AI + Milvus + MySQL + Redis + Docker

- **AI 功能（Spring AI + DeepSeek）**：通过 Prompt Engineering + Structured Output 实现活动推荐、行程规划、内容润色等多场景 AI 能力，设计完善的大模型降级兜底策略
- **Milvus 向量个性化推荐**：将帖子内容向量化存入 Milvus，结合用户画像进行语义相似度检索，实现活动个性化推荐
- **微服务架构**：Spring Cloud 拆分 5 个服务，Gateway + OpenFeign + Sentinel 熔断限流 + Zipkin 链路追踪，Docker Compose 编排部署

## 荣誉奖项

- 第十六届蓝桥杯 C/C++ 程序设计大学B组（四川）省三等奖（算法）
- 第九届华为 ICT 大赛实践赛省赛基础软件赛道高职组（四川）三等奖（综合）

## 专业技能

- **AI 应用**：熟悉 Prompt Engineering、RAG 检索增强生成架构；熟悉 LangGraph 状态机编排与 AI Agent 多步推理；熟悉向量数据库（Milvus / ChromaDB）、Embedding、Function Calling、MCP 协议等核心技术；有 Coze 平台智能体搭建与知识库构建经验
- **后端**：熟悉 Python / FastAPI 异步开发与 Java / Spring Boot / Spring Cloud 微服务开发；熟悉 SQLAlchemy、MyBatis-Plus、MySQL、Redis、Docker 容器化部署
- **前端**：熟悉 Vue 3、TypeScript、uni-app 跨端开发，熟悉 UnoCSS / TailwindCSS 原子化 CSS 方案
- **工具与效能**：熟练使用 Cursor、Copilot 、Antigravity 等 AI 辅助开发工具；有 OpenClaw AI Agent 辅助服务器运维排障经验