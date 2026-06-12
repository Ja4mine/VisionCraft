"""Configuration management for Aura."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class AuraSettings:
    """User-facing settings persisted on the local machine."""

    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    obsidian_vault_path: str = ""
    obsidian_folder: str = "VisionCraft"

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key.strip())

    @property
    def masked_api_key(self) -> str:
        if not self.api_key:
            return "未配置"
        if len(self.api_key) <= 8:
            return "*" * len(self.api_key)
        return f"{self.api_key[:4]}...{self.api_key[-4:]}"


class ConfigManager:
    """Load and save Aura settings as a small JSON config file."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or self.default_config_path()

    @staticmethod
    def default_config_path() -> Path:
        config_home = os.environ.get("XDG_CONFIG_HOME")
        if config_home:
            return Path(config_home) / "visioncraft" / "config.json"
        return Path.home() / ".config" / "visioncraft" / "config.json"

    def load(self) -> AuraSettings:
        if not self.config_path.exists():
            return AuraSettings()

        with self.config_path.open("r", encoding="utf-8") as file:
            raw_settings: dict[str, Any] = json.load(file)

        return AuraSettings(
            api_key=str(raw_settings.get("api_key", "")),
            base_url=str(raw_settings.get("base_url", AuraSettings.base_url)),
            model=str(raw_settings.get("model", AuraSettings.model)),
            obsidian_vault_path=str(raw_settings.get("obsidian_vault_path", "")),
            obsidian_folder=str(raw_settings.get("obsidian_folder", AuraSettings.obsidian_folder)),
        )

    def save(self, settings: AuraSettings) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config_path.open("w", encoding="utf-8") as file:
            json.dump(asdict(settings), file, indent=2, ensure_ascii=False)
            file.write("\n")
        self.config_path.chmod(0o600)

    def update_api_key(self, api_key: str) -> AuraSettings:
        settings = self.load()
        settings.api_key = api_key.strip()
        self.save(settings)
        return settings

    def update_obsidian(
        self,
        vault_path: str,
        folder: str | None = None,
    ) -> AuraSettings:
        settings = self.load()
        settings.obsidian_vault_path = vault_path.strip()
        if folder is not None:
            settings.obsidian_folder = folder.strip() or AuraSettings.obsidian_folder
        self.save(settings)
        return settings

    def delete(self) -> None:
        """Delete the local config file if it exists."""

        if self.config_path.exists():
            self.config_path.unlink()
