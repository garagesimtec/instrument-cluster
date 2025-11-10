import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from .logger import Logger
from .telemetry.mode import TelemetryMode

LOGGER = Logger("config.py").get()


@dataclass
class Config:
    width: int = field(default=1024)
    height: int = field(default=600)
    telemetry_mode: str = field(default=TelemetryMode.DEMO.value)
    udp_host: str = field(default="127.0.0.1")
    udp_port: int = field(default=5600)
    brightness: int = 50

    @classmethod
    def parse_config(cls, path: Path) -> "Config":
        config = {}
        LOGGER.debug(
            f'Config path "{path}" exists: {path.exists()} is file: {path.is_file()}'
        )
        if path.exists() and path.is_file():
            with open(path, "r") as f:
                config = json.load(f)

        result = Config(**config)
        LOGGER.info(f"Config: {result}")

        if not path.exists():
            result.write_to_file(path)

        return result

    def write_to_file(self, path: Path) -> None:
        LOGGER.debug(f"Write config to {path}")
        config_dict = asdict(self)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config_dict, indent=4))


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

    @classmethod
    def set_telemetry_mode(cls, mode: TelemetryMode | str) -> None:
        cfg = cls.get_config()
        cfg.telemetry_mode = (
            mode.value if isinstance(mode, TelemetryMode) else TelemetryMode(mode).value
        )
        cfg.write_to_file(cls.path)

    @classmethod
    def set_brightness_percent(cls, brightness: str) -> None:
        cfg = cls.get_config()
        cfg.brightness = brightness
        cfg.write_to_file(cls.path)
