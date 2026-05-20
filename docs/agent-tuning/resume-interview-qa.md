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

---

## 第四轮：RAG 检索优化 + 工程实战

### Q10：怎么提升 RAG 检索准确率的？⭐ 高频题，必须能完整讲出来

**标准回答**（按问题→排查→解决的故事线）：

> "我把论文上传知识库后，发现用户问'国内外研究现状'这种章节标题类问题时，LLM 回答质量很差。排查发现是**召回阶段就没命中正确的 chunk**。
>
> 第一步我改造了 Word 解析器——识别文档的 Heading 样式（包括自定义样式，用模糊匹配兜底），转成 Markdown 标题标记，再用 MarkdownHeaderSplitter 按标题层级分块，metadata 里自动带上 header_path。
>
> 但效果仍然不好。深入分析发现：一个 500 字的 chunk，标题只占 10 个字，**embedding 向量被正文语义主导**，搜'设计背景'时向量距离反而不是最近的。于是我做了 **Contextual Embedding**——向量化时把 header_path 拼到 chunk 前面（如 `[绪论 > 1.1 设计背景与意义] 正文...`），让标题在 embedding 输入中的占比提升，但存储的原文不变。这是参考 Anthropic 的 Contextual Retrieval 方案。
>
> 后来还加了**双路召回**：向量语义检索 + 自实现 BM25 关键词检索，通过 RRF 算法融合两路排名。BM25 纯 Python 实现，查询时动态构建倒排索引，避免引入 Elasticsearch。这样对精确关键词的匹配能力显著增强。"

**关键术语**（必须自然说出来）：
- Contextual Embedding / 上下文注入
- embedding 向量被正文语义主导
- MarkdownHeaderSplitter + header_path
- 双路召回（Dense + Sparse）
- RRF（Reciprocal Rank Fusion）互惠排名融合

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

### Q14：非结构化文档（Word）怎么保留标题层级？

**答**：

> "Word 文档用 python-docx 解析，遍历每个段落的 `style.name` 属性。用一个映射表把标准样式转为 Markdown 标题：'Heading 1'→'#'、'Heading 2'→'##'、'标题 1'→'#' 等。对于自定义样式（如'章节 二级标题'），用模糊匹配兜底——样式名包含'heading'或'标题'关键词就提取其中的数字作为层级。另外用正则过滤掉目录条目（匹配'标题文字...页码'的 TOC 格式），避免目录内容污染语义 chunk。"

**追问：为什么不直接用 LangChain 的 Document Loader？**
> "LangChain 的 UnstructuredWordDocumentLoader 也是基于 python-docx，但它默认只提取纯文本，不保留标题层级信息。我需要把标题转成 Markdown 格式，后续才能用 MarkdownHeaderSplitter 按结构分块、在 metadata 里保留 header_path。这是定制需求，通用 Loader 做不到。"

### Q15：为什么不加 Reranker（重排模型）？

**答**：

> "目前没有引入 Cross-Encoder 重排。双路召回 + RRF + Contextual Embedding 的效果已经满足需求。如果要加，我会选 bge-reranker-v2 做 Cross-Encoder 精排，放在 RRF 之后取 top-k 之前。但它会增加 100-200ms 延迟，需要权衡实时性。"

**追问：Reranker 和 Embedding 检索有什么区别？**
> "Embedding 检索用的是 Bi-Encoder（双塔模型）——query 和 doc 分别编码成向量再算距离，速度快但精度一般。Reranker 用 Cross-Encoder（交叉编码器）——把 query 和 doc 拼在一起输入 BERT，能捕捉更细粒度的交互特征，精度高但速度慢，不适合全量检索，只适合对候选集精排。所以典型 RAG 管道是：召回（Bi-Encoder）→ 重排（Cross-Encoder）→ 生成（LLM）。"

**注意**：不要假装有重排，但要展示你懂这个环节、知道 trade-off。

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
> 这个案例向面试官有力证明了：**第一，我平台具备严密的安全隔离沙箱；第二，在 49 个工具的超大动作空间和安全边界下，我的 Agent 具备极强的防御性编程意识、环境感知能力和自动容错自愈能力。**"
