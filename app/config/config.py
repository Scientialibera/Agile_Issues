from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class AgileConfig:
    """Immutable configuration for the Agile Issue Generator.

    Supports two loading strategies:
      - from_env()  : reads environment variables (production / Azure App Settings)
      - from_toml() : reads a local TOML file (local development)
    """

    openai_endpoint: str
    openai_model: str
    openai_api_key: str
    openai_api_version: str
    use_azure_ad_auth: bool
    reasoning_model: bool
    reasoning_effort: str
    temperature: float
    output_dir: str

    jira_id: str
    jira_key: str

    devops_organization: str
    devops_project: str
    devops_pat: str

    @staticmethod
    def from_env(env_path: str | Path | None = None) -> AgileConfig:
        if env_path:
            load_dotenv(dotenv_path=str(env_path))

        def _get_bool(key: str, default: bool) -> bool:
            value = os.getenv(key)
            if value is None:
                return default
            return value.strip().lower() in {"1", "true", "yes", "y"}

        return AgileConfig(
            openai_endpoint=os.environ.get("OPENAI_ENDPOINT", os.environ.get("AZURE_OPENAI_ENDPOINT", "")),
            openai_model=os.environ.get("CHAT_ENGINE", os.environ.get("AZURE_OPENAI_MODEL", "")),
            openai_api_key=os.environ.get("OPENAI_KEY", os.environ.get("AZURE_OPENAI_KEY", "")),
            openai_api_version=os.environ.get("OPENAI_API_VERSION", "2025-01-01-preview"),
            use_azure_ad_auth=_get_bool("USE_AZURE_AD_AUTH", False),
            reasoning_model=_get_bool("REASONING_MODEL", False),
            reasoning_effort=os.environ.get("REASONING_EFFORT", "medium"),
            temperature=float(os.environ.get("TEMPERATURE", "0.5")),
            output_dir=os.environ.get("OUTPUT_DIR", "./output"),
            jira_id=os.environ.get("JIRA_ID", ""),
            jira_key=os.environ.get("JIRA_KEY", ""),
            devops_organization=os.environ.get("DEVOPS_ORGANIZATION", ""),
            devops_project=os.environ.get("DEVOPS_PROJECT", ""),
            devops_pat=os.environ.get("DEVOPS_PAT", ""),
        )

    @staticmethod
    def from_toml(path: Path) -> AgileConfig:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
        azure = config.get("azure", {})
        jira = config.get("jira", {})
        devops = config.get("devops", {})
        output = config.get("output", {})

        return AgileConfig(
            openai_endpoint=azure["endpoint"],
            openai_model=azure["model"],
            openai_api_key=azure.get("api_key", ""),
            openai_api_version=azure.get("api_version", "2025-01-01-preview"),
            use_azure_ad_auth=azure.get("use_azure_ad_auth", False),
            reasoning_model=azure.get("reasoning_model", False),
            reasoning_effort=azure.get("reasoning_effort", "medium"),
            temperature=azure.get("temperature", 0.5),
            output_dir=output.get("dir", "./output"),
            jira_id=jira.get("id", ""),
            jira_key=jira.get("key", ""),
            devops_organization=devops.get("organization", ""),
            devops_project=devops.get("project", ""),
            devops_pat=devops.get("pat", ""),
        )
