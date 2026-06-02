# GitHub Readonly MCP SSE Server 执行计划

## 1. 目标

为 NexusAI 增加一个独立部署的 GitHub 只读 MCP Server，通过 SSE 传输接入主站现有 MCP Client。该服务只封装公开仓库/指定 token 可访问仓库的只读查询能力，用于线上演示“外部 MCP 工具动态接入”，避免直接接官方 GitHub MCP 带来的工具过多、权限过大、路由不稳定等问题。

目标链路：

```text
NexusAI 主站 Tool Agent
  -> MCP Client(sse_client)
  -> GitHub Readonly MCP Server(/sse)
  -> GitHub REST API
```

主站最终配置：

```text
名称：GitHub Readonly MCP
传输方式：sse
连接 URI：https://<github-mcp-service>.up.railway.app/sse
环境变量：{}
整体描述：只读查询 GitHub 仓库信息、README、Issue 和仓库搜索结果，适合分析开源项目与代码仓库概况。
```

## 2. 为什么采用方案 B：独立 SSE 服务

当前 NexusAI 项目已经具备：

- `backend/app/mcp/client.py` 支持 `stdio` 和 `sse_client(config.connection_uri)`。
- 前端 MCP 配置页支持选择 `stdio` / `sse`。
- `MCPServerConfig.cached_tools` 会缓存工具清单，Tool Agent 会把外部 MCP 工具挂入统一 Function Calling 工具池。
- `tool_agent.py` 已经支持 MCP 工具调用、超时、execution_trace 和连续失败兜底。

不建议直接使用官方 GitHub MCP：

- 官方/社区 GitHub MCP 往往工具很多，包含写操作，公开演示权限边界差。
- 你的项目目前不支持 Streamable HTTP，也不支持 SSE 自定义 headers/OAuth。
- stdio 方式线上每次 `npx` 拉起子进程，冷启动慢，不适合稳定演示。

独立 SSE 服务的优势：

- 主站不需要改 MCP Client 协议层。
- GitHub Token 放在 GitHub MCP 服务自己的 Railway 环境变量里，不放主站数据库。
- 只暴露你定义的 4-5 个只读工具，路由更稳定。
- 可以单独部署、单独调试、单独扩展。

## 3. 第一阶段范围

第一版只做只读能力，不做写操作，不做代码全文搜索，不做 PR 创建/评论/合并。

建议工具：

1. `search_github_repositories`
   - 按关键词搜索仓库。
   - 适合问题：“帮我找几个 FastAPI RAG 项目参考。”

2. `get_repository_info`
   - 获取仓库基础信息。
   - 适合问题：“分析 limengyuna/nexus-ai 这个仓库的基本情况。”

3. `get_repository_readme`
   - 获取仓库 README，返回裁剪后的 Markdown 文本。
   - 适合问题：“读取这个仓库 README，总结项目定位和技术栈。”

4. `list_repository_issues`
   - 列出 Issue，默认只取 open，限制数量。
   - 适合问题：“看一下这个项目最近有哪些 open issue。”

5. 可选：`get_repository_file`
   - 读取指定路径的小文件，例如 `package.json`、`pyproject.toml`、`README.md`。
   - 第一版可以先不做，避免被用于拉大文件。

## 4. 建议目录结构

建议在仓库根目录新增一个独立服务目录，避免污染主站后端：

```text
github-readonly-mcp/
  README.md
  requirements.txt
  Dockerfile
  main.py
  github_client.py
  tools.py
  config.py
  tests/
    test_tools.py
```

如果另一个 AI 更擅长 Node，也可以用 TypeScript 写。但从你项目主技术栈和简历表达看，建议用 Python/FastAPI/官方 MCP SDK，和主站后端技术统一。

## 5. 依赖建议

`github-readonly-mcp/requirements.txt`：

```text
fastapi==0.115.12
uvicorn[standard]==0.30.6
httpx==0.27.2
pydantic==2.9.2
pydantic-settings==2.5.2
mcp>=1.2.0
```

如果当前 MCP SDK 版本提供 SSE Server 辅助模块，优先使用 SDK 官方 SSE server transport；如果版本不兼容，再升级该独立服务的 MCP SDK，不要影响主站后端。

## 6. 环境变量

GitHub MCP 服务自己的 Railway 环境变量：

```text
GITHUB_TOKEN=ghp_xxx
GITHUB_API_BASE=https://api.github.com
GITHUB_MCP_MAX_LIMIT=10
GITHUB_MCP_TIMEOUT_SECONDS=10
GITHUB_MCP_README_MAX_CHARS=12000
GITHUB_MCP_FILE_MAX_CHARS=8000
```

说明：

- `GITHUB_TOKEN` 可选，但线上建议配置，避免 GitHub 未认证 API 限流过低。
- token 只需要最小只读权限。公开仓库查询可以使用 fine-grained token，尽量不要给写权限。
- 所有限制项必须在服务端强制执行，不能只依赖模型传参。

## 7. 工具设计细节

### 7.1 search_github_repositories

输入 Schema：

```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "搜索关键词，例如 fastapi rag langgraph"
    },
    "limit": {
      "type": "integer",
      "description": "返回数量，默认 5，最大 10",
      "default": 5
    },
    "sort": {
      "type": "string",
      "description": "排序方式：stars、updated、forks，默认 stars",
      "default": "stars"
    }
  },
  "required": ["query"]
}
```

返回字段建议：

```json
{
  "query": "fastapi rag langgraph",
  "items": [
    {
      "full_name": "owner/repo",
      "description": "...",
      "stars": 1234,
      "forks": 100,
      "language": "Python",
      "updated_at": "2026-01-01T00:00:00Z",
      "html_url": "https://github.com/owner/repo"
    }
  ]
}
```

防御规则：

- `limit` 最大 10。
- `query` 最大 200 字符。
- 不返回完整 owner 对象，避免 token 浪费。

### 7.2 get_repository_info

输入 Schema：

```json
{
  "type": "object",
  "properties": {
    "owner": {"type": "string", "description": "仓库 owner"},
    "repo": {"type": "string", "description": "仓库名"}
  },
  "required": ["owner", "repo"]
}
```

返回字段建议：

```json
{
  "full_name": "owner/repo",
  "description": "...",
  "stars": 1234,
  "forks": 100,
  "watchers": 50,
  "language": "Python",
  "license": "MIT",
  "default_branch": "main",
  "open_issues": 12,
  "created_at": "...",
  "updated_at": "...",
  "pushed_at": "...",
  "topics": ["rag", "fastapi"],
  "html_url": "https://github.com/owner/repo"
}
```

防御规则：

- owner/repo 只允许 GitHub 合法字符：字母、数字、`-`、`_`、`.`。
- 返回字段裁剪，不返回 GitHub API 原始大对象。

### 7.3 get_repository_readme

输入 Schema：

```json
{
  "type": "object",
  "properties": {
    "owner": {"type": "string"},
    "repo": {"type": "string"}
  },
  "required": ["owner", "repo"]
}
```

实现方式：

- 调 GitHub API：`GET /repos/{owner}/{repo}/readme`
- 读取 `content`，base64 decode。
- 按 `GITHUB_MCP_README_MAX_CHARS` 截断。
- 返回 `truncated: true/false`。

返回字段建议：

```json
{
  "full_name": "owner/repo",
  "path": "README.md",
  "html_url": "...",
  "content": "...",
  "truncated": false
}
```

防御规则：

- 不返回超过限制的全文。
- 如果 README 不存在，返回结构化错误，不抛出未处理异常。

### 7.4 list_repository_issues

输入 Schema：

```json
{
  "type": "object",
  "properties": {
    "owner": {"type": "string"},
    "repo": {"type": "string"},
    "state": {
      "type": "string",
      "description": "open、closed、all，默认 open",
      "default": "open"
    },
    "limit": {
      "type": "integer",
      "description": "返回数量，默认 5，最大 10",
      "default": 5
    }
  },
  "required": ["owner", "repo"]
}
```

返回字段建议：

```json
{
  "full_name": "owner/repo",
  "state": "open",
  "items": [
    {
      "number": 1,
      "title": "...",
      "state": "open",
      "created_at": "...",
      "updated_at": "...",
      "comments": 3,
      "html_url": "..."
    }
  ]
}
```

防御规则：

- 过滤掉 pull request：GitHub issues API 会混入 PR，需要忽略包含 `pull_request` 字段的项，或者明确标记。
- 不返回 issue body，避免 token 过大。需要 body 时后续单独做 `get_issue_detail`。

## 8. MCP Server 实现要求

### 8.1 Server 名称

```text
github-readonly-mcp
```

### 8.2 list_tools

必须只返回只读工具。

工具描述要写清楚边界，例如：

```text
Search public GitHub repositories by keyword. Read-only. Returns compact repository metadata.
```

不要出现“create/update/delete/comment/merge”等动词，避免 Supervisor 误判为可执行写操作。

### 8.3 call_tool

统一调用 `tools.py` 中的函数：

```text
call_tool(name, arguments)
  -> validate arguments
  -> call GitHubClient
  -> compact result
  -> return TextContent(json.dumps(result, ensure_ascii=False))
```

错误返回统一结构：

```json
{
  "error": {
    "code": "github_not_found",
    "message": "Repository not found or no permission",
    "status": 404
  }
}
```

不要直接把异常堆栈返回给模型。

## 9. SSE 传输实现要求

主站当前使用：

```python
from mcp.client.sse import sse_client
async with sse_client(config.connection_uri) as (read, write):
    ...
```

因此独立服务必须提供兼容旧版 MCP SSE Client 的 `/sse` endpoint。

执行时需要重点验证：

```text
NexusAI MCP 配置页
  -> 传输方式 sse
  -> 连接 URI https://<service>.up.railway.app/sse
  -> 测试连接并发现工具
```

如果实现时发现当前 `mcp` SDK 的 SSE server API 与主站 `sse_client` 不兼容，优先处理独立服务，不改主站：

- 方案 1：独立服务固定使用与主站兼容的 `mcp` SDK 版本。
- 方案 2：独立服务实现旧版 SSE transport。
- 方案 3：最后才考虑给主站补 Streamable HTTP Client 支持。

第一阶段不要同时改主站 MCP Client，否则风险变大。

## 10. Dockerfile

`github-readonly-mcp/Dockerfile`：

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --index-url https://pypi.org/simple -r requirements.txt

COPY . .

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

Railway 部署时：

- Root Directory 设为 `github-readonly-mcp`
- Start Command 可不填，使用 Dockerfile CMD
- 环境变量配置 `GITHUB_TOKEN`

## 11. 与 NexusAI 主站的配置方式

部署 GitHub MCP 服务后，在主站 MCP 配置页填写：

```text
名称：
GitHub Readonly MCP

传输方式：
sse（远程 HTTP）

连接 URI：
https://<github-mcp-service>.up.railway.app/sse

环境变量：
{}

整体描述：
只读查询 GitHub 仓库、README、Issue 和仓库搜索结果，用于分析开源项目与代码仓库概况。
```

点击：

```text
测试连接并发现子工具 -> 创建并预缓存
```

预期缓存工具：

```text
search_github_repositories
get_repository_info
get_repository_readme
list_repository_issues
```

主站 Tool Agent 中实际挂载名称会带前缀：

```text
mcp_<config_id>_search_github_repositories
mcp_<config_id>_get_repository_info
...
```

这是当前项目已有设计，不需要改。

## 12. Supervisor / Tool Agent 是否需要改

第一阶段尽量不改。

原因：

- `supervisor.py` 已经会读取用户 MCP 配置名称和描述，并在 prompt 中动态注入。
- `tool_agent.py` 已经把 `cached_tools` 转成 Function Calling schema。
- 只要 MCP 描述写清楚，Supervisor 应该能路由到 `tool_agent`。

如果测试发现路由不稳定，再做很小的 prompt 增强：

```text
当用户要求查询、分析 GitHub 仓库、README、Issue、开源项目资料时，优先交给 tool_agent 使用 GitHub Readonly MCP。
```

注意：不要写死具体仓库名，也不要把这个规则放到最高优先级。最高优先级仍然应该是 Business Context Agent 查询 NexusAI 系统内用户数据。

## 13. 安全与边界

必须保证：

- 不暴露任何写操作。
- 不暴露 token。
- 不返回 GitHub API 原始响应。
- 所有列表都有最大 limit。
- README / 文件内容必须截断。
- HTTP 请求必须有 timeout。
- GitHub 404/403/429 要返回结构化错误。
- User-Agent 必须设置，避免 GitHub API 拒绝请求。

建议请求头：

```text
Accept: application/vnd.github+json
Authorization: Bearer <GITHUB_TOKEN>
X-GitHub-Api-Version: 2022-11-28
User-Agent: NexusAI-GitHub-Readonly-MCP
```

## 14. 测试计划

### 14.1 单元测试

测试目标：

- 参数校验：非法 owner/repo 被拒绝。
- `limit` 超过最大值会被裁剪。
- README 超长会被截断并返回 `truncated=true`。
- GitHub 404 返回结构化错误。
- Issue 列表不返回 body，避免 token 膨胀。

建议 mock GitHub API，不依赖真实网络。

### 14.2 本地 MCP 测试

启动独立服务：

```bash
cd github-readonly-mcp
uvicorn main:app --host 0.0.0.0 --port 8005
```

主站配置：

```text
传输方式：sse
连接 URI：http://localhost:8005/sse
```

在 MCP 配置页点击测试连接，确认能发现工具。

### 14.3 主站对话测试

测试问题：

```text
用 GitHub MCP 搜索 5 个 FastAPI RAG 相关的开源项目，并按 stars 排序总结。
```

```text
读取 limengyuna/nexus-ai 的 README，总结这个项目解决了什么问题。
```

```text
查看 langchain-ai/langgraph 最近的 open issue，归纳常见问题类型。
```

预期：

- 思考过程/执行轨迹里出现 `tool_agent`。
- execution_trace 中出现 MCP 工具调用。
- 回答包含 GitHub MCP 返回的仓库/README/Issue 信息。
- 不应该走 Business Context Agent。

### 14.4 Railway 测试

部署后在主站配置：

```text
https://<github-mcp-service>.up.railway.app/sse
```

测试连接成功后，再创建并预缓存。

如果失败，按顺序排查：

1. `/sse` endpoint 是否可访问。
2. 独立服务日志是否收到 SSE 连接。
3. MCP SDK SSE server 是否与主站 `sse_client` 协议兼容。
4. Railway 是否设置了正确 PORT。
5. GitHub token 是否配置。
6. GitHub API 是否触发 403/429。

## 15. 面试表达方式

可以这样讲：

> 项目没有直接把 GitHub 官方 MCP 全量接入，因为它工具多且权限边界不清晰。我的做法是单独实现一个只读 GitHub MCP Server，通过 SSE 暴露给 NexusAI 主站。主站只负责动态发现和调用 MCP 工具，GitHub Token 和只读权限边界都封装在独立服务里。这样既能体现 MCP 的外部工具扩展能力，也能控制 Agent 的工具列表、权限范围和返回 token 体积。

突出点：

- MCP Client/Server 双向理解。
- Agent Harness：工具边界、只读封装、limit、超时、错误结构化。
- 工程化部署：独立 Railway service，主站通过 SSE 配置接入。
- 可观测：主站已有 execution_trace 可以展示 MCP 调用链路。

## 16. 不做事项

第一阶段明确不做：

- 不接官方 GitHub Remote MCP。
- 不支持写操作。
- 不做 OAuth 登录。
- 不读取私有仓库，除非 token 明确授权。
- 不做仓库代码全文扫描。
- 不改主站 MCP Client 为 Streamable HTTP。
- 不把 GitHub MCP 代码混进主站后端服务。

## 17. 验收标准

完成后必须满足：

- 独立 GitHub MCP 服务可本地启动。
- `/sse` 可被 NexusAI 主站 MCP 配置页连接。
- 能发现 4 个只读工具。
- 能在主站创建 MCP 配置并缓存工具列表。
- 聊天中能通过 Tool Agent 调用 GitHub MCP。
- execution_trace 能看到 MCP 工具调用。
- 公开演示时不会暴露写操作。
- README/Issue/Search 返回内容有长度控制，不会拖垮上下文。

