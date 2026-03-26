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
