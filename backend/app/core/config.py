"""
应用配置管理模块

基于 pydantic-settings 从环境变量 / .env 文件加载配置。
所有配置项集中在 Settings 类中，全局通过 settings 实例访问。
"""
from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局应用配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # 忽略未定义的环境变量
    )

    # ---------- 应用基础配置 ----------
    APP_NAME: str = "NexusAI"
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_DEBUG: bool = True

    # ---------- JWT 认证配置 ----------
    JWT_SECRET_KEY: str = Field(..., description="JWT 签名密钥，生产环境必填")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 默认 24 小时

    # ---------- PostgreSQL 数据库 ----------
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "nexus_ai"

    # ---------- Redis 配置 ----------
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0

    # ---------- Celery 配置 ----------
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ---------- CORS 跨域 ----------
    # 用 str 而非 List[str]，避免 pydantic-settings 强制 JSON 解码
    # 多个域名在 .env 中使用逗号分隔，例如：http://a.com,http://b.com
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---------- DeepSeek API（后续阶段使用） ----------
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_API_BASE: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # ---------- 阿里通义 Embedding API（后续阶段使用） ----------
    DASHSCOPE_API_KEY: str = ""
    EMBEDDING_MODEL: str = "text-embedding-v3"

    # ---------- ChromaDB（通过 HTTP 客户端连接 Docker 中的 Chroma Server） ----------
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001

    # ---------- Embedding 配置 ----------
    # 通义 text-embedding-v3 的向量维度为 1024（默认）
    EMBEDDING_DIM: int = 1024
    # 当 DASHSCOPE_API_KEY 为空时自动回退到 Mock Embedder（开发友好）
    EMBEDDING_PROVIDER: str = "auto"  # auto / tongyi / mock

    # ---------- 文件上传 ----------
    UPLOAD_DIR: str = "./data/uploads"
    MAX_UPLOAD_SIZE_MB: int = 50

    # ---------- 派生属性 ----------
    @property
    def database_url(self) -> str:
        """构造 PostgreSQL 同步连接字符串"""
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def is_production(self) -> bool:
        """是否为生产环境"""
        return self.APP_ENV.lower() == "production"

    @property
    def cors_origins_list(self) -> List[str]:
        """将逗号分隔的 CORS_ORIGINS 字符串切分为列表"""
        return [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(",")
            if origin.strip()
        ]


@lru_cache()
def get_settings() -> Settings:
    """
    获取全局配置单例。
    使用 lru_cache 确保只实例化一次，避免重复读取 .env 文件。
    """
    return Settings()


# 全局配置实例，业务代码统一通过此实例访问配置
settings = get_settings()
