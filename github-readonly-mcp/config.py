from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    GitHub 只读 MCP 服务的全局配置项管理（基于 Pydantic-Settings）
    """
    # Pydantic 2.x 设置配置
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), 
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # ---------- GitHub API 配置 ----------
    # 您的 GitHub 个人只读访问令牌，推荐在线上 Railway 环境变量中配置以避免限流
    github_token: Optional[str] = None
    
    # GitHub REST API 基础基址
    github_api_base: str = "https://api.github.com"
    
    # 请求外部 GitHub API 的超时时间（秒）
    github_mcp_timeout_seconds: int = 10

    # ---------- 系统防御与安全裁剪限制 ----------
    # 单次列表查询允许的最大条数限制，强制防止上下文爆掉
    github_mcp_max_limit: int = 10
    
    # README 内容最大截断字符数（默认 12000 字符，防 token 膨胀）
    github_mcp_readme_max_chars: int = 12000


# 全局配置实例
settings = Settings()
