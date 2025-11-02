import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    width: int = field(default=1024)
    height: int = field(default=600)

    @classmethod
    def parse_config(cls, path: Path) -> "Config":
        config = {}
        if path.exists() and path.is_file():
            with open(path, "r") as f:
                config = json.load(f)

        result = Config(**config)

        if not path.exists():
            result.write_to_file(path)

        return result


class ConfigManager:
    path = (
        Path.home() / ".config" / "instrument-cluster" / "config.json"
    )  # default path
    _config: Optional[Config] = None

    @classmethod
    def set_path(cls, path: Path) -> None:
        cls.path = path

    @classmethod
    def get_config(cls) -> Config:
        if cls._config is None:
            cls._config = Config.parse_config(cls.path)
        return cls._config
