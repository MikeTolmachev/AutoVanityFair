import os
import re
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class OpenAIConfig(BaseModel):
    api_key: str = ""
    model: str = "gpt-5.2-pro"
    fast_model: str = "gpt-5-nano"
    max_tokens: int = 1024
    temperature: float = 0.7


class AnthropicConfig(BaseModel):
    api_key: str = ""
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 1024
    temperature: float = 0.7


class AIConfig(BaseModel):
    provider: str = "openai"
    openai: OpenAIConfig = OpenAIConfig()
    anthropic: AnthropicConfig = AnthropicConfig()


class PostScheduleConfig(BaseModel):
    cron_hour: str = "7-9"
    cron_minute: str = "0,30"
    max_per_day: int = 2


class CommentScheduleConfig(BaseModel):
    interval_hours: int = 2
    active_start_hour: int = 9
    active_end_hour: int = 21
    max_per_day: int = 10


class SchedulingConfig(BaseModel):
    timezone: str = "Europe/Berlin"
    posts: PostScheduleConfig = PostScheduleConfig()
    comments: CommentScheduleConfig = CommentScheduleConfig()


class SafetyConfig(BaseModel):
    hourly_action_limit: int = 8
    daily_action_limit: int = 30
    weekly_action_limit: int = 150
    error_rate_threshold: float = 0.3
    error_window_seconds: int = 3600
    cooldown_minutes: int = 30


class LinkedInConfig(BaseModel):
    email: str = ""
    password: str = ""
    browser_profile_dir: str = "data/browser_profile"
    headless: bool = False
    slow_mo: int = 50


class PathsConfig(BaseModel):
    database: str = "data/openlinkedin.db"
    logs: str = "logs"
    chroma_persist: str = "data/chroma"


class RAGConfig(BaseModel):
    collection_name: str = "content_library"
    embedding_model: str = "all-MiniLM-L6-v2"
    similarity_threshold: float = 0.65
    max_context_docs: int = 3


class VertexAIConfig(BaseModel):
    project_id: str = ""
    location: str = "us-central1"
    imagen_model: str = "gemini-3-pro-image-preview"
    veo_model: str = "veo-3.1-generate-001"


class AggregationConfig(BaseModel):
    enabled: bool = True
    fetch_timeout: int = 15
    max_items_per_feed: int = 20
    cache_ttl_minutes: int = 30
    min_relevance_score: float = 10.0
    default_priorities: list[int] = [1, 2]
    schedule_interval_hours: int = 6
    auto_save_threshold: float = 35.0
    max_age_months: int = 3


class AppConfig(BaseModel):
    ai: AIConfig = AIConfig()
    scheduling: SchedulingConfig = SchedulingConfig()
    safety: SafetyConfig = SafetyConfig()
    linkedin: LinkedInConfig = LinkedInConfig()
    paths: PathsConfig = PathsConfig()
    rag: RAGConfig = RAGConfig()
    aggregation: AggregationConfig = AggregationConfig()
    vertex_ai: VertexAIConfig = VertexAIConfig()


_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


def _resolve_env_vars(value: str) -> str:
    """Replace ${ENV_VAR} placeholders with environment variable values."""

    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, "")

    return _ENV_VAR_PATTERN.sub(_replace, value)


def _resolve_dict(d: dict) -> dict:
    """Recursively resolve env vars in a dict."""
    resolved = {}
    for k, v in d.items():
        if isinstance(v, str):
            resolved[k] = _resolve_env_vars(v)
        elif isinstance(v, dict):
            resolved[k] = _resolve_dict(v)
        elif isinstance(v, list):
            resolved[k] = [
                _resolve_env_vars(i) if isinstance(i, str) else i for i in v
            ]
        else:
            resolved[k] = v
    return resolved


class ConfigManager:
    """Loads YAML config, resolves env vars, validates with Pydantic."""

    def __init__(
        self,
        config_path: str = "config/config.yaml",
        env_file: Optional[str] = ".env",
    ):
        if env_file and Path(env_file).exists():
            load_dotenv(env_file)

        self._raw = self._load_yaml(config_path)
        self._resolved = _resolve_dict(self._raw)
        self.config = AppConfig(**self._resolved)

    @staticmethod
    def _load_yaml(path: str) -> dict:
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}

    @property
    def ai(self) -> AIConfig:
        return self.config.ai

    @property
    def scheduling(self) -> SchedulingConfig:
        return self.config.scheduling

    @property
    def safety(self) -> SafetyConfig:
        return self.config.safety

    @property
    def linkedin(self) -> LinkedInConfig:
        return self.config.linkedin

    @property
    def paths(self) -> PathsConfig:
        return self.config.paths

    @property
    def rag(self) -> RAGConfig:
        return self.config.rag

    @property
    def aggregation(self) -> AggregationConfig:
        return self.config.aggregation

    @property
    def vertex_ai(self) -> VertexAIConfig:
        return self.config.vertex_ai
