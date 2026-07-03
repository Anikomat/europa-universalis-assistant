"""
应用配置 — pydantic 模型
支持多模型分级配置和 YAML 加载
"""
import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
import yaml


class ModelConfig(BaseModel):
    """单个模型配置"""
    provider: str = "deepseek"
    api_base: str = "https://api.deepseek.com/v1"
    api_key: str = ""
    model: str = "deepseek-chat"
    temperature: float = 0.7
    max_tokens: int = 800
    max_retries: int = 3
    timeout: int = 60

    def resolve_api_key(self) -> str:
        """解析 API Key：直接值或 ${ENV_VAR} 格式"""
        if self.api_key.startswith("${") and self.api_key.endswith("}"):
            env_var = self.api_key[2:-1]
            return os.environ.get(env_var, "")
        return self.api_key or os.environ.get("LLM_API_KEY", "")


class ModelsConfig(BaseModel):
    """多模型分级配置"""
    default: ModelConfig = Field(default_factory=ModelConfig)
    router: Optional[ModelConfig] = None   # 工具调用 / 决策
    reply: Optional[ModelConfig] = None    # 最终回复生成
    vision: Optional[ModelConfig] = None   # VLM 截图分析

    @staticmethod
    def _inherit_default(model: ModelConfig, default: ModelConfig) -> ModelConfig:
        """用 default 的值填充 target 未显式设置的字段，返回新对象不修改原值"""
        return ModelConfig(
            provider=model.provider if model.provider != ModelConfig.model_fields["provider"].default else default.provider,
            api_base=model.api_base if model.api_base != ModelConfig.model_fields["api_base"].default else default.api_base,
            api_key=model.api_key if model.api_key != ModelConfig.model_fields["api_key"].default else default.api_key,
            model=model.model if model.model != ModelConfig.model_fields["model"].default else default.model,
            temperature=model.temperature if model.temperature != ModelConfig.model_fields["temperature"].default else default.temperature,
            max_tokens=model.max_tokens if model.max_tokens != ModelConfig.model_fields["max_tokens"].default else default.max_tokens,
            max_retries=model.max_retries if model.max_retries != ModelConfig.model_fields["max_retries"].default else default.max_retries,
            timeout=model.timeout if model.timeout != ModelConfig.model_fields["timeout"].default else default.timeout,
        )

    def get_router(self) -> ModelConfig:
        cfg = self.router or self.default
        return self._inherit_default(cfg, self.default)

    def get_reply(self) -> ModelConfig:
        cfg = self.reply or self.default
        return self._inherit_default(cfg, self.default)

    def get_vision(self) -> Optional[ModelConfig]:
        if self.vision is not None:
            return self._inherit_default(self.vision, self.default)
        return None

    @property
    def has_vision(self) -> bool:
        return self.vision is not None


class RAGConfig(BaseModel):
    index_dir: Path = Path("rag_index")
    top_k: int = 3
    embedding_model: str = "shibing624/text2vec-base-chinese"


class ScreenshotConfig(BaseModel):
    monitor: int = 1


class PulseConfig(BaseModel):
    interval_min: int = 30   # 脉冲最小间隔（秒）
    interval_max: int = 90   # 脉冲最大间隔（秒）


class ContextConfig(BaseModel):
    retention_hours: int = 24   # 对话记录保留小时数
    max_messages: int = 30      # 注入 prompt 的最近消息条数上限
    max_chars: int = 5000       # 注入 prompt 的总字符数上限


class L2DConfig(BaseModel):
    model_path: str = "/models/huifeng/model0.json"
    # 启用后，AI 可根据对话内容自主选择角色表情。
    # 要求模型 JSON 中 Expressions 的 Name 字段语义明确（如 uemodel 的 "生气""机智" 等）。
    # huifeng 的表情名是文件名（如 jz.exp3），语义化程度低，不建议启用。
    expression_control: bool = False


class AppConfig(BaseModel):
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    screenshot: ScreenshotConfig = Field(default_factory=ScreenshotConfig)
    pulse: PulseConfig = Field(default_factory=PulseConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
    l2d: L2DConfig = Field(default_factory=L2DConfig)

    @classmethod
    def from_yaml(cls, path: Path) -> "AppConfig":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(**data)
