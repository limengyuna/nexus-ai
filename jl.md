
**男 | 22岁 | 籍贯：泸州 | 成都工业学院 · 本科 · 软件工程（2022-2026）**
**电话/微信：19111915461 | 邮箱：heidaheiwa123@gmail.com**

## 实习经历

**成都灵动次方科技有限公司** · 全栈开发实习 `2025.08 - 2026.03`

- **AI智能问答助手**：基于 Coze 平台为 ETF 量化产品搭建智能问答助手；从客户群提取高频问题去重后构建 30+ 条测试集，驱动 Prompt 多轮迭代调优，最终问题解决率达 90%+；设计"概述 + 权威文档引导"策略解决专业术语准确性问题，平衡便捷性与金融场景精度要求
- **ETF量化数据治理**：负责 1500+ 只 ETF/LOF 的行情数据治理（2018至今）；历史数据通过多源融合（API + 数据包）补全并统一处理复权因子与交易时段差异；当日分时数据基于定时任务分 5 个时间节点采集实时行情，保障回测系统数据完整性与时效性
- **核心业务全栈迭代**：作为主力开发独立完成大量前后端需求落地（登录链路重构、用户裂变系统等）；通过优化 SQL 查询与引入缓存策略，核心接口响应时间平均减少 30%

## 项目经历

**NexusAI —— 基于 LangGraph 的 RAG 多智能体平台（全栈开发）** `2026.03 - 2026.05`

**技术栈**：Python + FastAPI + LangGraph + ChromaDB + Celery + PostgreSQL + Redis + Vue 3 + TypeScript + TailwindCSS + Docker
**项目描述**：基于 LLM 驱动的多智能体协作平台，支持私有知识问答与多步复合任务；通过 MCP 协议动态集成外部工具（数据库、搜索、文件系统等），Agent 能力按需扩展；具备完整的可观测性与多租户安全隔离。

- **Supervisor 多 Agent 编排**：LLM 驱动动态 task_plan 拆解复合请求为多步执行（如"查规章制度再写邮件"），设计步骤隔离机制防子 Agent 越权；设计 Skill 编排层支持多种 Tool+LLM 组合模式（三明治、Map-Reduce 等）；全链路 Fast/Pro 双模型策略 + Fallback 降级兜底
- **RAG 全链路优化**：Unstructured 结构化文档解析 + 中文标题正则增强；Parent-Child 分块策略实现检索精度与上下文完整性解耦；Contextual Embedding 注入章节路径；向量 + BM25 双路检索 RRF 融合（top-15）→ Cross-Encoder（gte-rerank-v2）精排（top-6）；Query Rewrite 多轮消歧 + LLM 引用标注溯源 + **LLM-as-Judge 逐声明忠实性校验**（拆解回答为事实声明并逐条核查来源支撑，前端可视化校验报告）；构建 60 条评测集自动化回归，Recall@6 达 86.7%、Faithfulness 均分 100%、端到端平均响应 1.58s
- **L2 语义事实记忆**：三层记忆体系（对话摘要 / 语义事实 / RAG 知识库）覆盖分钟-天-永久三个时间维度；LLM 异步抽取错误教训与用户偏好，语义去重 + kb_id 范围隔离防上下文污染
- **MCP 协议双向集成**：作为 Server 暴露 RAG 能力给 Claude Desktop / Cursor；作为 Client 对接外部 MCP Server，创建时预缓存工具列表至 PostgreSQL，运行时 0ms 读取，消除实时连接的数秒级阻塞
- **流式 SSE + 可观测性 + 安全**：Queue 桥接 LangGraph → SSE 逐 token 流式输出；execution_trace 全链路追踪；Prompt Injection 软防护 + 多租户隔离 + Docker Compose 部署
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
- **后端**：熟悉 Python / FastAPI 异步开发与 Java / Spring Boot / Spring Cloud 微服务开发；熟悉 SQLAlchemy、MyBatis-Plus、MySQL、PostgreSQL、Redis；具备 Docker Compose 编排部署与 Linux 服务器交付经验（Web / 小程序 / APP 全端上线）
- **前端**：熟悉 Vue 3、TypeScript、uni-app 跨端开发，熟悉 UnoCSS / TailwindCSS 原子化 CSS 方案
- **工具与效能**：熟练使用 Cursor、Copilot 、Antigravity 等 AI 辅助开发工具；有 OpenClaw AI Agent 辅助服务器运维排障经验