from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class LLMConfig:
    provider: str = ""
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.2
    max_tokens: int = 1000

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    @property
    def chat_completions_url(self) -> str:
        base_url = self.base_url.rstrip("/")
        if base_url.endswith("/chat/completions"):
            return base_url
        return f"{base_url}/chat/completions"

    def masked(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "chat_completions_url": self.chat_completions_url if self.base_url else "",
            "api_key": "***" if self.api_key else "",
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "enabled": self.enabled,
        }


def load_llm_config(config_path: str | Path = "llm_config.json") -> LLMConfig:
    path = Path(config_path)
    raw: dict[str, object] = {}
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("llm_config.json 顶层必须是 JSON 对象。")

    import os

    return LLMConfig(
        provider=str(os.environ.get("LAYOUT_REVIEW_LLM_PROVIDER") or raw.get("provider", "")),
        base_url=str(os.environ.get("LAYOUT_REVIEW_LLM_BASE_URL") or raw.get("base_url", "")),
        api_key=str(os.environ.get("LAYOUT_REVIEW_LLM_API_KEY") or raw.get("api_key", "")),
        model=str(os.environ.get("LAYOUT_REVIEW_LLM_MODEL") or raw.get("model", "")),
        temperature=float(os.environ.get("LAYOUT_REVIEW_LLM_TEMPERATURE") or raw.get("temperature", 0.2)),
        max_tokens=int(os.environ.get("LAYOUT_REVIEW_LLM_MAX_TOKENS") or raw.get("max_tokens", 1000)),
    )


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str:
        """Return a text completion from the shared LLM service."""


@dataclass
class DisabledLLMClient:
    reason: str = "LLM is not configured. Advisory prompt is returned for future integration."

    def complete(self, prompt: str) -> str:
        return self.reason


@dataclass
class OpenAICompatibleLLMClient:
    config: LLMConfig
    timeout_seconds: int = 30

    def complete(self, prompt: str) -> str:
        payload = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a shared LLM capability used by a multi-agent thesis layout review system. Never override deterministic rules.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        url = self.config.chat_completions_url
        print(f"[llm] request provider={self.config.provider or 'openai-compatible'} model={self.config.model} url={url}")
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]
