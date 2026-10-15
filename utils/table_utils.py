"""Utilities for converting Astropy Tables to JSON-serializable formats."""

from typing import Any
import math

from astropy.table import Table
import numpy as np


def _make_serializable(value: Any) -> Any:
    """Convert a value to a JSON-serializable format.

    Args:
        value: Value to convert.

    Returns:
        JSON-serializable value.
    """
    if value is None:
        return None

    # Handle numpy types
    if isinstance(value, (np.integer, np.floating)):
        val = value.item()
        # Handle NaN and Inf
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return val

    if isinstance(value, np.ndarray):
        return value.tolist()

    if isinstance(value, np.bool_):
        return bool(value)

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    # Handle astropy masked values
    if hasattr(value, "mask") and value.mask:
        return None

    # Handle float NaN/Inf
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None

    return value


def table_to_records(table: Table | None) -> list[dict[str, Any]]:
    """Convert an Astropy Table to a list of dictionaries (records).

    Args:
        table: Astropy Table to convert.

    Returns:
        List of dictionaries, one per row.
    """
    if table is None or len(table) == 0:
        return []

    records = []
    columns = table.colnames

    for row in table:
        record = {}
        for col in columns:
            value = row[col]
            record[col] = _make_serializable(value)
        records.append(record)

    return records


def table_to_dict(table: Table | None, max_rows: int | None = None) -> dict[str, Any]:
    """Convert an Astropy Table to a dictionary with metadata.

    Args:
        table: Astropy Table to convert.
        max_rows: If set, convert only the first max_rows rows and add 'total_rows' and
            'truncated' so callers can tell rows were dropped.

    Returns:
        Dictionary with 'columns', 'data', 'meta' and 'row_count' (rows in 'data') keys.
    """
    if table is None:
        return {"columns": [], "data": [], "meta": {}, "row_count": 0}

    # Extract column information
    columns = []
    for col in table.colnames:
        col_info = {
            "name": col,
            "dtype": str(table[col].dtype),
        }
        if table[col].unit:
            col_info["unit"] = str(table[col].unit)
        if table[col].description:
            col_info["description"] = table[col].description
        columns.append(col_info)

    # Convert data (truncate first so huge tables are never fully converted)
    total_rows = len(table)
    data = table_to_records(table[:max_rows] if max_rows is not None else table)

    # Extract metadata
    meta = {}
    if table.meta:
        for key, value in table.meta.items():
            meta[key] = _make_serializable(value)

    result = {
        "columns": columns,
        "data": data,
        "meta": meta,
        "row_count": len(data),
    }
    if max_rows is not None:
        result["total_rows"] = total_rows
        result["truncated"] = total_rows > len(data)
    return result


def select_columns(
    table: Table,
    columns: list[str] | None = None,
    exclude: list[str] | None = None,
) -> Table:
    """Select specific columns from a table.

    Args:
        table: Input table.
        columns: List of columns to include. If None, include all.
        exclude: List of columns to exclude.

    Returns:
        Table with selected columns.
    """
    if columns is None:
        columns = list(table.colnames)

    if exclude:
        columns = [c for c in columns if c not in exclude]

    # Filter to only existing columns
    existing = [c for c in columns if c in table.colnames]

    if not existing:
        return table

    return table[existing]


def limit_table(table: Table, limit: int | None = None) -> Table:
    """Limit the number of rows in a table.

    Args:
        table: Input table.
        limit: Maximum number of rows.

    Returns:
        Table with limited rows.
    """
    if limit is None or limit <= 0:
        return table

    return table[:limit]


def sort_by_separation(
    table: Table,
    target_ra: float,
    target_dec: float,
    ra_col: str = "RA",
    dec_col: str = "DEC",
) -> Table:
    """Sort a table by angular separation from a target position.

    Args:
        table: Input table with coordinate columns.
        target_ra: Target RA in degrees.
        target_dec: Target Dec in degrees.
        ra_col: Name of the RA column.
        dec_col: Name of the Dec column.

    Returns:
        Table sorted by separation (closest first).
    """
    from utils.coord_utils import angular_separation

    if ra_col not in table.colnames or dec_col not in table.colnames:
        return table

    # Calculate separations
    separations = []
    for row in table:
        try:
            sep = angular_separation(
                target_ra, target_dec, float(row[ra_col]), float(row[dec_col])
            )
            separations.append(sep)
        except (ValueError, TypeError):
            separations.append(float("inf"))

    # Add separation column and sort
    table["_separation_deg"] = separations
    table.sort("_separation_deg")

    return table
