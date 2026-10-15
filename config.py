"""Configuration management for astroquery MCP server."""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class AuthConfig(BaseModel):
    """Authentication configuration for a service."""

    token_env: str = Field(description="Environment variable name for the token")


class EndpointConfig(BaseModel):
    """Service endpoint configuration."""

    tap: dict[str, str] = Field(default_factory=dict)
    sia: dict[str, str] = Field(default_factory=dict)
    ssa: dict[str, str] = Field(default_factory=dict)


class PaginationConfig(BaseModel):
    """Pagination configuration."""

    ads_rows_per_page: int = 100
    max_rows: int = 10000


class DefaultsConfig(BaseModel):
    """Default query parameters."""

    timeout: int = 60
    max_retries: int = 3
    backoff_factor: float = 2.0
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)


class RateLimitConfig(BaseModel):
    """Rate limiting configuration for a service."""

    requests_per_second: float = 10.0


class ResolverConfig(BaseModel):
    """Object resolver configuration."""

    fallback_order: list[str] = Field(
        default_factory=lambda: ["simbad", "ned", "vizier"]
    )


class SimbadConfig(BaseModel):
    """SIMBAD-specific configuration."""

    row_limit: int = 100
    resolvers: ResolverConfig = Field(default_factory=ResolverConfig)


class ArtifactsConfig(BaseModel):
    """Where downloaded science products are stored."""

    dir: str | None = Field(
        default=None,
        description="Artifact store directory; None uses the per-user cache dir. "
        "ASTROQUERY_MCP_ARTIFACT_DIR overrides this.",
    )


class ServiceConfig(BaseModel):
    """Complete service configuration."""

    version: str = "1.0"
    auth: dict[str, AuthConfig] = Field(default_factory=dict)
    endpoints: EndpointConfig = Field(default_factory=EndpointConfig)
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    rate_limits: dict[str, RateLimitConfig] = Field(default_factory=dict)
    simbad: SimbadConfig = Field(default_factory=SimbadConfig)
    artifacts: ArtifactsConfig = Field(default_factory=ArtifactsConfig)


def get_default_config() -> dict[str, Any]:
    """Return default configuration."""
    return {
        "version": "1.0",
        "auth": {
            "ads": {"token_env": "API_DEV_KEY"},
            "mast": {"token_env": "MAST_TOKEN"},
        },
        "endpoints": {
            "tap": {
                "gaia": "https://gea.esac.esa.int/tap-server/tap",
                "vizier": "http://tapvizier.u-strasbg.fr/TAPVizieR/tap",
                "heasarc": "https://heasarc.gsfc.nasa.gov/xamin/vo/tap",
                "irsa": "https://irsa.ipac.caltech.edu/TAP",
                "mast": "https://mast.stsci.edu/vo-tap/api/v0.1",
            },
            "sia": {
                "heasarc": "https://heasarc.gsfc.nasa.gov/xamin/vo/sia",
                "irsa": "https://irsa.ipac.caltech.edu/SIA",
                "mast": "https://mast.stsci.edu/vo-sia/api/v0.1",
            },
            "ssa": {},
        },
        "defaults": {
            "timeout": 60,
            "max_retries": 3,
            "backoff_factor": 2.0,
            "pagination": {
                "ads_rows_per_page": 100,
                "max_rows": 10000,
            },
        },
        "rate_limits": {
            "simbad": {"requests_per_second": 5},
            "ads": {"requests_per_second": 10},
        },
        "simbad": {
            "row_limit": 100,
            "resolvers": {
                "fallback_order": ["simbad", "ned", "vizier"],
            },
        },
    }


def load_config(config_path: str | Path | None = None) -> ServiceConfig:
    """Load configuration from YAML file and environment variables.

    Args:
        config_path: Path to YAML config file. If None, uses ASTROQUERY_MCP_CONFIG
                    env var or falls back to defaults.

    Returns:
        ServiceConfig: Validated configuration object.
    """
    # Start with defaults
    config_data = get_default_config()

    # Determine config file path
    if config_path is None:
        config_path = os.environ.get("ASTROQUERY_MCP_CONFIG")

    # Load from file if it exists
    if config_path:
        path = Path(config_path)
        if path.exists():
            with open(path) as f:
                file_config = yaml.safe_load(f)
                if file_config:
                    # Deep merge file config into defaults
                    _deep_merge(config_data, file_config)

    return ServiceConfig(**config_data)


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override into base dict, modifying base in place."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


# Global config instance (lazy loaded)
_config: ServiceConfig | None = None


def get_config() -> ServiceConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config(config_path: str | Path | None = None) -> ServiceConfig:
    """Reload configuration from file."""
    global _config
    _config = load_config(config_path)
    return _config
