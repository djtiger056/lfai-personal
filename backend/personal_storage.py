"""Personal-edition storage paths.

All mutable personal-edition data should live under data/personal so it can be
backed up or moved as one folder.
"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
PERSONAL_DATA_DIR = DATA_DIR / "personal"
PERSONAL_CONFIG_PATH = PERSONAL_DATA_DIR / "config.yaml"
PERSONAL_PROMPTS_DIR = PERSONAL_DATA_DIR / "prompts"
PERSONAL_BASE_IMAGE_DIR = PERSONAL_DATA_DIR / "base_image"
PERSONAL_ACCOUNTS_DB_PATH = PERSONAL_DATA_DIR / "accounts.db"

ROOT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"
EXAMPLE_CONFIG_PATH = PROJECT_ROOT / "config.example.yaml"
LEGACY_BASE_IMAGE_DIR = DATA_DIR / "base_image"
LEGACY_ACCOUNTS_DB_PATH = DATA_DIR / "personal_accounts.db"
LEGACY_CUSTOM_PROMPT_WORDS_PATH = DATA_DIR / "custom_prompt_words.yaml"
PERSONAL_CUSTOM_PROMPT_WORDS_PATH = PERSONAL_DATA_DIR / "custom_prompt_words.yaml"


def ensure_personal_dirs() -> None:
    PERSONAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    PERSONAL_PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    PERSONAL_BASE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
