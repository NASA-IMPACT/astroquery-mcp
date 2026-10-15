#!/usr/bin/env python3
"""Test script to verify ADS authentication is working."""

import pytest

pytestmark = pytest.mark.network  # calls live services; run with `pytest -m network`

import os
import sys


def test_auth():
    """Test ADS authentication configuration."""
    print("=" * 60)
    print("ADS Authentication Test")
    print("=" * 60)

    # Check 1: Environment variable
    print("\n1. Checking environment variable:")
    api_key = os.environ.get("API_DEV_KEY")
    if api_key:
        print(f"   ✓ API_DEV_KEY is set (length: {len(api_key)})")
    else:
        print("   ✗ API_DEV_KEY is NOT set")
        print("\n   To fix:")
        print("   1. Get your token from: https://ui.adsabs.harvard.edu/user/settings/token")
        print("   2. Set it in your environment:")
        print("      export API_DEV_KEY='your-token-here'")
        return False

    # Check 2: Config file
    print("\n2. Checking config.py:")
    try:
        from config import get_config
        config = get_config()
        ads_config = config.auth.get("ads")
        if ads_config:
            print(f"   ✓ ADS config found")
            print(f"   Token env var: {ads_config.token_env}")
        else:
            print("   ✗ ADS not in config")
            return False
    except Exception as e:
        print(f"   ✗ Error loading config: {e}")
        return False

    # Check 3: Auth module
    print("\n3. Testing auth.py:")
    try:
        from auth import get_token, configure_astroquery_auth

        token = get_token("ads")
        if token:
            print(f"   ✓ get_token('ads') returned token (length: {len(token)})")
        else:
            print("   ✗ get_token('ads') returned None")
            return False

        auth_result = configure_astroquery_auth()
        if auth_result.get("ads"):
            print("   ✓ configure_astroquery_auth() succeeded")
        else:
            print("   ✗ configure_astroquery_auth() failed")
            return False

    except Exception as e:
        print(f"   ✗ Error in auth module: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Check 4: ADS module
    print("\n4. Testing astroquery.nasa_ads:")
    try:
        from astroquery.nasa_ads import ADS

        if ADS.TOKEN:
            print(f"   ✓ ADS.TOKEN is set (length: {len(ADS.TOKEN)})")
        else:
            print("   ✗ ADS.TOKEN is None")
            return False

        # Verify env var is also set (ADS checks this directly)
        if os.environ.get("API_DEV_KEY"):
            print("   ✓ API_DEV_KEY env var is still set")
        else:
            print("   ✗ API_DEV_KEY env var was cleared")
            return False

    except ImportError as e:
        print(f"   ✗ Could not import ADS: {e}")
        return False
    except Exception as e:
        print(f"   ✗ Error checking ADS: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Check 5: Try a simple query
    print("\n5. Testing simple ADS query:")
    try:
        from astroquery.nasa_ads import ADS

        # Try to query
        result = ADS.query_simple("black hole")

        if result:
            print(f"   ✓ Query succeeded! Got {len(result)} results")
            print(f"   First result title: {result[0]['title'][0][:60]}...")
        else:
            print("   ✗ Query returned empty result")
            return False

    except Exception as e:
        print(f"   ✗ Query failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n" + "=" * 60)
    print("✓ ALL TESTS PASSED - ADS authentication is working!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = test_auth()
    sys.exit(0 if success else 1)
