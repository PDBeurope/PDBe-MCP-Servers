from pathlib import Path
from typing import cast

from omegaconf import DictConfig, OmegaConf


def get_config() -> DictConfig:
    """
    Load and return configuration from config.yaml using OmegaConf.

    Returns:
        DictConfig: Configuration object from config.yaml
    """
    config_path: Path = Path(__file__).parent / "config.yaml"
    config = cast(DictConfig, OmegaConf.load(config_path))
    return config
