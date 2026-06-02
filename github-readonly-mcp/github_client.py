import base64
from typing import Any, Dict, List, Optional
import httpx
from loguru import logger
from config import settings


class GitHubAPIError(Exception):
    """自定义 GitHub API 异常"""
    def __init__(self, code: str, message: str, status_code: int = 500):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class GitHubClient:
    """
    封装与 GitHub REST API 进行交互的只读客户端
    """
    def __init__(self):
        # 组装默认请求头，设置标准的 API 版本和 User-Agent 防止被拒绝
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "NexusAI-GitHub-Readonly-MCP"
        }
        # 如果配置了 token，则注入只读认证
        if settings.github_token:
            self.headers["Authorization"] = f"Bearer {settings.github_token}"

    async def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """底层 HTTP 通用请求封装"""
        url = f"{settings.github_api_base.rstrip('/')}/{path.lstrip('/')}"
        
        async with httpx.AsyncClient(timeout=settings.github_mcp_timeout_seconds) as client:
            try:
                response = await client.request(method, url, headers=self.headers, params=params)
                
                # 状态码拦截与统一结构化错误输出
                if response.status_code == 404:
                    raise GitHubAPIError("github_not_found", "资源未找到，请确认仓库路径或权限是否正确", 404)
                elif response.status_code == 403:
                    # 判断是否触发了限流
                    if "rate limit" in response.text.lower():
                        raise GitHubAPIError("github_rate_limited", "触发了 GitHub API 速率限制，请稍后再试或配置 Token", 403)
                    raise GitHubAPIError("github_forbidden", "拒绝访问，无权读取此仓库", 403)
                elif response.status_code == 429:
                    raise GitHubAPIError("github_rate_limited", "触发了 GitHub API 速率限制，请稍后再试", 429)
                elif response.status_code >= 400:
                    raise GitHubAPIError("github_api_error", f"GitHub 接口请求失败: {response.text}", response.status_code)
                
                return response.json()
            except httpx.RequestError as e:
                logger.error("[GitHub Client] 网络请求发生异常: {}", e)
                raise GitHubAPIError("github_network_error", f"连接 GitHub 接口失败: {str(e)}", 503)

    async def search_repositories(self, query: str, sort: str = "stars", limit: int = 5) -> List[Dict[str, Any]]:
        """按关键词检索公开的 GitHub 仓库"""
        # 强制限制最大单页条数，防止上下文暴涨
        safe_limit = min(limit, settings.github_mcp_max_limit)
        
        path = "search/repositories"
        params = {
            "q": query,
            "sort": sort,
            "order": "desc",
            "per_page": safe_limit
        }
        
        data = await self._request("GET", path, params=params)
        items = data.get("items", [])
        
        # 精简化返回数据，只保留高价值元数据，屏蔽无关的大对象以省 token
        result = []
        for item in items:
            result.append({
                "full_name": item.get("full_name"),
                "description": item.get("description") or "无描述",
                "stars": item.get("stargazers_count", 0),
                "forks": item.get("forks_count", 0),
                "language": item.get("language") or "未知",
                "updated_at": item.get("updated_at"),
                "html_url": item.get("html_url")
            })
        return result

    async def get_repository_info(self, owner: str, repo: str) -> Dict[str, Any]:
        """获取指定仓库的只读核心详情"""
        path = f"repos/{owner}/{repo}"
        data = await self._request("GET", path)
        
        return {
            "full_name": data.get("full_name"),
            "description": data.get("description") or "无描述",
            "stars": data.get("stargazers_count", 0),
            "forks": data.get("forks_count", 0),
            "watchers": data.get("subscribers_count", 0),
            "language": data.get("language") or "未知",
            "license": (data.get("license") or {}).get("name") or "未声明",
            "default_branch": data.get("default_branch", "main"),
            "open_issues": data.get("open_issues_count", 0),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
            "pushed_at": data.get("pushed_at"),
            "topics": data.get("topics", []),
            "html_url": data.get("html_url")
        }

    async def get_repository_readme(self, owner: str, repo: str) -> Dict[str, Any]:
        """获取仓库的 README 内容，自动进行 Base64 解码和安全字符数截断"""
        path = f"repos/{owner}/{repo}/readme"
        data = await self._request("GET", path)
        
        # 读取并解码 Base64 编码的 README 原始内容
        content_b64 = data.get("content", "")
        try:
            content_bytes = base64.b64decode(content_b64.replace("\n", ""))
            content_str = content_bytes.decode("utf-8", errors="replace")
        except Exception as e:
            logger.error("[GitHub Client] README 内容 Base64 解码失败: {}", e)
            raise GitHubAPIError("github_decode_failed", "README 内容解码失败，可能不是标准的 utf-8 文本", 500)

        # 强制按设置进行强截断防护，防止模型上下文爆掉
        max_chars = settings.github_mcp_readme_max_chars
        truncated = len(content_str) > max_chars
        if truncated:
            content_str = content_str[:max_chars]

        return {
            "full_name": f"{owner}/{repo}",
            "path": data.get("path", "README.md"),
            "html_url": data.get("html_url"),
            "content": content_str,
            "truncated": truncated
        }

    async def list_repository_issues(self, owner: str, repo: str, state: str = "open", limit: int = 5) -> List[Dict[str, Any]]:
        """获取指定仓库的 Issue 列表，强制过滤掉 Pull Request 混淆项"""
        safe_limit = min(limit, settings.github_mcp_max_limit)
        
        path = f"repos/{owner}/{repo}/issues"
        params = {
            "state": state,
            "per_page": safe_limit * 2  # 稍微多取一点，因为需要手动过滤掉 PR
        }
        
        items = await self._request("GET", path, params=params)
        
        result = []
        for item in items:
            # 关键过滤：GitHub 的 Issues API 会同时混入 Pull Request。如果带有 pull_request 字段，说明是 PR，过滤掉
            if "pull_request" in item:
                continue
            
            result.append({
                "number": item.get("number"),
                "title": item.get("title"),
                "state": item.get("state"),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
                "comments": item.get("comments", 0),
                "html_url": item.get("html_url")
            })
            
            # 达到安全数量限制则终止
            if len(result) >= safe_limit:
                break
                
        return result
