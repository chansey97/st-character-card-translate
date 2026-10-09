"""Load and validate each TOML layer before merging its OpenAI settings."""

import tomllib
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from platformdirs import user_config_path

APP_NAME = "st-character-card-translate"


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class OpenAIConfig:
    base_url: str
    api_key: str
    model: str
    max_retries: int


def _load_layer(path) -> dict:
    try:
        with path.open("rb") as stream:
            document = tomllib.load(stream)
        unknown = document.keys() - {"openai"}
        if unknown:
            raise ValueError(f"Unknown tables: {', '.join(sorted(unknown))}")
        settings = document.get("openai", {})
        if not isinstance(settings, dict):
            raise ValueError("openai must be a table")
        unknown = settings.keys() - {"base_url", "api_key", "model", "max_retries"}
        if unknown:
            raise ValueError(f"Unknown openai fields: {', '.join(sorted(unknown))}")
        for name, value in settings.items():
            if name == "max_retries":
                if type(value) is not int or value < 0:
                    raise ValueError("openai.max_retries must be a nonnegative integer")
            elif not isinstance(value, str) or not value.strip():
                raise ValueError(f"openai.{name} must be a nonempty string")
        return settings
    except (OSError, ValueError) as exc:
        raise ConfigError(f"{path}: {exc}") from exc


def load_config(config_file: Path | None = None) -> OpenAIConfig:
    settings = _load_layer(files(__package__).joinpath("config.default.toml"))
    user_file = user_config_path(APP_NAME, appauthor=False) / "config.toml"
    if user_file.exists():
        settings.update(_load_layer(user_file))
    if config_file is not None:
        settings.update(_load_layer(config_file))
    return OpenAIConfig(**settings)
