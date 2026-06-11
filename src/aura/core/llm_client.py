"""DeepSeek client construction."""

from __future__ import annotations

from openai import OpenAI

from aura.config import AuraSettings


class DeepSeekClientFactory:
    """Create official OpenAI SDK clients configured for DeepSeek."""

    def __init__(self, settings: AuraSettings) -> None:
        self.settings = settings

    def create(self) -> OpenAI:
        if not self.settings.has_api_key:
            raise ValueError("DeepSeek API Key 尚未配置，请先运行 `aura config`。")

        return OpenAI(
            api_key=self.settings.api_key,
            base_url=self.settings.base_url,
        )
