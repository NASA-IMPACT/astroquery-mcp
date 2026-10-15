#!/usr/bin/env python3
"""Compare token usage between generic executor and optimized ADS tools."""

import pytest

pytestmark = pytest.mark.network  # calls live services; run with `pytest -m network`

import json
import sys
from auth import configure_astroquery_auth
from ads_tools import query_ads_compact
from executor import execute_function


def estimate_tokens(data):
    """Rough token estimate (chars / 4)."""
    json_str = json.dumps(data, indent=2)
    return len(json_str) // 4


def test_generic_executor():
    """Test generic executor (old way)."""
    print("=" * 70)
    print("TEST 1: Generic Executor (astroquery_execute)")
    print("=" * 70)

    try:
        result = execute_function("ads", "query_simple", {"query_string": "NGC 3783"})

        if result.get("success"):
            data = result.get("data", {})
            count = len(data.get("bibcode", []))
            tokens = estimate_tokens(result)

            print(f"✓ Query successful")
            print(f"  Papers returned: {count}")
            print(f"  Estimated tokens: {tokens:,}")

            # Show field count
            if data:
                field_count = len(data.keys())
                print(f"  Fields per paper: {field_count}")
                print(f"  Sample fields: {', '.join(list(data.keys())[:10])}...")

        return result, tokens
    except Exception as e:
        print(f"✗ Query failed: {e}")
        import traceback
        traceback.print_exc()
        return None, 0


def test_compact_query(preset="standard"):
    """Test compact query (new way)."""
    print(f"\nTEST 2: Compact Query (ads_query_compact, preset={preset})")
    print("=" * 70)

    try:
        result = query_ads_compact("NGC 3783", fields=preset, max_results=10)

        if result.get("success"):
            count = result.get("count", 0)
            tokens = estimate_tokens(result)

            print(f"✓ Query successful")
            print(f"  Papers returned: {count}")
            print(f"  Estimated tokens: {tokens:,}")
            print(f"  Fields per paper: {len(result.get('fields', []))}")
            print(f"  Fields: {', '.join(result.get('fields', []))}")

        return result, tokens
    except Exception as e:
        print(f"✗ Query failed: {e}")
        import traceback
        traceback.print_exc()
        return None, 0


def main():
    """Run comparison tests."""
    print("\n" + "=" * 70)
    print("TOKEN USAGE COMPARISON: Generic vs Optimized ADS Queries")
    print("=" * 70 + "\n")

    # Configure auth
    configure_astroquery_auth()

    # Test 1: Generic executor (all fields)
    generic_result, generic_tokens = test_generic_executor()

    # Test 2: Compact query - minimal
    print()
    minimal_result, minimal_tokens = test_compact_query("minimal")

    # Test 3: Compact query - standard
    print()
    standard_result, standard_tokens = test_compact_query("standard")

    # Test 4: Compact query - extended
    print()
    extended_result, extended_tokens = test_compact_query("extended")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY: Token Savings")
    print("=" * 70)

    if generic_tokens > 0:
        print(f"Generic executor:     {generic_tokens:>6,} tokens (baseline)")
        print(f"Compact (minimal):    {minimal_tokens:>6,} tokens ({100*(generic_tokens-minimal_tokens)//generic_tokens}% savings)")
        print(f"Compact (standard):   {standard_tokens:>6,} tokens ({100*(generic_tokens-standard_tokens)//generic_tokens}% savings)")
        print(f"Compact (extended):   {extended_tokens:>6,} tokens ({100*(generic_tokens-extended_tokens)//generic_tokens}% savings)")

    print("\n" + "=" * 70)
    print("RECOMMENDATION")
    print("=" * 70)
    print("""
For most ADS queries:
  1. Use ads_query_compact() with fields="standard" (67-75% token savings)
  2. Browse results, pick interesting papers
  3. Use ads_get_paper(bibcode) to get full details for specific papers

Only use astroquery_execute("ads", ...) when you need:
  - Advanced query features not exposed by ads_query_compact
  - Custom field lists beyond the presets
  - All 50+ fields from ADS
""")


if __name__ == "__main__":
    main()
