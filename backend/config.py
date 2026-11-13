"""Single place where JeolAI loads its environment configuration.

Every backend module that reads configuration imports this module first, so
``.env`` is loaded before any model ID or pricing constant is evaluated,
regardless of which backend module happens to be imported first.

Previously ``load_dotenv()`` ran inside ``gemini_client.py``. ``main.py``
imports ``backend.budget`` before ``backend.gemini_client``, so budget.py read
``os.getenv`` before ``.env`` was loaded and silently used its fallbacks.

Values already present in the process environment (CI, Docker, a shell
export) take precedence over ``.env``.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# JEOLAI_ENV_FILE lets tests point at a temporary env file.
ENV_FILE = Path(os.getenv("JEOLAI_ENV_FILE") or PROJECT_ROOT / ".env")

ENV_FILE_LOADED = load_dotenv(ENV_FILE, override=False)

# Records where each setting came from so /health and tests can show whether
# a fallback was used instead of configured values.
CONFIG_SOURCES: dict[str, str] = {}


def get_str(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        CONFIG_SOURCES[name] = "default"
        return default
    CONFIG_SOURCES[name] = "env"
    return value.strip()


def get_float(name: str, default: float) -> float:
    return float(get_str(name, str(default)))


def get_int(name: str, default: int) -> int:
    return int(get_str(name, str(default)))


def defaulted_settings() -> list[str]:
    return sorted(key for key, source in CONFIG_SOURCES.items() if source == "default")
