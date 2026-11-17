"""Settings read from the environment. Every key is optional: with none set, Clawback runs offline
on the snapshots in data/ so the demo always works. See .env.example for the full list."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return default


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    # Cognee: Cognee Cloud (handed out by the Cognee team) or a self-hosted cognee server.
    cognee_url: str
    cognee_api_key: str
    cognee_dataset: str
    # Claude: reads vendor emails and writes claim emails. Without it, rules and templates take over.
    anthropic_api_key: str
    anthropic_model: str
    # Shared state between serverless calls (claims, audits, the memory log). Upstash Redis REST.
    redis_url: str
    redis_token: str
    # Fetch status pages live (falls back to data/status snapshots when a fetch fails).
    live_status: bool
    # Force every outside call off: snapshots, rules, templates, offline memory.
    demo_mode: bool

    @property
    def cognee_enabled(self) -> bool:
        return bool(self.cognee_url) and not self.demo_mode

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key) and not self.demo_mode

    @property
    def redis_enabled(self) -> bool:
        return bool(self.redis_url and self.redis_token)


def get_settings() -> Settings:
    return Settings(
        cognee_url=_env("COGNEE_URL", "COGNEE_CLOUD_URL").rstrip("/"),
        cognee_api_key=_env("COGNEE_API_KEY"),
        cognee_dataset=_env("COGNEE_DATASET", default="clawback"),
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        anthropic_model=_env("ANTHROPIC_MODEL", default="claude-sonnet-5-5"),
        # Vercel's Upstash integration names these KV_REST_API_*; Upstash's own console uses UPSTASH_*.
        redis_url=_env("UPSTASH_REDIS_REST_URL", "KV_REST_API_URL"),
        redis_token=_env("UPSTASH_REDIS_REST_TOKEN", "KV_REST_API_TOKEN"),
        live_status=_flag("CLAWBACK_LIVE_STATUS", True),
        demo_mode=_flag("CLAWBACK_DEMO", False),
    )
