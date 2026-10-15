"""Offline tests for table, coordinate and ADS result helpers."""

import numpy as np
import pytest
from astropy.table import MaskedColumn, Table

from ads_tools import filter_ads_result
from models.errors import ErrorCode, MCPError
from utils.coord_utils import angular_separation, parse_coordinates, validate_coordinates
from utils.table_utils import limit_table, select_columns, table_to_dict


class TestTableUtils:
    def test_nan_inf_and_masked_become_none(self):
        table = Table()
        table["f"] = [1.0, np.nan, np.inf]
        table["m"] = MaskedColumn([1, 2, 3], mask=[False, True, False])
        data = table_to_dict(table)["data"]
        assert [row["f"] for row in data] == [1.0, None, None]
        assert [row["m"] for row in data] == [1, None, 3]

    def test_columns_carry_units(self):
        table = Table({"ra": [1.0]})
        table["ra"].unit = "deg"
        assert table_to_dict(table)["columns"][0]["unit"] == "deg"

    def test_none_table(self):
        assert table_to_dict(None)["row_count"] == 0

    def test_select_and_limit(self):
        table = Table({"a": [1, 2, 3], "b": [4, 5, 6]})
        assert select_columns(table, exclude=["b"]).colnames == ["a"]
        assert len(limit_table(table, 2)) == 2


class TestCoordUtils:
    def test_parse_sexagesimal(self):
        coord = parse_coordinates("00h42m44.3s", "+41d16m09s")
        assert coord.ra.deg == pytest.approx(10.6846, abs=1e-3)

    def test_parse_invalid(self):
        with pytest.raises(MCPError) as exc:
            parse_coordinates("garbage", "nonsense")
        assert exc.value.code == ErrorCode.INVALID_COORDINATES

    def test_validate_ranges(self):
        assert validate_coordinates(10, 20)
        with pytest.raises(MCPError):
            validate_coordinates(400, 0)
        with pytest.raises(MCPError):
            validate_coordinates(10, 95)

    def test_angular_separation(self):
        assert angular_separation(0, 0, 0, 1) == pytest.approx(1.0)


class TestFilterAdsResult:
    @pytest.fixture
    def papers(self):
        return Table(
            {
                "bibcode": ["2020A", "2021B", "2022C"],
                "abstract": ["x" * 500, "short", "y" * 10],
                "citation_count": [5, 3, 1],
            }
        )

    def test_empty(self):
        assert filter_ads_result(None)["count"] == 0

    def test_limits_rows_and_fields(self, papers):
        result = filter_ads_result(papers, fields=["bibcode", "missing"], max_results=2)
        assert result["count"] == 2
        assert result["truncated"] is True
        assert result["fields"] == ["bibcode"]
        assert result["results"][0] == {"bibcode": "2020A"}

    def test_truncates_abstracts(self, papers):
        result = filter_ads_result(papers, truncate_abstract=20)
        assert result["results"][0]["abstract"] == "x" * 20 + "..."
        assert result["results"][1]["abstract"] == "short"

    def test_numpy_values_become_python(self, papers):
        value = filter_ads_result(papers)["results"][0]["citation_count"]
        assert type(value) is int
