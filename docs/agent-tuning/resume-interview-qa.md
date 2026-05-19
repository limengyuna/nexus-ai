# 简历面试深挖问答记录

## 第一轮：Agent 架构

### Q1：Router 关键词匹配是怎么实现的？新增 Skill 需要改代码吗？

**答**：每个 Skill 类里定义了 `trigger_keywords` 列表，Router 用子串搜索（`kw.lower() in user_input.lower()`）遍历所有 Skill 匹配。新增 Skill 只需 `@register_skill` 装饰器 + 定义 `trigger_keywords`，路由代码不用改。

**注意点（已迭代）**：当会话绑定了知识库（`has_kb=True`）时，默认跳过关键词匹配，强制走 LLM 分类——但引入了 `allow_with_kb` 白名单机制：Skill 可设置 `allow_with_kb = True` 声明自己在有 KB 时也允许通过关键词触发（如 DocumentSummarizerSkill，用户说"总结"时应直接命中而非被 RAG 抢走）。

**设计取舍**：
- 默认跳过：避免误命中（如"向量数据库"中的"数据"被 `data_analyst` 抢走）
- 白名单放行：某些 Skill 和 RAG 场景有重叠关键词（"总结"），需要优先级机制
- 面试时主动提这个「默认严格 + 白名单松绑」的分层设计

### Q2：RAG Agent 检索到低质量内容怎么处理？

**答**（已实现完整方案）：

> "我最终采用的是**不过滤 + LLM 自判断 + 事后引用标记**的方案。所有 top-k 结果全部传给 LLM，让 LLM 自行判断相关性。回答末尾 LLM 会标注实际引用了哪些资料（如'参考资料：资料 #1、资料 #3'），后端解析这个引用列表，给对应 chunk 打上 `adopted=True`，前端据此高亮展示。"

**为什么不做硬过滤**（迭代踩坑经验）：
1. 最初设了 `RELEVANCE_THRESHOLD=0.42` 做软过滤，只保留 top-1 → 正确 chunk 排 #3 被丢弃
2. 改为保留 top-3 → 还是可能漏掉 #4、#5 的正确结果
3. 最终结论：**过度过滤的损害 > 多给噪音的损害**，LLM 本身就能区分相关/不相关

**三层协作**：
- **检索层**：全部 top-k 传入，不丢弃
- **LLM 层**：prompt 要求标注引用编号 + "资料不足就说明"
- **前端层**：被引用的蓝色高亮，未被引用的灰色展示

**注意**：ChromaDB 返回的是余弦距离（distance，越小越相关，范围 0~2），不要说反了！`adopted` 字段的含义是"LLM 实际引用了"，不是"score 低于阈值"。

### Q3：简历上"70% 请求节省一次 LLM 调用"怎么来的？

**问题**：原简历写了具体数字但无法验证。实际上只要会话绑了知识库，关键词匹配就跳过了——大部分知识库问答场景都会走 LLM 分类。

**已修正**：简历已改为定性描述"无 KB 场景下跳过 LLM 直接路由"，去掉了无法支撑的 70%。

**教训**：简历上的每一个数字都必须能自圆其说，答不上来会被认为编数据。

---

## 第二轮：RAG 深挖 + MCP + 实习

### Q4：Semantic Splitter 具体怎么判断"跳变点"？阈值是固定的还是动态的？

**答**：
1. 按句末标点把文档切成句子列表
2. 每句话生成 Embedding 向量（批量调用通义 API）
3. 计算每两个相邻句子之间的余弦距离
4. 距离从小到大排列，取 `breakpoint_percentile=95` 分位数作为动态阈值
5. 距离超过阈值的位置就是"语义跳变点"，在那里切一刀

**两个兜底机制**（加分项）：
- 太短的 chunk（< `min_chunk_chars=80`）自动并入前一个，避免碎片化
- 单块超过 `chunk_size` 时，用 RecursiveSplitter 二次细切，防止语义块过大

**为什么选这个方案**：比固定长度切分更灵活，能最大程度保证语义相关的内容在同一个 chunk 里不被截断，提升 RAG 检索质量。

### Q5：MCP Server 暴露了哪些内容？传输层用什么？为什么？

**答**：暴露了三类 MCP 原语：
- **Resources**：知识库列表 + 单个知识库元数据读取
- **Tools**：`nexus_rag_search`（RAG 语义检索）+ 内部所有工具（get_weather、calculate 等）
- **Prompts**：`rag_qa_template`（RAG 问答提示词模板）——**容易漏掉，注意提**

传输层用 stdio，原因：
> "Server 端用 stdio 是因为目标场景是本地客户端（Claude Desktop / Cursor 都在本机运行），stdio 是进程间通信，延迟最低、无需网络配置。Client 端同时支持 stdio 和 SSE 两种，根据外部 MCP Server 的配置自动选择。"

### Q6：SQL 优化和缓存策略具体做了什么？30% 怎么量化的？

**答**：
- SQL：把 `SELECT *` 改为只查业务需要的字段
- 缓存：对高频使用的基金代码和名称建了一个**内存字典做双向映射**（Python dict），启动时一次性从 DB 加载，后续查询走内存不走 DB（输入 code 返回名称，输入名称返回 code）
- 30%：通过多次批量调用线上部署好的服务，对比优化前后的平均响应时间得出

---

## 第三轮：Skills + SSE + 安全 + 底层理解

### Q7：multi-query RAG 子查询质量怎么保证？

**答**：通过 Prompt 约束 LLM 拆解为 1-3 个互补的子查询，代码里硬限制 `_MAX_QUERIES = 3`。召回时做 chunk 去重 + 分数排序，高相关度排前面。

**不足**：目前没有对子查询质量做校验（如与原问题语义相似度检查）。可诚实说"靠 Prompt 约束，后续可加语义相似度校验过滤低质量子查询"。

**注意**：面试别说"一般只拆3个"，要说"代码硬限制了 `_MAX_QUERIES = 3`"，体现主动设计。

### Q8：SSE 流式是真流式还是假流式？⚠️ 重要

**答错了**：说成了"假流式"，实际上是**真流式**（逐 token）。

**正确回答**：
> "RAG 和 Fallback 节点用的是逐 token 真流式——`stream=True` 调 LLM API，每个 token 通过 `queue.Queue` 桥接到 ASGI 异步生成器，再通过 SSE 推给前端。之所以用队列桥接，是因为 LangGraph 的 `invoke` 是同步调用，但 FastAPI 的 StreamingResponse 需要异步生成器，所以用 `asyncio.to_thread` + Queue 做了同步→异步的适配。Tool Agent 因为要等工具执行完才有结果，是执行完一次性推送，不是逐 token 的。"

**架构**：
```
LLM API (stream=True) → 逐 token yield → token_queue.put() → 主线程 asyncio 消费 → SSE chunk → 前端打字机
```

**和 ChatGPT 的区别**：token 粒度完全一样，唯一区别是中间多了 queue + asyncio.to_thread 的同步→异步桥接层。

**教训**：自己写的代码注释都写了"真流式"，面试说反了会被严重质疑项目真实性。

### Q9：Prompt Injection 防护链路 ⚠️ 链路说错

**关键词分类**（答对了）：
1. 无视指令类（忽略以上所有指令）
2. 身份劫持类（你现在是 DAN）
3. 套壳窥探类（reveal your system prompt）
4. 越权指令类（sudo）
5. 伪造系统消息（`<|im_start|>system`）

**完整链路**（答错了 Router 部分）：
```
1. chat_service 入口 → maybe_warn() 正则匹配检测
2. 命中 → 打印 WARNING 日志（记录 user_id + 模式 + 输入）
3. 在 summary 追加 GUARD_REINFORCEMENT（对抗性安全指令）
4. 正常进入 LangGraph：context_prep → router → 某个节点
5. 不管走到哪个节点，LLM 都看到安全加固指令
6. LLM 根据加固指令拒绝泄露 system prompt
```

**重点**：防护不是在路由层拦截的，是在 LLM 层通过追加对抗性指令实现的。Router 不参与安全防护，它甚至不知道输入有没有风险。不要说"Router 分配到闲聊节点"——Router 走的是正常 LLM 分类逻辑，不知道输入是攻击。

**为什么选软防护不硬阻断**：硬阻断容易误伤正常用户（如讨论 prompt 技术的合法请求），软防护对用户体验更好。
