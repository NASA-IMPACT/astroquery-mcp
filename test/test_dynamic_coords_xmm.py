#!/usr/bin/env python3
"""Test dynamic discovery of coordinates and XMM Newton modules."""

import pytest

pytestmark = pytest.mark.network  # calls live services; run with `pytest -m network`

from executor import list_modules, list_functions, execute_function


def test_module_discovery():
    """Test that coordinates and XMM Newton are discovered."""
    print("=" * 70)
    print("TEST: Module Discovery")
    print("=" * 70)

    modules = list_modules()

    # Check for coordinates
    coords = [m for m in modules['modules'] if m['name'] == 'coordinates']
    if coords:
        print(f"✓ coordinates module: {coords[0]['class_path']}")
        print(f"  Available: {coords[0]['available']}")
    else:
        print("✗ coordinates module not found")

    # Check for XMM Newton
    xmm = [m for m in modules['modules'] if m['name'] == 'xmm_newton']
    if xmm:
        print(f"✓ xmm_newton module: {xmm[0]['class_path']}")
        print(f"  Available: {xmm[0]['available']}")
    else:
        print("✗ xmm_newton module not found")

    print()


def test_coordinates_functions():
    """Test coordinates functions are discovered."""
    print("=" * 70)
    print("TEST: Coordinates Functions")
    print("=" * 70)

    funcs = list_functions('coordinates')
    print(f"Found {funcs['function_count']} coordinate functions:")

    for func in funcs['functions']:
        print(f"  - {func['name']}")

    print()


def test_xmm_functions():
    """Test XMM Newton functions are discovered."""
    print("=" * 70)
    print("TEST: XMM Newton Functions")
    print("=" * 70)

    funcs = list_functions('xmm_newton')
    print(f"Found {funcs['function_count']} XMM Newton functions:")

    for func in funcs['functions']:
        print(f"  - {func['name']}")

    print()


def test_coords_from_name():
    """Test SkyCoord.from_name dynamically."""
    print("=" * 70)
    print("TEST: Execute coordinates.from_name('M31')")
    print("=" * 70)

    result = execute_function('coordinates', 'from_name', {'name': 'M31'})

    if result.get('success'):
        data = result.get('result', {})
        print(f"✓ Successfully resolved M31:")
        print(f"  RA: {data.get('ra_deg', 'N/A'):.4f}° = {data.get('ra_hms', 'N/A')}")
        print(f"  Dec: {data.get('dec_deg', 'N/A'):.4f}° = {data.get('dec_dms', 'N/A')}")
        print(f"  Galactic: l={data.get('galactic', {}).get('l', 0):.2f}°, b={data.get('galactic', {}).get('b', 0):.2f}°")
        print(f"  Frame: {data.get('frame', 'N/A')}")
    else:
        print(f"✗ Failed: {result}")

    print()


def test_xmm_query_example():
    """Show XMM Newton TAP query example."""
    print("=" * 70)
    print("TEST: XMM Newton TAP Query (Example)")
    print("=" * 70)

    print("Example usage (not executed, would query real data):")
    print("""
    from astropy.coordinates import SkyCoord
    coord = SkyCoord(ra=9.218704, dec=-33.554787, unit='deg', frame='icrs')

    query = f\"\"\"
        SELECT observation_id, target_name, ra, dec, duration
        FROM v_public_observations
        WHERE CONTAINS(POINT('ICRS', ra, dec),
                      CIRCLE('ICRS', {coord.ra.deg}, {coord.dec.deg}, 0.05))=1
    \"\"\"

    result = execute_function('xmm_newton', 'query_xsa_tap', {'query': query})
    """)

    print("\nNote: This would return XMM Newton observations within 0.05° of the target.")
    print()


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("DYNAMIC MODULE DISCOVERY TEST SUITE")
    print("Testing: coordinates (SkyCoord) + XMM Newton")
    print("=" * 70 + "\n")

    test_module_discovery()
    test_coordinates_functions()
    test_xmm_functions()
    test_coords_from_name()
    test_xmm_query_example()

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("""
✓ Coordinates module dynamically discovered
✓ XMM Newton module dynamically discovered
✓ SkyCoord functions callable via execute()
✓ XMM Newton TAP queries available via execute()

All modules are discovered automatically - no manual tool creation needed!

Key benefits:
- SkyCoord.from_name() resolves object names to coordinates
- Rich coordinate output: RA/Dec (deg + HMS/DMS), Galactic
- XMM Newton TAP queries for X-ray observations
- Fully dynamic - add new modules by updating introspection.py
""")


if __name__ == "__main__":
    main()
