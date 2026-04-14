"""Config loader — reads YAML project configs from configs/."""

import os
from pathlib import Path

import yaml


def load_config(config_name: str) -> dict:
    """Load a project config from configs/{name}.yaml"""
    config_dir = Path(__file__).parent.parent / "configs"
    config_path = config_dir / f"{config_name}.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_project_dir() -> str:
    return str(Path(__file__).parent.parent)


def get_project_notes_path(cfg: dict) -> str | None:
    """Expand and return project_notes_path, or None if not set."""
    path = cfg.get("project_notes_path")
    if not path:
        return None
    return os.path.expanduser(str(path))


def parse_notion_page_id(url: str) -> str | None:
    """Extract 32-char hex page ID from a Notion page URL.

    Handles:
      https://www.notion.so/workspace/Title-33f46e8c24378185934bca03f02c0369
      https://www.notion.so/33f46e8c-2437-8185-934b-ca03f02c0369
    """
    import re
    # Raw 32-char hex at end (most common Notion URL format)
    m = re.search(r'([0-9a-f]{32})$', url)
    if m:
        return m.group(1)
    # UUID format with hyphens at end
    m = re.search(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$', url)
    if m:
        return m.group(1).replace('-', '')
    return None
