#!/usr/bin/env python3
"""Test script to verify ads_query_compact and ads_get_paper work correctly."""

import pytest

pytestmark = pytest.mark.network  # calls live services; run with `pytest -m network`

import os
import sys
from ads_tools import query_ads_compact, get_paper_details, FIELD_PRESETS
from auth import configure_astroquery_auth

def test_field_presets():
    """Test that field presets are properly defined."""
    print("=" * 60)
    print("Testing Field Presets")
    print("=" * 60)

    for preset, fields in FIELD_PRESETS.items():
        if fields:
            print(f"✓ {preset:12s}: {len(fields):2d} fields - {', '.join(fields[:3])}...")
        else:
            print(f"✓ {preset:12s}: all fields (unfiltered)")
    print()

def test_auth():
    """Test authentication configuration."""
    print("=" * 60)
    print("Testing Authentication")
    print("=" * 60)

    result = configure_astroquery_auth()
    print(f"Auth result: {result}")

    # Check for ADS token
    has_token = bool(os.environ.get("API_DEV_KEY") or os.environ.get("ADS_API_KEY"))
    if has_token:
        print("✓ ADS token found")
    else:
        print("✗ No ADS token found (queries may be rate-limited)")
    print()

def test_compact_query():
    """Test compact query with minimal fields."""
    print("=" * 60)
    print("Testing ads_query_compact (minimal)")
    print("=" * 60)

    try:
        result = query_ads_compact(
            "NGC 3783",
            fields="minimal",
            max_results=3,
        )

        print(f"✓ Query successful")
        print(f"  Results found: {result.get('count', 0)}")
        print(f"  Fields returned: {result.get('fields', [])}")
        print(f"  Preset used: {result.get('preset', 'unknown')}")

        if result.get('results'):
            print(f"\n  First result:")
            first = result['results'][0]
            for key, value in first.items():
                value_str = str(value)[:60]
                print(f"    {key}: {value_str}")

        print()
        return result
    except Exception as e:
        print(f"✗ Query failed: {e}")
        import traceback
        traceback.print_exc()
        print()
        return None

def test_paper_details(bibcode=None):
    """Test getting paper details."""
    print("=" * 60)
    print("Testing ads_get_paper")
    print("=" * 60)

    # Use provided bibcode or a known one
    test_bibcode = bibcode or "2020ApJ...901..151S"

    try:
        result = get_paper_details(test_bibcode, fields=None)

        print(f"✓ Paper lookup successful")
        print(f"  Bibcode: {result.get('bibcode', 'unknown')}")
        print(f"  Results: {result.get('count', 0)}")

        if result.get('results'):
            paper = result['results'][0]
            print(f"\n  Paper details:")
            print(f"    Title: {paper.get('title', 'N/A')}")
            print(f"    Authors: {len(paper.get('author', []))} authors")
            print(f"    Year: {paper.get('year', 'N/A')}")
            print(f"    Citations: {paper.get('citation_count', 0)}")

        print()
        return result
    except Exception as e:
        print(f"✗ Paper lookup failed: {e}")
        import traceback
        traceback.print_exc()
        print()
        return None

def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("ADS Compact Tools - Verification Tests")
    print("=" * 60 + "\n")

    # Test 1: Field presets
    test_field_presets()

    # Test 2: Authentication
    test_auth()

    # Test 3: Compact query
    query_result = test_compact_query()

    # Test 4: Paper details (use bibcode from query if available)
    bibcode = None
    if query_result and query_result.get('results'):
        bibcode = query_result['results'][0].get('bibcode')
    test_paper_details(bibcode)

    print("=" * 60)
    print("Tests Complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()
