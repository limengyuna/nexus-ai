# 简历面试深挖问答记录

## 第一轮：Agent 架构

### Q1：Router 是怎么做意图识别和 Skill 推荐的？为什么不用关键词匹配？

**答**：

> "Router 完全由 LLM 做意图分类。我在 Router 的 system prompt 里列出所有可用技能和 MCP 服务的描述，LLM 输出一个 JSON，包含 `intent`（rag/tool/chitchat）、`reason`（理由）和 `recommended_skill`（推荐的技能名或 null）。如果推荐了具体 Skill，后端验证该 Skill 真实存在后写入 state，Tool Agent 就会强制执行该 Skill，避免 LLM 自由选工具时可能出现的参数幻觉（比如编造 kb_id）。"

**追问：为什么不用关键词预匹配？之前尝试过吗？**

> "最初用过关键词预匹配，每个 Skill 定义 `trigger_keywords`，Router 先子串匹配再 LLM 分类。但实际使用中发现严重的误命中问题——比如用户说'把研究报告写入文件'，'研究'被 `research_assistant` 的关键词命中，但用户实际意图是文件写入。子串匹配无法区分词语在句中是动词（帮我研究 X）还是名词修饰（研究报告）。改为纯 LLM 分类后，语义理解精准度大幅提升，用的是轻量快速模型延迟可控。"

**设计取舍**：
- LLM 分类比关键词匹配多一次 API 调用，但用 `get_llm_fast`（轻量模型），延迟在可接受范围
- `recommended_skill` 只在意图明确时才填，不确定时填 null 让 Tool Agent 自行决策
- Tool Agent 的强制执行兜底了 Router 推荐准确时的参数安全问题

**⚠️ 重要说明**：Router 节点代码已实现但**目前未接入主流程**，系统直接走 Supervisor 统一调度。如果面试官问 Router，可以说"这是早期设计的轻量级分流方案，后来发现 Supervisor 本身就能处理意图分类（闲聊直接回答），所以目前只用 Supervisor，Router 保留作为未来优化选项"。

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

### Q3：Router 每次都调 LLM 会不会太慢？

**答**：

> "Router 用的是 `get_llm_fast`（轻量快速模型），`max_tokens=200`，`temperature=0`，输出只有一行 JSON。实测延迟在 200-500ms，相比 Tool Agent 动辄几秒的工具执行，这个开销可接受。之前用关键词预匹配虽然更快但误命中严重，为了准确率值得这点延迟。"

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

### Q5：MCP Server 暴露了哪些内容？传输层用什么？Client 端怎么做的？

**答**：暴露了三类 MCP 原语：
- **Resources**：知识库列表 + 单个知识库元数据读取
- **Tools**：`nexus_rag_search`（RAG 语义检索）+ 内部所有工具（get_weather、calculate 等）
- **Prompts**：`rag_qa_template`（RAG 问答提示词模板）——**容易漏掉，注意提**

传输层用 stdio，原因：
> "Server 端用 stdio 是因为目标场景是本地客户端（Claude Desktop / Cursor 都在本机运行），stdio 是进程间通信，延迟最低、无需网络配置。Client 端同时支持 stdio 和 SSE 两种，根据外部 MCP Server 的配置自动选择。"

**追问：Client 端 MCP 工具怎么挂载和管理的？**

> "Client 端的核心设计是**整个 MCP Server 作为一个工具整体挂载**，而不是把子工具逐个拆开注册。每个 MCP 的描述由 LLM 在创建时自动生成——前端点击'测试连接'后预拉取全部子工具列表，LLM 根据子工具的名称和描述精炼出一句 30-80 字的整体功能描述，写入数据库。
>
> Supervisor 在做任务规划时，直接从 PostgreSQL 读取各 MCP 的名称和描述注入 prompt，就像 Skill 一样作为能力选项出现，决策速度是 0ms 级别。Tool Agent 执行时也是从数据库的 `cached_tools` 字段读取子工具 schema，而不是每次都去实时连接外部 Server。只有在用户主动点击'强制刷新'时才重新连接拉取并更新缓存。
>
> 这样做的好处是：即使外部 MCP Server 暂时不可用（比如 npx 网络不通），Supervisor 的规划和 Tool Agent 的工具注册都不受影响，系统的鲁棒性大幅提升。"

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

---

## 第四轮：RAG 检索优化 + 工程实战

### Q10：怎么提升 RAG 检索准确率的？⭐ 高频题，必须能完整讲出来

**标准回答**（按问题→排查→解决的故事线，分四层优化）：

> "我做了四层递进优化，每层解决不同维度的问题：
>
> **第一层：文档解析**——用 unstructured 库做结构化解析，识别文档元素类型（Title / NarrativeText / Table）。针对中文文档额外写了正则增强（`_enhance_chinese_headings`），把'第X章'、'（一）'等中文编号模式提升为正确的标题级别。解析后转成 Markdown 格式，保留层级结构。
>
> **第二层：分块策略**——用 MarkdownHeaderSplitter 按标题层级分块，metadata 里自动带上 header_path。实现了 **Parent-Child 分块策略**：大块（800-2000字）作为 parent，超长时再切成 child（300-500字），child 的 metadata 记录 parent_content。检索时匹配小的 child 块（精准），但给 LLM 送完整的 parent 块（上下文完整）——**检索精度和上下文完整性解耦**。
>
> **第三层：向量化优化**——做了 **Contextual Embedding**：向量化时把 header_path 拼到 chunk 前面（如 `[绪论 > 1.1 设计背景] 正文...`），解决 embedding 被正文语义主导、标题类查询召回率低的问题。参考 Anthropic 的 Contextual Retrieval 方案。
>
> **第四层：检索精排**——向量 + BM25 双路召回通过 RRF 融合取 top_k=15 个候选，再用 **Cross-Encoder（gte-rerank-v2）精排**取 top_n=6 给 LLM。Cross-Encoder 把 query 和 document 拼在一起做联合编码，精度远高于向量检索，解决了粗排不够精准的问题。
>
> 整体思路是**每一层都在提升信噪比**：解析去噪 → 分块聚焦 → 向量化增强 → 检索精排 → 最终送给 LLM 的是高质量、完整的相关内容。"

**关键术语**（必须自然说出来）：
- unstructured 结构化解析 + 中文标题正则增强
- Parent-Child 分块（检索粒度和上下文粒度解耦）
- Contextual Embedding / 上下文注入
- embedding 向量被正文语义主导
- 双路召回（Dense + Sparse）+ RRF 融合
- Cross-Encoder 精排（粗排+精排两阶段）

**⚠️ 致命错误**：不要说"增加了标题的向量权重"——你没有改模型权重，你改的是**喂给模型的输入文本**。

### Q11：Query Rewrite 查询改写做了什么？踩过什么坑？

**答**：

> "我做了查询改写，用 LLM 结合对话历史把模糊查询改写为适合向量检索的独立查询，主要解决指代消歧——比如用户说'它的设计背景'，改写为'NexusAI系统的设计背景'。
>
> 踩了一个坑：最初改写 prompt 规则是'把代词替换为具体实体'，结果 LLM 过度改写——把'设计背景'改成了完全不相关的实体名，导致检索偏离。后来优化了 prompt，加了三条约束：①不要过度改写 ②保留用户原始关键词 ③如果已经足够明确就原样输出。"

**追问：为什么不直接用原始查询？**
> "多轮对话场景下用户会用代词指代之前的话题，比如'它怎么实现的'——不改写的话，'它'没有语义，向量检索会命中一堆不相关内容。改写的目的是消歧，不是重写。"

**追问：怎么确保改写质量？**
> "temperature=0 保证确定性，max_tokens=200 限制输出长度，有 try-catch 兜底——改写失败就直接用原始查询。另外加了日志打印改写前后对比，方便排查。"

**追问：每次都调 LLM 改写不会太慢吗？有没有想过更细粒度的可控策略？**
> "考虑过的。我做了**第一道闸门**——首轮没有对话历史时直接跳过改写，零 LLM 调用。
>
> 还考虑过更激进的方案：在调 LLM 前用关键词检测（'它'、'这个'、'刚才'等指代词）判断是否需要改写——理论上能减少 60% 的改写调用。但**最终没做**，因为中文对话里有大量**主语省略**的延续问题，比如用户问'限制是什么'、'为什么'、'还有呢'，没有显式指代词但实际是延续问题。规则检测会漏判这些场景，损害检索质量。
>
> 检索是 RAG 的命脉，宁可多花 800ms 让 LLM 在 prompt 里自己判断（已经明确的就原样输出），也不要因为关键词漏判导致检索质量下滑。这是一个**质量优先于延迟**的有意识 trade-off。"

**追问（高阶）：还有什么提升召回率的高级技术？**
> "**HyDE**（Hypothetical Document Embeddings）是一个有意思的思路——先让 LLM 根据用户 query 生成一段假设性回答，再用这段回答去做向量检索，而不是用原始 query。
>
> 原理是：query 通常是问句风格（'驾照视力要求是什么'），而知识库 document 是陈述句风格（'申请机动车驾驶证应当符合的身体条件包括视力...'），两者语义相同但**风格不对称**，向量距离可能不够近。让 LLM 先把 query 改写成陈述句风格的假设回答，能让检索向量更接近真实 document 的分布，提升召回。
>
> 我没用 HyDE 主要因为：**第一**，我已经有 BM25 关键词检索作为双路兜底，能弥补语义检索的风格差异问题；**第二**，HyDE 多一次 LLM 调用会增加 1 秒左右延迟，对实时问答影响明显；**第三**，如果 LLM 生成的假设回答有幻觉偏差，反而会污染检索。HyDE 真正适合**纯向量检索 + 长篇学术文档**的场景，跟我的多源混合检索系统不太匹配。"

**关键术语**：
- HyDE = Hypothetical Document Embeddings（CMU 2022 提出）
- query-document 风格不对称问题
- 改写可控的多级闸门（无 history 跳过 / 关键词预检测 / LLM 自判）

### Q12：双路召回 + RRF 具体怎么实现的？为什么不用 Elasticsearch？

**答**：

> "向量路用 ChromaDB 做语义检索，BM25 路是我自研的纯 Python 实现——查询时从 ChromaDB 拉取当前知识库的全量 chunk 文本，在内存中动态构建倒排索引和 IDF，用单字（中文）+ 单词（英文）做分词。两路各取 top_k×2 个候选，用 RRF 融合排名后取 top_k。"

**追问：RRF 是什么？**
> "Reciprocal Rank Fusion，核心公式是 `1/(k+rank_dense) + 1/(k+rank_sparse)`，k=60 是论文推荐的常数。只看排名不看原始分数，天然避免了两路异构分数不可比的问题。两路都排名靠前的文档得分最高。"

**追问：为什么不用 Elasticsearch？**
> "项目规模不需要。单个知识库通常几千个 chunk，全量拉取构建索引耗时在毫秒级，引入 ES 会增加部署复杂度（多一个服务）和运维成本。纯 Python 实现零外部依赖，对这个规模足够。如果扩展到百万级 chunk，再考虑 ES 或 Milvus。"

**追问：单字分词不会有噪音吗？**
> "会有。比如搜'机器学习'会被拆成单字，匹配到只含'学习'的文档。但 BM25 是辅路，向量路已经兜底了语义匹配——两路互补正是双路召回的意义。单字分词对精确关键词（人名、产品型号）的匹配效果已经足够好。"

### Q13：长文档总结是怎么做的？

**答**：

> "用 Map-Reduce 方案。通过 `vector_store.list_by_metadata(document_id=xxx)` 按文档 ID 拉取该文档的全部 chunk。如果 chunk 数量 ≤ 阈值，直接拼接给 LLM 一次总结；超过阈值走 Map-Reduce——Map 阶段每 N 个 chunk 一批生成局部摘要，Reduce 阶段把所有局部摘要合并为最终总结。"

**追问：为什么不直接用 RAG 检索来做总结？**
> "RAG 检索是基于查询相关性取 top-k，适合回答具体问题。但'总结全文'没有具体查询方向，top-k 只能命中部分内容，会遗漏重要段落。Map-Reduce 保证覆盖全文每一个 chunk，不遗漏。"

**追问：这个是哪个 Skill 实现的？**
> "DocumentSummarizerSkill。它有两种模式：用户问具体主题时走 multi-query RAG（拆子查询多路检索），用户要求'总结全文/整篇文档'时走 Map-Reduce。通过分析用户输入中的关键词（'全文'、'整篇'、'总结一下这篇文档'）来选择模式。"

### Q14：非结构化文档（Word/PDF）怎么解析并保留标题层级？

**答**：

> "我用 unstructured 库做结构化文档解析——它能识别文档中的元素类型（Title / NarrativeText / Table / ListItem 等），保留层级关系。解析后把每个元素按类型转成 Markdown 格式：Title 转为对应层级的 `#` 标题，Table 转为 Markdown 表格，NarrativeText 保留段落。
>
> 但 unstructured 对中文文档的标题识别不够好——比如'第一章'、'（一）'、'1.1 概述'这类中文法规常见的编号标题，它可能识别为普通段落。所以我额外写了 `_enhance_chinese_headings()` 函数，用正则匹配常见的中文编号模式（'第X章'→h1、'第X节'→h2、'（一）'→h3、'1.1'→h2 等），把被错误识别的段落提升为正确的标题级别。这样后续 MarkdownHeaderSplitter 就能按结构精确分块。"

**追问：为什么不直接用 python-docx？**
> "python-docx 只能处理 .docx，不支持 PDF、RTF 等格式。unstructured 统一了多种格式的解析入口（底层按格式调用不同引擎：docx 用 python-docx、PDF 用 pdfminer、PPT 用 python-pptx 等），并且自带元素类型识别。我只需要在它的基础上做中文增强就够了，不用针对每种格式写解析逻辑。"

**追问：表格怎么处理的？**
> "unstructured 识别出 Table 元素后，如果元素自带 HTML 格式，我会解析 HTML 的 `<tr>/<td>` 标签转成 Markdown 表格格式（`| col1 | col2 |`）。如果没有 HTML，就直接用元素的纯文本内容。保留表格结构的好处是 LLM 能更好地理解表格内的对应关系，比如'视力要求 → 对应车型'这种映射。"

### Q15：Reranker 重排模型怎么实现的？为什么要加？⭐

**答**：

> "我实现了**粗排+精排的两阶段架构**。粗排阶段：向量 + BM25 双路检索通过 RRF 融合，取 top_k=15 个候选。精排阶段：用通义 gte-rerank-v2（Cross-Encoder）对 15 个候选逐个与 query 做联合编码，按相关性重新排序，取 top_n=6 给 LLM。
>
> 加 Reranker 的原因：向量检索用的是 Bi-Encoder——query 和 document 分别编码成向量再算距离，速度快但精度有限，因为编码时看不到对方。Cross-Encoder 把 query 和 document 拼在一起做联合编码，能捕捉词级别的语义交互，精度远高于向量检索。但它计算量大，不能对全库跑，只适合对少量候选精排。
>
> 实测效果：加了 Reranker 后，送入 LLM 的 5 个 chunk 相关性明显提升，尤其是原来排在 #4、#5 的正确结果，经过精排后被提到 #1、#2。"

**追问：为什么用 gte-rerank-v2 而不是 bge-reranker？**
> "gte-rerank-v2 是通义 DashScope 的云端 API，和我们已有的 Embedding API（text-embedding-v4）同属一个平台，共用一个 API Key，部署零成本。bge-reranker 需要本地部署模型（需要 GPU），对我这个项目规模来说过重了。"

**追问：Reranker 增加了多少延迟？**
> "gte-rerank-v2 对 10 个候选的精排耗时约 200-400ms，相比 LLM 生成的几秒钟可以接受。而且粗排多召回、精排精筛选的策略，让整体回答质量的提升远超这点延迟成本。"

**追问（高阶）：除了 Cross-Encoder，工业搜索还有什么排序方案？为什么不用？**
> "工业级最经典的方案是 **Learning to Rank（LTR）**，代表算法是 **LambdaMART**——基于 GBDT 的有监督排序模型。它把 query 和 document 的几十维特征（BM25 分、向量相似度、文档长度、点击率、新鲜度、PageRank 等）作为输入，用 Multiple Additive Regression Trees 学习排序函数，直接优化 NDCG 等排序指标。百度、Bing、淘宝搜索都在用这套方案。
>
> 我没用 LambdaMART 主要因为两点：**第一是缺少训练数据**——它需要人工标注的相关性数据或大量真实用户的点击日志，个人项目无法获得；**第二是规模不匹配**——我的知识库在千级 chunk，Cross-Encoder 精排已经达到很好的精度，引入 LambdaMART 需要大量特征工程和 ensemble 调优，属于过度工程。
>
> 如果未来知识库扩到百万级、有真实用户的点击数据，**LambdaMART 是合理的下一步**——可以把 Cross-Encoder 的输出作为它的一个特征，把多路信号一起做 ensemble，在精度上还能再上一个台阶。"

**关键术语**（高阶答法用）：
- Learning to Rank（LTR）—— 学习排序
- LambdaMART = LambdaRank + MART（GBDT 排序）
- 直接优化 NDCG/MAP 等不可导排序指标
- Pointwise / Pairwise / Listwise 三种训练范式（LambdaMART 属于 Listwise）

---

## 第五轮：底层原理 + 易错概念

### Q16：余弦距离和余弦相似度什么关系？你项目里的 score 越大越好还是越小越好？

**答**：

> "余弦相似度 = 两个向量夹角的余弦值，范围 [-1, 1]，越大越相似（1 = 完全相同）。余弦距离 = 1 - 余弦相似度，范围 [0, 2]，越小越相似。ChromaDB 默认返回余弦距离，所以我的项目里 **score 越小越相似**。"

**⚠️ 常见陷阱**：面试官可能问"score 0.9 和 0.2 哪个更相关"——必须先确认是**距离还是相似度**再回答，不然说反了直接扣分。

### Q17：SSE 为什么要用 Queue 桥接？子线程不能直接输出给前端吗？

**答**：

> "不能。根本原因是 **Python 的 yield 不能跨线程**——yield 是函数内部的暂停/恢复机制，绑定在定义它的函数栈里，别的线程访问不到。FastAPI 的 StreamingResponse 需要一个 async generator 来逐步 yield 数据，但 LangGraph `graph.invoke` 是同步阻塞的，占着子线程直到全部节点跑完。子线程有数据但不能 yield，主线程能 yield 但没数据——Queue 就是两者之间传数据的桥梁。"

**追问：为什么 LangGraph 不做成异步的？**
> "LangGraph 的 `invoke` 方法设计上就是同步的（目前版本），内部节点函数也是同步定义。虽然有 `ainvoke` 异步版本，但节点函数本身调用了同步的 LLM SDK 和数据库操作，强行 async 化收益不大，反而增加复杂度。用 `asyncio.to_thread` 包一层是最简单的适配方式。"

### Q18：本地开发或 Windows 部署 Stdio MCP 踩过哪些坑？你怎么解决的？⭐ 证明你真正懂 Windows 底层和协议细节的“杀手锏”

**答**：

> "在把平台从 Linux 生产容器迁移到本地 Windows 开发模式时，我踩了一连串由于 **Windows 操作系统底层机制** 和 **MCP 协议实现** 导致的严重死结，并逐一进行了重构：
>
> 1. **Windows 异步事件循环冲突（NotImplementedError）**：
>    * **问题**：Uvicorn 开启热重载（`--reload`）时，在 Windows 上会强行把 Python 事件循环修改为 `SelectorEventLoop`（以适配 `watchfiles`）。然而这个循环在 Windows 上**完全不支持子进程管道**。一旦启动 stdio 形式的 MCP 子进程，底层 `CreateProcess` 就会抛出 `NotImplementedError` 崩溃。
>    * **解决**：我设计了一个 **Proactor 线程异步桥接器**——在 `app.mcp.client` 中拦截该情况，检测到 `_WindowsSelectorEventLoop` 时，自动在后台拉起一个带有原生 `ProactorEventLoop` 的独立守护线程执行子进程通信，再利用标准库的 `asyncio.wrap_future` 将结果无缝、非阻塞地桥接回主线程。
>
> 2. **Windows 下的可执行文件找不到（FileNotFoundError）**：
>    * **问题**：在 Windows 上，`npx` 实际是批处理脚本 `npx.cmd`。Python 底层的 `subprocess.Popen` 在 `shell=False` 时不会自动补全 `.cmd` 导致找不到文件。
>    * **解决**：在 Stdio 参数解析中，我引入 `shutil.which`。如果是 Windows 系统，自动利用 `PATHEXT` 找到带有 `.cmd` 后缀的**完整绝对路径**并替换命令，确保子进程能成功创建。
>
> 3. **npx 每次启动更新检查导致 40 秒严重挂起**：
>    * **问题**：Windows 下运行 `npx -y` 启动 MCP 时，npm 每次都会联网查询最新版本并在 NTFS 上解压成千上万个碎文件，导致前端界面卡死 40 秒之久。
>    * **解决**：我在 Stdio 参数拼装中实现参数拦截，检测到 Windows + npx 运行时，自动在参数最前面插入 **`--prefer-offline`**。告诉 npm 强制优先使用本地 node 缓存，**启动速度瞬间从 40 秒直接缩短到 0.8 秒**。
>
> 4. **MCP 初始化阶段的反向请求死锁（Request timed out）**：
>    * **问题**：某些官方 MCP Server（如 `@modelcontextprotocol/server-filesystem`）在被初始化握手时，会主动向客户端反向请求 `client/roots`（Roots 列表）。因为我们的 `ClientSession` 初始没有配置对该请求的处理，导致双方在 `initialize()` 阶段互相死等 60 秒直至超时崩溃。
>    * **解决**：我将 `mcp` SDK 从 `1.1.0` 升级至 `1.2.0+`（以支持 roots 回调注册），并在实例化时注入一个默认的 **`_default_list_roots` 异步回调**，一旦服务端发起请求，秒回一个空列表 `roots=[]` 证明客户端无本地 workspace。**初始化瞬间解除死锁，1 秒内绿色秒通**。"

**追问：在这个统一工具池下，有没有什么典型的多轮协作和纠错场景？**

> "有一个非常惊艳的 **安全沙箱与自我纠错（Self-Correction）** 案例：
> 
> 在我们的 `Tool Agent` 统一工具池中（包含 4 内部、5 Skill 和 40 远程 MCP 工具），我们接入了官方的 Filesystem MCP 并限定了安全沙箱范围为 `C:\Users\86191\Desktop\mcp-test`。
> 
> 用户说：*『帮我查询东京天气、生成旅行规划并保存为 trip.txt』*。
> 
> 1. **初始行动**：大模型第一步调用 `TravelPlannerSkill` 生成了精美规划。在第二步尝试保存文件时，大模型基于本能直觉，调用 `write_file` 尝试写入用户的 **Windows 桌面根目录**（`C:\Users\86191\Desktop\trip.txt`）。
> 2. **沙箱报错**：因为超出我们限制的沙箱范围，MCP Server 直接给模型返回了 `Access Denied` 报错。
> 3. **主动搜证与纠错**：模型没有崩溃，而是展示了极高的 Self-Correction 能力：它拦截了报错，**主动转而调用 `list_allowed_directories` 探测工具**，去问系统『到底哪些路径是被允许写入的？』。
> 4. **自愈与降级**：查到被允许写入的只有沙箱 `mcp-test` 后，模型自动修正了参数，将路径组装为 `mcp-test/trip.txt` 重新发起 `write_file` 成功落盘。并最终在前端输出友好提示向用户解释了权限受限并已安全降级写入的情况。
> 
> 这个案例向面试官有力证明了：**第一，我平台具备严密的安全隔离沙箱；第二，在 49 个工具的超大动作空间和安全边界下，我的 Agent 具备极强的防御性编程意识、环境感知能力和自动容错自愈能力。**
>
> 另外我还做了一个改进：跨轮上下文会携带上一轮的工具调用摘要（成功和失败记录）。这样如果用户事后问'你刚才有遇到什么问题吗'，Agent 能在上下文里看到之前的错误记录并如实回答，而不是只看到最终成功的回复文本就回答'没问题'。这是对齐了 ChatGPT 等主流做法——工具调用记录作为完整消息保留在对话历史中。"

---

## 第六轮：L2 语义事实记忆系统

### Q19：三层记忆体系是什么？为什么要分三层？

**答**：

> "我设计了三层记忆体系来解决不同时间跨度和粒度的上下文管理：
>
> - **L1 对话摘要**：当前会话的短期记忆。消息超过阈值后触发 LLM 压缩为摘要，保留最近对话 + 摘要作为上下文窗口。解决的是单次会话内的上下文长度限制问题。
> - **L2 语义事实记忆**：跨会话的长期记忆。从对话中异步抽取结构化事实（错误教训、环境约束、用户偏好、业务知识），存入 PostgreSQL + ChromaDB 向量库。每次新对话开始时，通过语义检索召回最相关的历史事实注入上下文。解决的是「Agent 跨会话遗忘」问题——比如同一个错误不应该犯两次。
> - **L3 RAG 知识库**：外部知识的持久化存储。用户上传文档，经分块、向量化后存入知识库，通过 RAG 双路召回检索。解决的是 LLM 缺乏私有领域知识的问题。
>
> 三层分别覆盖了**会话内**（分钟级）、**跨会话**（天/周级）、**持久知识**（永久）三个时间维度，互不干扰、各司其职。"

### Q20：L2 记忆是怎么抽取的？四种类型怎么分的？

**答**：

> "抽取是异步的，不阻塞主对话流程。有三个触发时机：
>
> 1. **每轮对话结束后（即时抽取）**：用专门的严格 prompt 只抽取高价值信息——用户身份、持久性偏好、对 AI 的纠正反馈。大部分普通对话返回空数组，不产生记忆。解决的是短对话中关键信息丢失的问题
> 2. **工具调用出错时**：立即启动后台线程，把错误上下文喂给 LLM，抽取 `error_lesson`（错误教训）
> 3. **对话摘要压缩时（批量抽取）**：把即将被归档的消息喂给 LLM，用更宽泛的 prompt 批量抽取 `env_constraint`（环境约束）、`preference`（用户偏好）、`knowledge`（业务知识）
>
> 即时抽取和批量抽取用的是不同的 prompt：即时版只关注身份/指令/纠正三类，避免把一次性操作指令当偏好存；批量版更全面，也会提取环境信息和业务知识。两者的结果都经过语义去重（余弦距离 < 0.15 自动合并），不会重复存储。
>
> 四种类型的分工：
> - `error_lesson`：'写文件前必须检查目录存在'——避免重复犯错
> - `env_constraint`：'服务器为 CentOS7 4核8G'——适应环境差异
> - `preference`：'用户偏好中文回答'——贴合习惯
> - `knowledge`：'前端部署在 5173 端口'——积累项目知识
>
> LLM 输出 JSON 结构化格式，包含 content、fact_type、importance（0-1 重要性评分）。代码端用 Pydantic 校验并持久化。"

**追问：为什么用后台线程而不是 Celery？**
> "记忆抽取是轻量级任务（单次 LLM 调用），不需要 Celery 的任务队列和重试机制。用 `threading.Thread(daemon=True)` 足够，避免增加基础设施复杂度。但为了线程安全，我在新线程里创建独立的数据库 Session，通过传递消息 ID 而不是 ORM 对象来避免跨线程 Session 共享问题。"

### Q21：多知识库场景下怎么防止记忆上下文污染？⭐

**答**：

> "核心机制是给每条记忆打 `kb_id` 标签。保存时，记忆关联到当前会话绑定的知识库；检索时，按 `user_id + kb_id` 范围过滤——只返回全局记忆（`kb_id=NULL`）和当前知识库专属记忆（`kb_id=当前kb`）。
>
> 举个例子：用户有两个知识库，项目 A 的环境是 CentOS7，项目 B 是 Ubuntu22。Agent 回答项目 B 的问题时，不会把'CentOS7'这条环境约束注入进去——因为它的 `kb_id` 指向项目 A，被过滤掉了。
>
> 但 `preference` 类型（用户偏好）是全局的，`kb_id=NULL`，任何知识库场景都能检索到——因为'用户偏好中文回答'这种信息跨项目通用。"

**追问：ChromaDB 不支持 NULL 过滤怎么办？**
> "ChromaDB 的 metadata where 条件不支持 NULL 值。我在存储时把 `kb_id=None` 转为 `-1`，检索时构造 `$or` 条件——`kb_id == -1`（全局）或 `kb_id == 当前kb_id`。这是适配层的处理，业务层面完全透明。"

### Q22：记忆衰减淘汰机制是怎么设计的？⭐

**答**：

> "模拟人类记忆的'用进废退'原理，在每次检索后自动执行轻量级衰减淘汰，分三个阶段：
>
> 1. **自动删除**：超过 60 天未访问且 importance < 0.3 的记忆直接删除——已经衰减到极低价值的过期记忆
> 2. **时间衰减**：超过 30 天未访问的记忆降低 importance，衰减幅度根据 `access_count` 动态调节：
>    - 从未被引用 → 每次 -0.15（衰减快）
>    - 引用 1~3 次 → 每次 -0.10（正常衰减）
>    - 引用 4~9 次 → 每次 -0.05（衰减慢）
>    - 引用 ≥10 次 → 每次 -0.02（衰减极慢但仍会衰减）
> 3. **容量淘汰**：每个 user + kb 维度最多 50 条，超出时按 importance 最低的先淘汰
>
> 关键设计决策：**没有任何记忆是永久免疫的**。早期版本有 `access_count >= 2` 的豁免机制，后来去掉了——因为一条记忆可能早期被引用过 2 次后再也没用过，变成'僵尸记忆'占用容量。改为动态衰减幅度后，高频使用的记忆寿命更长但不是不死，更符合真实记忆模型。"

**追问：衰减只在检索时触发，用户长期不用不会静默清理吗？**
> "对，这是设计意图。如果用户 3 个月不登录，记忆不会在后台悄悄消失。只有用户回来聊天触发检索时才执行清理。避免用户长期不用后回来发现记忆全没了的糟糕体验。"

### Q23：记忆检索的具体流程是什么？怎么排序的？

**答**：

> "检索流程分四步：
>
> 1. **向量召回**：把用户输入 embedding 后，在 ChromaDB 中按 `user_id + kb_id` 范围过滤，取 top-10 候选
> 2. **关联度过滤**：余弦距离超过 0.7 的候选直接过滤掉（太不相关了）
> 3. **加权重排**：综合考虑语义相似度（距离越小越好）和 importance（越高越好），加权计算最终得分排序
> 4. **取 top-k**：默认取前 3 条注入上下文，同时更新这些记忆的 `last_accessed_at` 和 `access_count`
>
> 注入方式是作为 system 消息写入上下文：'以下是从你的历史执行经验中检索到的最相关的记忆，请作为强力参考规则'。这样 LLM 会把它当作高优先级的指导信息。"

### Q24：整个记忆系统在 Agent 管道里的位置是哪？

**答**：

> "在 LangGraph 状态机的最前端。执行顺序是：
> ```
> context_prep_node → router → rag_agent / tool_agent / fallback
> ```
> `context_prep_node` 是统一的上下文准备中间件，职责包括：注入当前时间、从 L2 记忆库检索相关事实、注入对话历史摘要、拼装用户输入。所有下游节点直接从 `state.context_messages` 读取，不需要关心上下文怎么来的——这是中间件/拦截器模式的设计。
>
> 记忆写入则是异步的，在 `chat_service` 层触发，不在 LangGraph 图内。这样记忆的读写完全解耦：读在图内同步执行保证时效，写在图外异步执行不阻塞响应。"

---

## 第七轮：AI 基础理论高频题

### Q25：为什么选 RAG 不选微调（Fine-tuning）？⭐ 必考题

**答**：

> "两者解决的问题不同：
>
> - **微调**：改变模型的行为模式或风格（如让模型输出特定格式、学会某种语气、掌握某个垂直领域的推理方式）。本质是修改模型权重。
> - **RAG**：给模型补充它不知道的外部知识（如公司内部文档、最新数据）。本质是修改模型的输入。
>
> 我选 RAG 的原因：
> 1. **知识时效性**：用户上传新文档后立刻可用，微调需要重新训练，周期长
> 2. **可解释性**：RAG 能标注引用来源（我做了引用高亮），微调后模型说的话你不知道来源
> 3. **成本**：微调需要 GPU 算力和标注数据，RAG 只需要调 embedding API
> 4. **幻觉控制**：RAG 可以通过检索结果约束模型回答范围，微调后模型仍可能编造
>
> 但 RAG 不是万能的——如果需求是让模型学会一种新的推理能力（比如法律条文之间的逻辑推理），那微调更合适。RAG 只能提供知识，不能教会模型新的思维方式。"

**追问：能不能两个一起用？**
> "可以，业界叫 RAG + Fine-tuning 混合方案。先微调让模型适应特定领域的表达风格和推理模式，再用 RAG 注入最新知识。但这对中小团队来说投入产出比不高，除非是对准确率要求极高的场景（如医疗、法律）。"

### Q26：Embedding 是什么？原理是什么？

**答**：

> "Embedding 是把文本映射成一个高维向量（如 1536 维），使得语义相似的文本在向量空间中距离更近。
>
> 原理是用预训练的神经网络（如 BERT 家族）把输入文本编码为固定长度的向量。训练时用对比学习——让同义句的向量靠近、不相关句子的向量远离。推理时直接取模型某一层的输出作为向量表示。
>
> 在我的项目里用了两种 Embedding：
> - **通义 text-embedding-v4**：用于 RAG 文档向量化和查询向量化，1024 维
> - **同一个模型也用于 L2 记忆的向量化**：存入 ChromaDB 后按余弦距离检索
>
> 关键理解：Embedding 不是关键词匹配，而是语义匹配——'如何部署'和'怎么上线'虽然没有共同关键词，但向量距离很近。这就是为什么向量检索能补充 BM25 关键词检索做不到的事。"

**追问：Bi-Encoder 和 Cross-Encoder 有什么区别？**
> "Bi-Encoder（双塔）：query 和 document 各自独立编码成向量再算距离。优点是 document 向量可以提前算好存入向量库，查询时只需要编码 query + 近似最近邻搜索，毫秒级。缺点是 query 和 document 之间没有交互，精度一般。
>
> Cross-Encoder（交叉编码）：把 query 和 document 拼在一起输入 BERT，模型能看到两者的细粒度交互（如词级别的对齐）。精度高但不能预计算，每个 query-document 对都要跑一次模型，只适合对少量候选做精排。
>
> 所以典型 RAG 管道是：Bi-Encoder 做粗召回（快）→ Cross-Encoder 做精排（准）→ LLM 生成答案。我的项目完整实现了这个管道——向量+BM25 双路 RRF 融合粗召回 top_k=15，再用 gte-rerank-v2（Cross-Encoder）精排取 top_n=6 给 LLM。"

### Q27：Temperature 和 Top-p 是什么？你项目里怎么设的？

**答**：

> "两者都控制 LLM 输出的随机性：
>
> - **Temperature**：调节 token 概率分布的平滑度。T=0 时永远选概率最高的 token（确定性输出），T 越高分布越平坦，越可能选到低概率 token（更有创意但也更可能胡说）
> - **Top-p（nucleus sampling）**：只从累积概率达到 p 的最小 token 集合中采样。p=0.1 只从最高概率的少数 token 里选，p=1.0 从所有 token 里选
>
> 我项目里的设置：
> - **Router 分类**：temperature=0，需要确定性判断走 rag/tool/chitchat
> - **Query Rewrite**：temperature=0，改写必须稳定可复现
> - **RAG 回答**：temperature=0.3，轻微创意但以忠实检索结果为主
> - **闲聊 Fallback**：temperature=0.7，更自然有趣
> - **记忆抽取**：temperature=0，结构化 JSON 输出必须确定性"

**追问：Temperature=0 和 Temperature=0.01 有区别吗？**
> "理论上有。T=0 是 greedy decoding（贪心解码），永远选 argmax，完全确定性。T=0.01 仍然是采样，只是分布非常尖锐，99.9% 情况下结果相同但极低概率会选到第二名 token。实际工程中差别可以忽略，但如果你需要严格可复现（如 CI 测试），用 T=0。"

### Q28：Token 和 BPE 分词是什么？

**答**：

> "LLM 不直接处理文字，而是把文本切成 token（词元）再处理。Token 可以是一个完整的词、一个词的一部分、一个标点，甚至一个中文字。
>
> BPE（Byte Pair Encoding）是最常用的分词算法：
> 1. 初始把每个字符作为一个 token
> 2. 统计所有相邻 token 对的出现频率
> 3. 把最高频的 token 对合并成一个新 token
> 4. 重复直到词表大小达到预设值（如 GPT-4 是 100k+）
>
> 结果是高频词（如 'the'）变成一个 token，低频词（如 'NexusAI'）被拆成多个子词 token。中文通常一个字就是一个 token。
>
> 在我的项目里，用 tiktoken 库计算 token 数来判断对话是否需要触发摘要压缩——超过阈值就启动 L1 摘要，避免上下文溢出。"

### Q29：Function Calling 的原理是什么？和普通 Prompt 有什么区别？

**答**：

> "Function Calling 不是模型真的'调用'了函数——模型只是输出了一段结构化的 JSON，表示'我想调用这个函数，参数是这些'。真正的函数执行是我们的代码做的。
>
> 流程：
> 1. 开发者在 API 请求中定义可用函数的 schema（名称、参数、描述）
> 2. 模型根据用户输入判断是否需要调用函数，输出 function_call JSON
> 3. 我们的代码解析 JSON，执行实际函数，拿到结果
> 4. 把结果作为 tool message 回传给模型，模型据此生成最终回答
>
> 和普通 Prompt 的区别：
> - Prompt 方式：'如果用户问天气，请输出 JSON 格式 {"tool": "weather", "city": "xx"}'——模型可能输出格式不对、幻觉、加多余文字
> - Function Calling：模型原生支持结构化输出，格式稳定，有专门的 stop reason 标识'我要调用函数'
>
> 在我的项目里，Tool Agent 就是基于 Function Calling 实现的——把内部工具 + Skill + MCP 外部工具（从数据库缓存读取）的 schema 统一传给模型，模型自主选择调用哪个。MCP 子工具在创建时就已预缓存到 PostgreSQL，运行时直接读 DB 拼装 schema，不发起任何外部连接。"

---

## 第八轮：Supervisor 动态调度 + MCP 缓存架构

### Q30：Supervisor 是怎么做任务规划的？和 Router 什么关系？⭐

**答**：

> "Supervisor 是多 Agent 协作的调度中心，基于 LLM 动态规划。整个流程分两个阶段：
>
> **规划阶段**（首轮 iterations=0）：把用户请求 + 可用能力清单（RAG Agent、Tool Agent 的 Skills 和 MCP 服务描述）注入 prompt，LLM 输出一个 JSON，包含 `task_plan`（步骤列表）和第一步要分发到的 `next_agent`。每个步骤有 `step_id`、`description`、`agent`、`status` 字段。如果是闲聊或简单问答，LLM 判断不需要子 Agent，直接输出 `direct_response` 自己回答。
>
> **执行阶段**（后续轮）：子 Agent 完成后，Supervisor 拿到执行结果，LLM 判断是按原计划继续下一步、还是需要调整计划（比如前一步失败了要换方案），输出更新后的 `task_plan` 和下一个 `next_agent`，或者输出 `FINISH` 表示全部完成。
>
> 和 Router 的关系：Router 是**单步意图分类器**的设计思路，只看当前这一句话该走哪个 Agent；Supervisor 是**多步任务编排器**，能把复合请求拆成多步计划依次执行。比如用户说'查天气然后写入文件'，Router 只能选一个方向，而 Supervisor 能拆成两步分别派给 Tool Agent。**目前系统只用 Supervisor**——它既负责意图分类（闲聊直接回答），也负责多步规划（复合请求拆解）。Router 节点代码保留但未接入主流程，作为未来轻量化分流的备选方案。"

**追问：task_plan 前端怎么展示的？**
> "通过 SSE 的 `meta` 事件实时推送 `task_plan` 给前端。前端的 ThinkingTrace 面板会渲染成一个 Pipeline 视图——每个步骤显示描述、目标 Agent、执行状态（pending/running/done/failed）。用户能实时看到当前执行到哪一步，哪些步骤已完成。task_plan 还会持久化到 LocalStorage，刷新页面后仍可查看。"

**追问：Supervisor 最多循环几次？超了怎么办？**
> "硬限制 `MAX_ITERATIONS=5`。超过后强制输出 FINISH，把已完成的步骤结果汇总返回给用户，未完成的步骤标记为 `skipped`。这是防止 LLM 反复调整计划导致死循环的兜底机制。"

### Q31：MCP 工具为什么不实时连接？缓存用 PostgreSQL 而不是 Redis？⭐

**答**：

> "这是一个性能瓶颈驱动的架构决策。最初 Tool Agent 每次运行时都会实时连接外部 MCP Server 拉取工具列表——如果是 stdio 类型（比如 `npx -y @modelcontextprotocol/server-github`），每次都要启动一个 Node.js 子进程、npm 检查更新、解压 node_modules，在 Windows 上耗时 3-40 秒不等。这意味着用户发一句话，光 MCP 工具加载就要卡好几秒，体验不可接受。
>
> 解决方案是**创建时预缓存 + 运行时只读 DB**：
> 1. 用户在前端新建 MCP 配置时，点击'测试连接'会触发一次实时连接，拉取全部子工具的 name、description、inputSchema，写入 `mcp_server_configs` 表的 `cached_tools` JSON 字段
> 2. 同时 LLM 根据子工具列表生成一句整体功能描述（30-80 字），写入 `description` 字段
> 3. 运行时 Supervisor 读 `description` 做规划，Tool Agent 读 `cached_tools` 拼装 Function Calling schema，全程只查 PostgreSQL，0ms 级别
> 4. 用户需要更新时，前端有'强制刷新'按钮重新连接并覆盖缓存"

**追问：为什么不用 Redis？**
> "因为这个场景不需要 Redis 的特性。MCP 配置是低频写入（创建/刷新时才写）、中频读取（每次对话加载一次），数据量极小（每个用户几条记录）。PostgreSQL 的单行主键查询本身就是亚毫秒级，而且数据需要持久化（重启不能丢）、需要和 `MCPServerConfig` 模型的其他字段（name、connection_uri 等）在同一个事务里管理。引入 Redis 反而增加了一层缓存一致性问题和运维复杂度，对这个场景是过度设计。"

**追问：缓存会不会过期？外部 Server 更新了工具怎么办？**
> "缓存没有自动过期机制，因为 MCP Server 的工具列表通常是稳定的（版本不变就不会变）。如果外部 Server 升级了，用户在管理页点击'强制刷新'按钮即可——后端会重新连接外部 Server、拉取最新工具列表、覆盖 `cached_tools` 和 `tool_count`，并返回新列表给前端展示。这是**显式刷新**而非**隐式过期**的设计——用户对缓存状态有完全的控制权和可见性。"

### Q32：LLM 生成 MCP 描述的 prompt 是怎么设计的？质量怎么保证？

**答**：

> "prompt 的核心约束是：输入 MCP 服务名 + 全部子工具列表（名称和描述），输出一句 30-80 字的中文整体功能概述。要求精准概括该服务能做什么，不要列举每个工具，而是抽象到能力层面。
>
> 比如 GitHub MCP 有 26 个子工具（create_issue、get_pull_request、search_repos 等），LLM 生成的描述可能是：'GitHub 代码仓库管理服务，支持仓库搜索、Issue/PR 管理、代码文件读写、分支操作等 GitHub API 全功能集成'。
>
> 质量保证靠三层：
> 1. **prompt 约束**：明确字数范围、语言、风格要求，用 `temperature=0` 保证确定性
> 2. **用户可编辑**：LLM 生成后自动填入描述输入框，用户可以手动修改再保存
> 3. **随时重新生成**：管理页支持点击'AI 重新总结'按钮，基于当前缓存的子工具列表重新调用 LLM 生成
>
> 用的是 `get_llm_fast`（轻量模型），不是主力模型，因为这个任务不需要太强的推理能力，快速响应更重要。"

### Q33：Supervisor 怎么知道有哪些 MCP 可用？信息从哪来？

**答**：

> "Supervisor 在规划阶段调用 `_get_mcp_info(user_id)`，这个函数直接查 PostgreSQL——`SELECT name, description FROM mcp_server_configs WHERE created_by=用户ID AND is_active=True`。返回一个 `[{name, description}]` 列表。
>
> 然后在 `_build_planning_prompt` 里动态拼接到 prompt 中，格式类似：`外部工具(MCP)：GitHub(GitHub 代码仓库管理服务...)、Filesystem(本地文件系统读写服务...)`。这样 LLM 就能像看到内部 Skill 一样看到外部 MCP 的能力描述，在规划 task_plan 时决定是否需要调用。
>
> 关键点：这个函数**不发起任何网络连接或子进程**，只是一次简单的 DB 查询。即使用户配了 10 个 MCP Server，查询耗时也不到 1ms。如果某个 MCP 没有描述（description 为空），它仍然会出现在列表里，只是 LLM 只能看到名称，可能无法准确判断它的用途——所以我们在前端强烈建议用户添加描述。"

**⚠️ 注意**：面试时不要说"Supervisor 会去连接 MCP Server"——它根本不会。所有 MCP 信息都是从数据库读的，连接只发生在用户创建/刷新时。这个区分体现了你对**读写分离**和**性能优化**的理解。

---

## 第九轮：多步任务执行优化 + LLM 分级策略

### Q34：多步任务是怎么实现步骤隔离的？遇到过什么问题？⭐

**答**：

> "这是一个实际踩坑后修复的问题。Supervisor 把'搜索 + 写文件'拆成两步 task_plan 是正确的，Graph 结构也支持 Supervisor → Tool Agent → Supervisor 循环。但实际运行时，Step 1 的 Tool Agent 在一次 FC 循环里把两步全做了——搜完直接写文件，Supervisor 回来发现全做完了就直接 finish。
>
> **根因**：Tool Agent 的 messages 里同时包含了原始用户消息（'帮我搜索 X 信息并写入文件'）和 Supervisor 指令（'搜索 X 信息'）。LLM 看到用户原始请求后优先满足完整意图，忽略了 Supervisor 的步骤指令。
>
> **修复**：当存在 supervisor_instruction 时，不注入 context_messages（原始用户消息），Tool Agent 只看到 system prompt + 上一步结果 + 当前步骤指令。这样每步 Tool Agent 只做被分配的任务，真正走多轮 Graph 循环。
>
> **效果**：执行链路从 `supervisor → tool_agent → supervisor`（1 次）变成 `supervisor → tool_agent → supervisor → tool_agent → supervisor`（2 次循环），每步的工具调用独立记录，前端按步骤分别展示。"

**追问：工具调用怎么按步骤区分？**

> "后端 `ToolCallRecord` 加了 `step` 字段，Tool Agent 执行前从 `task_plan` 里找到当前 `in_progress` 的步骤编号，给每条记录打上标记。同时 `tool_calls` 改为累积式——每次 Tool Agent 执行后追加到已有列表上，不覆盖上一步的记录。前端用 computed 按 step 分组，每个步骤卡片只展示自己的工具调用和数量。"

**追问：上一步的结果怎么传给下一步？**

> "Tool Agent 执行完后 `final_answer` 写入 state，下一步的 Tool Agent 通过 `existing_answer` 读取。以 assistant 消息注入 messages，截取前 6000 字符避免 context 过大。Supervisor 的 dispatch 指令里也会描述上一步做了什么，LLM 能理解当前应该做什么。"

### Q35：为什么全链路都用 Fast 模型？不怕推理能力不够吗？

**答**：

> "系统里有两个模型：Pro（deepseek-v4-pro，推理能力强但慢，单次调用 20-25 秒）和 Fast（flash 模型，快但推理弱一些，单次调用 3-5 秒）。
>
> 实际上 **Supervisor、Tool Agent、Router、RAG Agent 全部用的是 Fast 模型**。原因是这些节点的任务本质上都是'看到上下文 + 指令，输出结构化 JSON'——这是结构化输出任务，不需要深度推理。工具/Skill 的名称和描述已经很明确了，Fast 模型完全能准确匹配。
>
> **分级策略总结**：
> - **Pro 模型**：仅用于部分复杂 Skills（如 document_summarizer 长文档摘要、email_drafter 邮件生成）和对话摘要压缩——这些场景需要更强的理解和生成能力
> - **Fast 模型**：Supervisor 任务规划、Router 意图分类、Tool Agent FC 循环、RAG Agent 回答生成
>
> 这样设计的核心考量是**响应速度优先**。多步任务里 Tool Agent 会被调用多次，每次 FC 循环至少 2 次 LLM 调用，用 Fast 模型节省的时间是乘法级别的。如果未来发现 Fast 模型在复杂规划场景准确率下降，可以单独把 Supervisor 升级为 Pro 模型。"

### Q36：research_assistant Skill 为什么去掉了 RAG 搜索？

**答**：

> "最初设计是'web 搜索 + 可选 RAG'——如果会话关联了知识库就同时查 KB。但实际使用发现一个问题：用户说'帮我调研 ReAct 框架'，这明显是互联网调研需求，但因为会话有关联的知识库（可能是完全不相关的内容），Skill 还是会对每个搜索关键词都做一次 RAG 检索。浪费了时间，也可能把无关的内部文档混入报告。
>
> **重构思路**是职责单一化：
> - `research_assistant`：纯互联网搜索 + LLM 综合报告（多关键词并行搜索 + 去重 + 带引用报告）
> - `document_summarizer`：纯 KB 检索 + 总结（multi-query RAG + LLM 摘要）
>
> 如果用户需要'结合互联网和内部知识库'的综合调研，Supervisor 会拆成多步：Step 1 用 `research_assistant` 搜互联网，Step 2 用 `document_summarizer` 查 KB，由 Supervisor 综合两步结果回答。这样每个 Skill 职责清晰，不会互相干扰，也契合了多步任务编排的架构优势。"

**⚠️ 注意**：这个问题可能会被追问"你怎么发现的这个问题？"——答：通过日志分析发现 `rag_search` 的调用出现在纯互联网搜索场景里，查看 Skill 代码发现是 `kb_id is not None` 就必查的逻辑。属于功能设计和实际使用场景不匹配。

### Q37：在全局总结或多领域对比（如对比十个行业挑战、对比四个行业未来态）的宏观查询下，你的 Reranker 精排取 Top-6（`RERANK_TOP_N=6`）会不会导致关键信息丢失？如果发生了这种物理截断，你是怎么在工程上优雅解决的？⭐

**答**：

> "这是我在对系统进行高强度压力测试（Stress Test）时，真实遇到并定位解决的一个**关于 Reranker（精排器）在‘多主体/全局汇总’意图下的物理截断缺陷**。
> 
> **1. 现象与排查**：
> 在要求系统‘对比自动驾驶、农业、工业、电网这四个行业未来的终极形态’时，大模型完美答对了前三个，但对于第四个电网，却在没有原文背景的情况下依靠自身的‘逻辑泛化能力’进行了假装类比推断。
> 我去翻了系统的运行追踪日志（Trace Log），发现大模型的 Prompt 限制极其严密（没有幻觉乱编），且第一阶段的向量+BM25双路检索成功粗筛召回了包含电网内容的 Top-15。
> **根因在于**：因为我平时将精排限制为 `RERANK_TOP_N = 6`。在面对多实体对比时，前三个行业的 Chunks 抢占了精排得分的前 6 名，导致第四个行业的 Chunks（即使语义十分相关）由于第 6 名的物理限制，在精排阶段被无情地截断（丢弃）了。
> 
> **2. 系统级优化与解决思路**：
> 我没有盲目地去修改 Prompt，而是从**检索路由与数据链路层**设计了三套优雅的渐进式解决方案：
> 
> *   **方案一：动态重排窗口（Dynamic Rerank Window）**：
>     In Supervisor 任务规划节点中，一旦大模型检测到当前用户的 Query 属于‘多实体对比、全局汇总、全景梳理’等宏观意图，系统在分发任务给 RAG Agent 时，会自动将 `RERANK_TOP_N` 的精排上限从 6 动态放宽到 12。
> *   **方案二：多路并行检索与 Reduce 合并（Parallel Multi-Query & Reduce）**：
>     如果对比的主体非常明确，由 Agent 将查询拆分为 4 个独立的子查询（如分别单独检索‘农业未来态’、‘电网未来态’），每个子查询各自捞取 Top-3，最后将 12 个强相关的 Chunks 拼装成上下文。这利用了 **MapReduce** 的思想，彻底消除了单路 Reranker 的打分偏见。
> *   **方案三：分层级章节索引（Hierarchical Summary Indexing）**：
>     对于通篇总结任务，优先检索在向量库中提前保存好的‘小章节/大章节 Summary’。利用 Summary 定位到具体实体和章节后，再去检索其底层的 Child Chunks 进行细节补充，避免了在细碎 Chunks 层面由于 Top-K 限制导致的主体丢失。
> 
> 这个调优经历有力证明了：**我不仅能实现高阶 RAG 管道，而且深刻理解双塔/交叉编码器在不同业务场景下的局限性，并具备在工程链路层实现自适应调优的架构设计能力。**"

---

## 第十轮：LangGraph 选型 + State 设计

### Q38：为什么选 LangGraph？不用 CrewAI / AutoGen / 普通 LangChain Agent？⭐ 高频

**答**：

> "我对比过四种方案：
>
> - **普通 LangChain Agent**：基于 ReAct prompting，工具调用流程黑盒，没有显式的状态管理。多步任务里 LLM 经常忘记前面的执行结果，且不支持复杂的条件分支。
> - **CrewAI**：基于'多 Agent 角色扮演'抽象（每个 Agent 有 role/goal/backstory）。适合'多角色协作写文章'这种场景，但**对状态机和工程化控制不友好**——你很难精确控制谁先执行、共享什么数据。
> - **AutoGen**：微软出的，基于'Agent 之间对话'抽象，每个 Agent 是一个独立 LLM 实例。对于工程化的'确定性多步任务'来说过重，调试也困难。
> - **LangGraph**：基于**状态机**的明确抽象——节点是函数，边是路由，State 是共享内存。我的项目是'明确的多步流水线'（context_prep → supervisor → rag_agent / tool_agent → loop），LangGraph 是最贴合的工具。
>
> 选 LangGraph 的核心理由：**显式状态机 + 可观测的执行链路**。我用 `execution_trace` 字段记录每个节点的输入/输出/耗时，前端可视化整条执行链路。CrewAI 和 AutoGen 没有这种工程化的状态可观测性。"

**追问：LangGraph 的 checkpoint 你用了吗？为什么？**

> "**没用 checkpoint**。LangGraph 的 checkpoint 主要用于：①长任务断点续跑 ②人在回路（Human-in-the-Loop）。我的场景是'一次对话 = 一次 graph.invoke'，没有跨次复用的需求；多轮对话靠 session_id 在数据库层管理历史消息，比 checkpoint 更显式可控。如果未来要做'用户中途打断 + 继续'这种交互，再开 checkpoint 也不迟。"

### Q39：你的 AgentState 是怎么设计的？字段之间怎么合并？⭐

**答**：

> "AgentState 是一个 TypedDict，分六大组：
>
> 1. **输入**：user_input / session_id / user_id / kb_id
> 2. **上下文记忆**：summary（L1 摘要）/ messages（自动追加）/ context_messages（中间件统一打包）
> 3. **Supervisor 决策**：intent / route_reason / next_agent / supervisor_instruction / agent_iterations / **task_plan**（任务计划数组）/ step_contexts（每步上下文）
> 4. **RAG 结果**：retrieved_docs / faithfulness
> 5. **Tool 执行**：tool_calls（带 step 字段标记归属步骤）/ skill_used
> 6. **可观测性**：execution_trace / total_tokens / error
>
> 还有一个特殊字段 `_token_queue`，是流式推送用的 `queue.Queue` 对象——只在 SSE 模式下注入。"

**追问：LangGraph 是怎么合并多个节点对 State 的修改的？**

> "LangGraph 用 **reducer 机制**合并。每个节点 return 一个 partial dict，框架自动 merge 到主 State：
>
> - **默认行为**：直接覆盖
> - **特殊 reducer**：用 `Annotated[List, add_messages]` 标记的字段会**追加**而不是覆盖
>
> 我的 `messages` 字段就用了 `add_messages`，子 Agent 添加的消息自动累积。但 `execution_trace` 我**故意没用 reducer**——每个节点显式调用 `append_trace(state, ...)` 拼出完整新 list 返回，这样可以精确控制 trace 的格式和顺序，调试时更可控。"

**追问：为什么不用 LangChain 的 BaseMessage 而是普通 dict？**

> "两个原因：**第一**，BaseMessage 在不同节点间 pickle/JSON 序列化有兼容性坑（特别是 tool_calls 字段）；**第二**，纯 dict 直接对接 OpenAI Chat Completions API 格式，前端可视化、数据库持久化、日志打印都更方便。我宁可放弃 LangChain Message 的类型检查也要换来工程灵活性。"

---

## 第十一轮：Celery + 数据库 + 服务架构

### Q40：文档处理为什么用 Celery？不能直接 BackgroundTask 吗？⭐

**答**：

> "FastAPI 的 BackgroundTask 跑在 web 进程里，有三个致命缺陷：①web 进程重启会丢失任务 ②跟用户请求抢占 CPU/内存，并发上来 web 会卡 ③没有重试、超时、状态查询机制。
>
> 文档处理是典型的**重 I/O + 长耗时**任务：解析（几秒）→ LLM 清洗（几十秒）→ 分块 → 调通义向量化 API（千条 chunk 需要几十次 API 调用）→ 写 ChromaDB。一份 100MB 的 PDF 完整处理可能要 5-10 分钟。这种任务必须扔给独立 worker 进程异步跑。
>
> 我的实现是单个 Celery task `process_document(document_id, task_record_id)` 串行跑五个阶段，每阶段结束更新 `task_records` 表的 progress 字段（0/5/20/30/50/100）。前端轮询任务接口拿到实时进度。"

**追问：Broker 为什么选 Redis 不选 RabbitMQ？**

> "**Redis 当 broker 对中小项目就够了**。RabbitMQ 是为'高可靠性 + 复杂路由（exchange/binding）'设计的，比如需要 fanout 广播、topic 路由这种场景才有价值。我的任务模型很简单：单队列、串行执行、低 QPS（人工上传文档触发，每分钟几十个任务封顶）。
>
> Redis 的优势是**部署简单**——项目已经在用 Redis 做缓存和会话，broker 直接复用，部署只多两行配置（DB 1 当 broker、DB 2 当 result backend）。RabbitMQ 要额外起一个服务，对个人项目是过度工程。
>
> 如果未来扩到企业级，每天百万级文档任务，再换 RabbitMQ 不迟——Celery 的 broker 是配置项，业务代码完全无感。"

**追问：任务怎么保证幂等？失败了怎么重试？**

> "**幂等**：每个 task 拿 `document_id` 后第一件事是检查 document.status——如果已经是 COMPLETED 就直接返回，不重复处理。如果是 FAILED 重试时会清空已有 chunks 再重新跑。
>
> **重试**：Celery 配了 `autoretry_for=(ConnectionError,)` + `max_retries=2 + countdown=5`，**只对网络错误自动重试**。业务错误（如文件损坏、API 鉴权失败）不重试——立刻标记 FAILED，避免反复消耗 LLM token。
>
> **超时**：`task_soft_time_limit=600` 软超时抛异常，`task_time_limit=900` 硬超时直接 kill worker。防止单文档死循环卡住整个队列。
>
> **Worker 配置**：`worker_prefetch_multiplier=1` 让每个 worker 同时只拿 1 个任务，避免单 worker 吃多个任务时其他 worker 饿死。`task_acks_late=True` 让任务执行完再 ack，挂掉的任务会被重新分发。"

**追问：为什么用 `--pool=solo` 这种单线程模式？**

> "**Windows 上 Celery 5.x 默认的 prefork 模式不可用**——prefork 依赖 `fork()` 系统调用，Windows 没有。`solo` 是单线程模式，开发环境完全够用；生产部署 Linux 上会切到 prefork 或 gevent 模式。这是 Celery 的已知历史问题，部署文档里有注明。"

### Q41：为什么选 PostgreSQL 不选 MySQL？SQLAlchemy 怎么用的？

**答**：

> "选 PostgreSQL 的核心理由是**对 JSONB 的原生支持**。我有几个字段是 JSON 结构：MCP 的 `cached_tools`（每个 MCP 几十个工具的 schema）、ChatMessage 的 `tool_calls_json`、TaskRecord 的 `meta_json`。这些字段用 JSONB 存储 + 索引，比拆表关联快得多。MySQL 的 JSON 字段虽然也能用，但索引能力和函数支持都差一截。
>
> 另外 PostgreSQL 的 array 类型、partial index、CTE 等高级特性也是加分项。但日常使用差别不大，技术栈替换成本可控。
>
> **ORM 用 SQLAlchemy 2.0 + Alembic**：
> - SQLAlchemy 2.0 的新式 `Mapped[]` 类型标注让 IDE 类型提示完全到位
> - Alembic 自动生成迁移文件，每次改 model 跑 `alembic revision --autogenerate` 就行
> - **没用 ORM 的关联加载**：所有跨表查询都显式写 SQL（`db.query(Model).filter(...)`），避免 N+1 隐性陷阱"

**追问：怎么做用户数据隔离？**

> "我所有业务表（KnowledgeBase / Document / ChatSession / MCPServerConfig / MemoryFact）都有 `user_id` 外键。Service 层每个查询都强制带 `user_id` 过滤——比如 `KnowledgeBaseService.list(db, user_id=current_user.id)`。
>
> 防越权的关键是**不在 URL/Body 接收 user_id**：所有需要鉴权的接口从 JWT token 里解出 `current_user`，user_id 永远从服务端 session 取，避免前端篡改。比如查询知识库的接口是 `GET /api/kb/{kb_id}`，后端会校验 `kb.user_id == current_user.id`，不匹配直接 403。
>
> 不算严格意义的多租户（没用 schema 隔离），但对 SaaS 早期阶段够用。"

**追问：Alembic 迁移踩过什么坑？**

> "踩过两个坑：
>
> 1. **`enum` 类型修改要手写**：PostgreSQL 的 enum 不能直接 ALTER，必须 `ALTER TYPE ... ADD VALUE 'new'`。Alembic autogenerate 检测不出来 enum 变化，要手动加迁移逻辑。
>
> 2. **多 schema 同时改要分批**：一次 `autogenerate` 改了 5 张表的字段，结果某张表的外键约束依赖另一张表的新字段，迁移顺序错了会失败。改为每次改 1-2 张表，跑通再 commit。"

### Q42：做这个项目最难的部分是什么？踩了哪些坑成长最大？⭐ HR/Lead 必问

**答**（按"问题 - 解决 - 收获"三段式）：

> "最难的不是 RAG 本身，而是**把多个独立组件粘合成可观测、可调试的统一系统**。三个最痛的坑：
>
> **1. 同步 LangGraph + 异步 FastAPI 的桥接**（细节见 Q8/Q17）
> - 问题：LangGraph 的 invoke 是同步的，FastAPI StreamingResponse 需要 async generator
> - 我尝试过把所有节点改 async，但 LLM SDK 和数据库操作都是同步的，强行 async 化收益不大
> - 最终用 `asyncio.to_thread + queue.Queue` 做同步→异步桥接
> - **收获**：理解了 Python 协程/线程/进程的三层抽象，不再迷信 async 万能
>
> **2. Windows 上 stdio MCP 的死锁**（细节见 Q18）
> - 问题：Uvicorn 强制 SelectorEventLoop，但它在 Windows 上不支持子进程管道
> - 排查了一晚上才定位到是事件循环类型问题
> - 解决：Proactor 守护线程 + asyncio.wrap_future 桥接
> - **收获**：对操作系统底层（事件循环 / 子进程 / Windows 特殊性）有了真实理解
>
> **3. 多步任务里 Tool Agent 越权问题**（细节见 Q34）
> - 问题：Supervisor 拆成两步，Tool Agent 一次性把两步全做了
> - 根因是把原始用户消息和 Supervisor 指令一起喂给了 LLM
> - 修复：有 supervisor_instruction 时不注入 context_messages
> - **收获**：LLM 的'听话度'强依赖 prompt 中的信息层级，必须像写测试用例一样精确控制输入
>
> 整体最大的成长是：**把'用 LLM 写 demo'升级到'用 LLM 做工程'**。前者关注 prompt 调优，后者关注 fallback、超时、可观测、安全。这是质的飞跃。"

**追问：如果重做你会改什么？**

> "三件事：
>
> 1. **从一开始就上 LangSmith 或自建 trace 系统**——我的 execution_trace 是中后期才补的，前期排错全靠 print。
> 2. **建立评测集和 RAG 回归测试机制**——目前 RAG 改 prompt 全靠人肉测，没法量化对比。如果有评测集驱动，迭代会更快更稳。
> 3. **MCP 协议选择上**——一开始投入太多精力做 stdio，回头看 SSE / HTTP 形式部署和调试都更轻量。"

**追问：项目花了多久？怎么规划的？**

> "**两个月，我一个人独立完成**。前期一周做调研和架构图，中间六周编码（按周拆 milestone：RAG → Agent → 记忆 → MCP → 前端打磨），最后一周做评测和文档。
>
> 时间最大的失控点是 MCP 集成——预估 3 天，实际跑了 1 周（全是 Windows 坑）。教训是：**任何涉及子进程/操作系统底层的集成至少要预留 2-3 倍的 buffer**。"

---

## 第十二轮：横向选型对比 + 观测性

### Q43：ChromaDB vs Milvus vs Qdrant vs PGVector 怎么选？⭐ 必问

**答**：

> "我做了详细对比，最终选 ChromaDB。决策依据：
>
> | 项 | ChromaDB | Milvus | Qdrant | PGVector |
> |---|---|---|---|---|
> | 部署复杂度 | 单 Docker 容器 | 多组件（etcd+MinIO+多节点）| 单容器 | 数据库扩展 |
> | 性能 | 中（千万级前优秀）| 极强（亿级）| 强 | 中 |
> | Filtering | 简单 metadata where | 复杂表达式 | 类 SQL | 完整 SQL |
> | 适用规模 | 千~百万 chunk | 千万~亿 | 百万~千万 | 百万以内 |
> | 易用性 | 极简 Python SDK | 学习曲线陡 | API 优雅 | SQL 即用 |
>
> 我的项目场景是'每用户几个知识库，每库千~万级 chunk'，**ChromaDB 完全够用且部署最简**。Milvus 是工业级方案但起步复杂——光 etcd + MinIO + Milvus 主体就要起 5+ 容器，对个人项目过重。
>
> 上一个项目（找搭子）我用的是 Milvus，因为是 Spring Boot 全家桶，团队对 Java 容器化已经熟悉。这次个人项目优先速度迭代选 ChromaDB。"

**追问：为什么不直接用 PGVector？数据库已经有了**

> "考虑过。PGVector 的优势是和业务数据在同一个 PG 实例里，可以原生 JOIN。但有两个劣势：①索引重建时锁表（千万级 chunk 时影响业务）②不支持 HNSW 之外的高级索引算法。
>
> 我把'业务数据和向量数据解耦'当作主动设计——业务用 PG，向量用 ChromaDB，未来切换向量库（如升到 Milvus）只需改一个抽象层（我的 `BaseVectorStore` 接口），业务代码完全无感。"

### Q44：LLM 为什么选 DeepSeek？不选 OpenAI / Claude？

**答**：

> "**主要原因是成本和速度**：
>
> - DeepSeek v4 Flash：输入 $0.07/M tokens，输出 $0.27/M。中文场景下质量已经追平 GPT-4 Mini。延迟在国内 200-500ms。
> - DeepSeek v4 Pro：用于复杂 Skills 和摘要生成，质量接近 GPT-4
> - GPT-4 Turbo：输入 $10/M，输出 $30/M，是 DeepSeek 的 40-100 倍
> - Claude 3.5 Sonnet：质量最优，但国内访问需要代理，延迟和稳定性不可控
>
> 对一个'每对话可能调用 5-10 次 LLM'的 Agent 系统，成本差距是数量级的。**用 DeepSeek 我能在个人项目里跑出真正可用的 Agent，用 GPT-4 我连开发期都跑不起。**
>
> 设计上做了'模型分级'：Router/Supervisor/RAG 这种结构化输出任务用 Flash，document_summarizer 这种创造性任务用 Pro。详见 Q35。"

**追问：DeepSeek API 兼容 OpenAI 协议吗？**

> "**完全兼容**。DeepSeek 的 SDK 就是 `openai` Python 包，只改 `base_url` 和 `api_key` 两个参数。包括 Function Calling、streaming、JSON mode 都兼容。这意味着如果未来要切回 OpenAI 或换其他模型，业务代码不用动一行。"

### Q45：execution_trace 是怎么设计的？前端怎么消费？

**答**：

> "`execution_trace` 是一个 `List[TraceStep]`，每个 TraceStep 包含：
>
> ```python
> {
>   'node': str,           # 节点名（如 'supervisor', 'rag_agent'）
>   'started_at': float,   # 起始时间戳
>   'elapsed_ms': int,     # 耗时（毫秒）
>   'input': dict,         # 关键输入摘要（截断的）
>   'output': dict,        # 关键输出摘要
>   'error': Optional[str]
> }
> ```
>
> 每个节点执行结束时调 `append_trace(state, 'node_name', started_at, input_summary={...}, output_summary={...})`，返回一个新的完整 trace list（**不能直接 append 因为没用 reducer**）。
>
> 前端通过 SSE 的 `meta` 事件接收 task_plan 和实时执行信息，每个节点结束后追加显示。**ThinkingTrace 组件**渲染成一个 Pipeline 视图：每个节点显示名称、耗时、输入输出摘要、是否出错。前端还会把 trace 持久化到 LocalStorage，刷新页面后仍可查看。
>
> 这是我自建的'迷你版 LangSmith'——不需要外部服务，调试效率比 print 高一个数量级。"

**追问：日志怎么打？怎么排查 LLM 出错？**

> "用 loguru。每个节点开头打 `[NodeName] 开始 input={...}`，结束打 `[NodeName] 完成 output={...} tokens={...}`。LLM 调用包了一层 logger 装饰器，每次调用打 `[LLM] in={n_input_tokens} out={n_output_tokens} total={...}`。
>
> 出错排查三步走：①看 execution_trace 定位是哪个节点挂了 ②看 loguru 日志找到具体的 LLM 输出 ③把 LLM 输入 prompt 复制到对话窗口手动重跑，复现问题。99% 的 bug 都是 prompt 设计不严谨或 LLM 输出格式漂移。"

### Q46：测试策略是什么？写了多少测试？⭐ 容易被坑

**答**（**老实承认，别编**）：

> "**老实说，自动化测试覆盖率很低**。我写的主要是：
>
> 1. **关键工具的单元测试**：calculator 工具（防 eval 注入）、splitter 分块（防边界 bug）、embedder mock 模式（让测试不依赖外部 API）
> 2. **API 集成测试**：用 FastAPI 的 TestClient 写了 chat / kb / document 几个核心接口的冒烟测试
> 3. **RAG 端到端**：手工测试集，没自动化
>
> **没写**：LangGraph 节点的单元测试、SSE 流式的集成测试、L2 记忆抽取的回归测试。这是已知短板。
>
> 如果重做我会优先建两套东西：
> - **RAG 评测集**（人工标注 100 条 Q-A + ground truth chunk）+ 自动化跑 Recall@K
> - **Agent 行为回归**（用固定 seed 跑 task_plan 生成，对比是否一致）
>
> 这块面试如果被深挖，可以诚实说'测试体系是后期没做完的部分，我有清晰认知和补救计划'——比假装写过更可信。"

**⚠️ 教训**：测试问题千万别编"覆盖率 80%"，面试官追问"哪些模块没覆盖"或"展示一下 pytest 文件"会瞬间穿帮。

### Q47：怎么部署？数据量增长 100 倍系统能撑吗？

**答**：

> "**当前部署**：Docker Compose 一键起，5 个服务：
> - `backend`：FastAPI（gunicorn + 4 workers）
> - `worker`：Celery worker（solo pool 开发，prefork 生产）
> - `postgres`：PG 15
> - `redis`：缓存 + Celery broker
> - `chromadb`：HTTP server 模式
> - `frontend`：nginx 静态托管
>
> 每个服务都有 healthcheck，依赖通过 `depends_on: condition: service_healthy` 控制启动顺序。Volume 持久化关键数据（PG / ChromaDB / 上传文件）。
>
> **扩展性分析**：
>
> | 维度 | 当前 | 100 倍后 | 解法 |
> |---|---|---|---|
> | 用户量 | 100 | 10k | backend 横向扩展，nginx 负载均衡 |
> | 文档数 | 1k | 100k | Celery worker 增加，PG 加从库 |
> | Chunks | 100k | 10M | ChromaDB 单节点撑得住，但要换 Milvus 集群更稳 |
> | 并发对话 | 10 | 1000 | LLM API 限速是真瓶颈，可能要走多账号轮询 + 自建模型 |
>
> 真正的瓶颈不在我这边，而是 **LLM API 配额**。100 倍并发意味着 LLM 调用量也 100 倍，会被 DeepSeek 限速。最终解法是混合部署：高频简单任务用本地小模型（如 Qwen-7B），复杂任务才走云端 API。"

**追问：用过 Kubernetes 吗？**

> "**没用过 K8s 生产部署**。这个项目用 Docker Compose 已经够用了。K8s 适合多节点集群、滚动升级、自动扩缩容这些场景，对个人项目是过度工程。但我了解 K8s 的核心概念（Pod / Service / Ingress / HPA），如果未来加入团队需要也能快速上手。"

**⚠️ 教训**：没用过的东西就老实说没用过 + 加'但了解核心概念'+ '能快速上手'，比假装用过被追问细节穿帮强。

---

## 通用闲聊问题（HR / 技术 Lead 常问）

### Q48：为什么从全栈实习转 AI 方向？

> "实习期间做的 AI 问答助手让我体会到 LLM 能做的远不止'问答'——它是新一代的程序范式。所以业余时间自己学了 RAG、Agent、向量库，做了 NexusAI 这个项目作为系统性练习。我的优势是：**全栈底子让我能独立闭环（前端到部署），AI 视野让我能把 LLM 真正落到工程**——大部分 AI 工程师不懂工程化部署，大部分全栈不懂 AI 底层，我两边都有积累。"

### Q49：平时怎么学新东西？关注哪些资讯？

> "三个渠道：
> 1. **论文**：关注 ArXiv 上 RAG / Agent / LLM 系统相关的工作，比如 Anthropic 的 Contextual Retrieval、CMU 的 HyDE、IBM 的 ReAct
> 2. **工程博客**：Anthropic / LangChain / OpenAI 官方博客，HuggingFace 周报
> 3. **开源代码**：直接读 LangGraph / MCP SDK / Unstructured 这些库的源码——比看文档更能学到设计思路
>
> 最近在看的：Anthropic 的 Computer Use Agent 实现思路、Mem0 的长期记忆架构、OpenAI Realtime API 的语音对话设计。"

### Q50：你觉得自己的短板是什么？

> "三个：
> 1. **大规模分布式经验缺**——做过单机 / Docker Compose，没做过 K8s 集群和真正的高并发系统
> 2. **算法和数据结构底子比专业刷题选手弱**——能写常见算法但 LeetCode Hard 题比较吃力
> 3. **测试和 CI/CD 体系搭得不完善**——见 Q46
>
> 这些都是入职后可以快速补的'技能短板'，不是'认知短板'。"

**⚠️ 这道题千万别说'我没短板'或'我太追求完美'**。诚实承认 3 个具体短板 + 表达成长意愿，是最好的答法。

---

## 第十三轮：最近的实战故事（Bonus 题，强烈推荐主动讲）

### Q51：最近一次解决得最爽的技术问题是什么？⭐ 重点准备

> "上周给 Agent 加了 **Human-in-the-Loop 工具审批** ——MCP 工具是用户动态接入的，写文件、shell 执行这种副作用 LLM 误调一次就翻车，所以必须让用户在执行前确认。我用 LangGraph 0.3.x 的 `interrupt()` + Checkpointer 实现的，全栈做下来踩了三个有意思的坑。
>
> **第一个坑是序列化**。LangGraph 编译时要传 `checkpointer=PostgresSaver(...)`，每次状态切换都会把 `AgentState` 整个 pickle 进 Postgres。我原本在 state 里塞了一个 `queue.Queue` 当流式 token 通道，结果 checkpoint 直接报序列化失败。解决方案是把 queue 抽出来做成一个**全局注册表**（`stream_queue.py`），key 是 session_id，state 里只存 ID，不存对象——本质上就是把"运行时引用"和"可持久化状态"做隔离。
>
> **第二个坑最有教育意义**——我按文档以为 `graph.invoke()` 遇到 `interrupt()` 会在返回值里塞一个 `__interrupt__` 字段。代码写完跑了一下，前端审批卡片永远不弹。日志看后端，节点的 `interrupt()` 明明触发了 `GraphInterrupt`，但 `final_state.get("__interrupt__")` 永远是 None。后来读 LangGraph 源码才发现：**`invoke()` 的返回值是图的 output state，不带元信息**，中断信息要单独从 `graph.get_state(config).next` 和 `state_snapshot.tasks[*].interrupts[0].value` 取——前者非空说明图没真正结束，后者才是 payload。换成 `get_state()` 检测之后立刻就通了。这个坑让我意识到：**面对新 API 的时候不要被文档示例带偏，要去源码里看返回值的真实结构**。
>
> **第三个坑是危险工具的判定边界**。我一开始把"内部工具白名单"做成精确匹配（`weather`、`calculator`），结果实际工具名是 `get_weather`，没命中白名单就被当成危险工具拦下来了，连查个天气都要审批，体验很糟糕。改成**子串匹配 + 高危关键词反向判定**：白名单关键字（`weather/search/get_/list_`）命中就放行，否则再看是否包含 `write/delete/execute` 这类高危词——这样既能兜住命名变体，又不会漏掉真危险的操作。
>
> 整个功能下来：后端改了 11 个文件（新增 3 个模块）、前端改了 3 个文件、升级了 langgraph 到 0.3.34，端到端打通从 `interrupt → SSE → 审批卡片 → POST /resume → Command(resume=) → 工具执行 → 写文件成功`。最爽的就是第二个坑被定位的那一刻——盯着日志看了半小时，最后是去翻 `langgraph/pregel/__init__.py` 才确认的。"

**这道题为什么必讲**：
- 展示 **LangGraph 高阶特性掌握**（interrupt/Checkpointer/Command resume，比单纯 ReAct 高一个量级）
- 展示 **从抽象问题到工程实现** 的全链路：架构（Queue 分离）→ 调试（源码定位）→ 体验（白名单边界）
- 展示 **全栈交付能力**：SSE 协议、Pinia 状态、Vue 响应式，一个人闭环
- 展示 **安全意识**：工具分级、Human-in-the-Loop，是 Agent 落地企业场景的核心需求
- **故事感强**：三个坑层层递进，比单点炫技更让面试官有记忆点

**追问预案**：
- *Q：为什么不存 `interrupt` 状态在自己的数据库里，要用 Checkpointer？*
  → "Checkpointer 不只是存中断点，它存的是图的**完整执行栈**——节点已经跑到哪一步、消息列表、工具调用记录全在内。`Command(resume=decision)` 之所以能精准回到 `interrupt()` 那一行继续跑，靠的就是 Checkpointer 重放整个图。自己实现就得手动序列化所有节点状态，不划算。"
- *Q：审批通过后，节点是从中断点继续，还是从头重跑？*
  → "**从头重跑**。这是 LangGraph 的设计：节点是幂等单元，恢复时整个节点重新执行，但 `interrupt(payload)` 在重跑过程中遇到时会**直接返回缓存的 decision**，不再抛 GraphInterrupt。所以我在 interrupt 之前的代码（LLM 调用、安全工具执行）会重复跑——这要求节点设计要避免不可重复的副作用。"
- *Q：thread_id 怎么设计的？为什么不用 session_id？*
  → "用的是 `turn-{user_msg_id}`，**每条用户消息一个 thread**。这样一来，多轮对话历史还是由我自己的 DB 管理（`chat_messages` 表），Checkpointer 只负责**单轮内部**的中断恢复。如果用 session_id，会出现跨轮 checkpoint 互相污染、清理时机难定的问题。"
