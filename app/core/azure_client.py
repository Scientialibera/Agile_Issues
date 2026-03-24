from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from openai import AzureOpenAI

from app.config.config import AgileConfig
from app.core.retry import retry_external_call

logger = logging.getLogger("agile_issues.openai")


class AgileExtractor:
    """Azure OpenAI client using modern tools / tool_choice API.

    Follows the RFP-SUMMARIZER pattern: every call forces a named tool so
    the model always returns structured JSON via function arguments.
    """

    def __init__(self, config: AgileConfig, schema: dict) -> None:
        client_kwargs: dict = dict(
            azure_endpoint=config.openai_endpoint,
            api_version=config.openai_api_version,
        )
        if config.use_azure_ad_auth:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider

            token_provider = get_bearer_token_provider(
                DefaultAzureCredential(),
                "https://cognitiveservices.azure.com/.default",
            )
            client_kwargs["azure_ad_token_provider"] = token_provider
        else:
            client_kwargs["api_key"] = config.openai_api_key

        self.client = AzureOpenAI(**client_kwargs)
        self.model = config.openai_model
        self.temperature = config.temperature
        self.reasoning_model = config.reasoning_model
        self.reasoning_effort = config.reasoning_effort
        self.schema = schema

    @classmethod
    def from_schema_file(cls, config: AgileConfig, schema_path: Path) -> AgileExtractor:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        return cls(config, schema)

    def extract(self, system_prompt: str, user_message: str) -> dict:
        """Call Azure OpenAI with forced tool use and return parsed arguments."""
        tools = [{"type": "function", "function": self.schema}]

        api_kwargs: dict = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            tools=tools,
            tool_choice={
                "type": "function",
                "function": {"name": self.schema["name"]},
            },
        )
        if self.reasoning_model:
            api_kwargs["reasoning_effort"] = self.reasoning_effort
        else:
            api_kwargs["temperature"] = self.temperature

        start = time.perf_counter()
        response = retry_external_call(
            self.client.chat.completions.create
        )(**api_kwargs)
        elapsed_ms = round((time.perf_counter() - start) * 1000)

        usage = response.usage
        logger.info(json.dumps({
            "event": "openai_call",
            "model": self.model,
            "tool": self.schema["name"],
            "elapsed_ms": elapsed_ms,
            "prompt_tokens": usage.prompt_tokens if usage else None,
            "completion_tokens": usage.completion_tokens if usage else None,
        }, default=str))

        choices = response.choices or []
        if not choices:
            raise ValueError("Model returned no choices.")

        message = choices[0].message
        tool_calls = message.tool_calls or []
        if not tool_calls:
            raise ValueError("Model did not return a tool call.")

        arguments = tool_calls[0].function.arguments
        if not arguments:
            raise ValueError("Tool call returned empty arguments.")
        return json.loads(arguments)

    def chat(self, system_prompt: str, user_message: str) -> str:
        """Plain chat completion (no function calling) for free-text generation."""
        api_kwargs: dict = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        if self.reasoning_model:
            api_kwargs["reasoning_effort"] = self.reasoning_effort
        else:
            api_kwargs["temperature"] = self.temperature

        response = retry_external_call(
            self.client.chat.completions.create
        )(**api_kwargs)

        choices = response.choices or []
        if not choices:
            raise ValueError("Model returned no choices.")
        return choices[0].message.content or ""
