"""Runtime settings, all overridable through environment variables.

The client speaks the OpenAI-compatible chat completions API, so the same code
runs against local Ollama and against the team's 27B server.
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen3:14b")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
# "none" turns Qwen3 thinking off on Ollama. Set to "" to omit the field
# for servers that reject it.
LLM_REASONING_EFFORT = os.environ.get("LLM_REASONING_EFFORT", "none")
LLM_TIMEOUT_SEC = int(os.environ.get("LLM_TIMEOUT_SEC", "300"))

SEED_MAILBOX = Path(os.environ.get("SEED_MAILBOX", ROOT / "data" / "seed_mailbox.json"))
MAX_AGENT_STEPS = int(os.environ.get("MAX_AGENT_STEPS", "8"))
