import re
from typing import Any, Dict, List, Optional
from github_client import GitHubClient, GitHubAPIError
from loguru import logger

# 正则表达式安全防线：GitHub 用户名和仓库名只允许英文字母、数字、短横线(-)、下划线(_)以及英文点号(.)
# 彻底杜绝注入攻击和非法字符探测，保证线上安全
GITHUB_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9-_\.]+$")

# 实例化全局单例 GitHub API 客户端
client = GitHubClient()


def validate_repo_path(owner: str, repo: str) -> None:
    """
    对输入的 GitHub Owner 和 Repo 名称进行严格的安全合规审查
    """
    if not owner or not GITHUB_NAME_PATTERN.match(owner):
        raise ValueError(f"非法的 owner 名称: '{owner}'。只允许字母、数字、-、_ 或 .")
    if not repo or not GITHUB_NAME_PATTERN.match(repo):
        raise ValueError(f"非法的 repo 名称: '{repo}'。只允许字母、数字、-、_ 或 .")


async def search_repositories_tool(query: str, sort: str = "stars", limit: int = 5) -> Dict[str, Any]:
    """
    工具接口：搜索公开仓库。处理所有捕获的异常，返回结构化的 JSON 数据。
    """
    try:
        # 输入安全校验，限制最大搜索 query 长度防止滥用
        clean_query = query.strip()[:200]
        if not clean_query:
            return {"error": {"code": "invalid_argument", "message": "搜索关键词不能为空", "status": 400}}
            
        data = await client.search_repositories(clean_query, sort=sort, limit=limit)
        return {"query": clean_query, "items": data}
    except GitHubAPIError as e:
        return {"error": {"code": e.code, "message": e.message, "status": e.status_code}}
    except Exception as e:
        logger.exception("[MCP Tools] 搜索仓库发生未处理异常")
        return {"error": {"code": "internal_error", "message": f"系统内部异常: {str(e)}", "status": 500}}


async def get_repository_info_tool(owner: str, repo: str) -> Dict[str, Any]:
    """
    工具接口：获取仓库核心只读元信息。
    """
    try:
        # 物理防线：执行安全校验
        validate_repo_path(owner, repo)
        
        data = await client.get_repository_info(owner, repo)
        return data
    except ValueError as e:
        return {"error": {"code": "invalid_argument", "message": str(e), "status": 400}}
    except GitHubAPIError as e:
        return {"error": {"code": e.code, "message": e.message, "status": e.status_code}}
    except Exception as e:
        logger.exception("[MCP Tools] 获取仓库详情发生未处理异常")
        return {"error": {"code": "internal_error", "message": f"系统内部异常: {str(e)}", "status": 500}}


async def get_repository_readme_tool(owner: str, repo: str) -> Dict[str, Any]:
    """
    工具接口：获取并截断 README 内容。
    """
    try:
        validate_repo_path(owner, repo)
        
        data = await client.get_repository_readme(owner, repo)
        return data
    except ValueError as e:
        return {"error": {"code": "invalid_argument", "message": str(e), "status": 400}}
    except GitHubAPIError as e:
        return {"error": {"code": e.code, "message": e.message, "status": e.status_code}}
    except Exception as e:
        logger.exception("[MCP Tools] 获取仓库 README 发生未处理异常")
        return {"error": {"code": "internal_error", "message": f"系统内部异常: {str(e)}", "status": 500}}


async def list_repository_issues_tool(owner: str, repo: str, state: str = "open", limit: int = 5) -> Dict[str, Any]:
    """
    工具接口：列出 Issue，自动过滤 PR 混淆数据。
    """
    try:
        validate_repo_path(owner, repo)
        
        # 验证 state 合规性
        if state not in ("open", "closed", "all"):
            state = "open"
            
        data = await client.list_repository_issues(owner, repo, state=state, limit=limit)
        return {"full_name": f"{owner}/{repo}", "state": state, "items": data}
    except ValueError as e:
        return {"error": {"code": "invalid_argument", "message": str(e), "status": 400}}
    except GitHubAPIError as e:
        return {"error": {"code": e.code, "message": e.message, "status": e.status_code}}
    except Exception as e:
        logger.exception("[MCP Tools] 获取 Issue 列表发生未处理异常")
        return {"error": {"code": "internal_error", "message": f"系统内部异常: {str(e)}", "status": 500}}
