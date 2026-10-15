"""Authentication management for astroquery MCP server."""

import os
from typing import Any

from config import get_config
from models.errors import ErrorCode, MCPError


def get_token(service: str) -> str | None:
    """Get authentication token for a service.

    Args:
        service: Service name (e.g., 'ads', 'mast')

    Returns:
        Token string or None if not configured.
    """
    import logging
    logger = logging.getLogger(__name__)

    config = get_config()

    if service not in config.auth:
        logger.warning(f"Service {service} not found in auth config")
        return None

    token_env = config.auth[service].token_env
    token = os.environ.get(token_env)

    # Fallback for ADS: also check ADS_API_KEY if API_DEV_KEY not found
    if not token and service == "ads" and token_env == "API_DEV_KEY":
        token = os.environ.get("ADS_API_KEY")
        if token:
            logger.info(f"[get_token] Using ADS_API_KEY fallback (preferred is API_DEV_KEY)")

    # Debug logging (always log, not just debug level)
    logger.info(f"[get_token] Looking for token in env var: {token_env}")
    logger.info(f"[get_token] Token found: {bool(token)}")
    if token:
        logger.info(f"[get_token] Token length: {len(token)}")
    else:
        logger.warning(f"[get_token] Environment variable {token_env} is not set or is empty")
        # List names (never values) of env vars that start with API or ADS for debugging
        relevant_vars = sorted(k for k in os.environ if k.startswith(("API", "ADS")))
        logger.warning(f"[get_token] Available API/ADS env var names: {relevant_vars}")

    return token


def require_token(service: str) -> str:
    """Get authentication token, raising error if not found.

    Args:
        service: Service name (e.g., 'ads', 'mast')

    Returns:
        Token string.

    Raises:
        MCPError: If token is not configured.
    """
    token = get_token(service)

    if not token:
        config = get_config()
        token_env = config.auth.get(service, {})
        env_var = (
            token_env.token_env
            if hasattr(token_env, "token_env")
            else f"{service.upper()}_TOKEN"
        )

        raise MCPError(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message=f"Authentication required for {service}",
            service=service,
            recoverable=False,
            suggestion=f"Set the {env_var} environment variable with your API token",
            details={"env_var": env_var},
        )

    return token


def configure_astroquery_auth() -> dict[str, Any]:
    """Configure astroquery modules with available tokens.

    Returns:
        Dict of configured services and their status.
    """
    import logging
    logger = logging.getLogger(__name__)

    configured = {}

    logger.info("[configure_auth] Starting authentication configuration")

    # Configure ADS token
    ads_token = get_token("ads")
    logger.info(f"[configure_auth] ADS token retrieved: {bool(ads_token)}")

    if ads_token:
        try:
            from astroquery.nasa_ads import ADS

            # Set both the class attribute AND ensure env var is set
            # (ADS module checks environment variable directly in some cases)
            ADS.TOKEN = ads_token
            os.environ["API_DEV_KEY"] = ads_token

            configured["ads"] = True
            logger.info("[configure_auth] ✓ ADS authentication configured successfully")
        except ImportError as e:
            configured["ads"] = False
            logger.error(f"[configure_auth] ✗ Failed to import ADS module: {e}")
    else:
        configured["ads"] = False
        logger.warning("[configure_auth] ✗ ADS token not found in environment")

    # Configure MAST token (optional)
    logger.info("[configure_auth] Checking MAST token...")
    mast_token = get_token("mast")
    if mast_token:
        try:
            from astroquery.mast import Observations

            Observations.login(token=mast_token)
            configured["mast"] = True
            logger.info("[configure_auth] ✓ MAST authentication configured successfully")
        except (ImportError, Exception) as e:
            configured["mast"] = False
            logger.warning(f"[configure_auth] ✗ MAST configuration failed: {e}")
    else:
        logger.info("[configure_auth] MAST token not provided (optional)")

    logger.info(f"[configure_auth] Final configuration: {configured}")
    return configured


def check_auth_status() -> dict[str, dict[str, Any]]:
    """Check authentication status for all services.

    Returns:
        Dict with service names as keys and status info as values.
    """
    config = get_config()
    status = {}

    for service, auth_config in config.auth.items():
        token = os.environ.get(auth_config.token_env)
        status[service] = {
            "configured": token is not None,
            "env_var": auth_config.token_env,
            "required": service == "ads",  # Only ADS is strictly required
        }

    return status
