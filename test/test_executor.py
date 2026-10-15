"""Offline tests for argument conversion, result serialization and dispatch."""

import numpy as np
import pytest
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.table import Table

import executor
from executor import (
    execute_function,
    get_function_info,
    list_modules,
    prepare_argument,
    serialize_result,
)
from introspection import ASTROQUERY_MODULES, introspect_class
from models.errors import ErrorCode, MCPError


class TestPrepareArgument:
    def test_coordinate_dict_becomes_skycoord(self):
        coord = prepare_argument({"ra": 10.68, "dec": 41.27}, "coordinates")
        assert isinstance(coord, SkyCoord)
        assert coord.ra.deg == pytest.approx(10.68)
        assert coord.dec.deg == pytest.approx(41.27)

    def test_radius_number_defaults_to_arcmin(self):
        assert prepare_argument(5, "radius") == 5 * u.arcmin

    def test_radius_dict_uses_given_unit(self):
        assert prepare_argument({"value": 2, "unit": "deg"}, "search_radius") == 2 * u.deg

    def test_width_number_defaults_to_arcmin(self):
        assert prepare_argument(3, "width") == 3 * u.arcmin

    def test_other_params_pass_through(self):
        assert prepare_argument("M31", "object_name") == "M31"
        assert prepare_argument(None, "radius") is None


class TestSerializeResult:
    def test_table(self):
        result = serialize_result(Table({"a": [1, 2], "b": ["x", "y"]}))
        assert result["row_count"] == 2
        assert result["data"] == [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]

    def test_list_of_tables(self):
        result = serialize_result([Table({"a": [1]}), Table({"a": [2]})])
        assert [r["data"][0]["a"] for r in result] == [1, 2]

    def test_scalar_skycoord(self):
        result = serialize_result(SkyCoord(ra=10 * u.deg, dec=20 * u.deg))
        assert result["ra_deg"] == pytest.approx(10)
        assert result["dec_deg"] == pytest.approx(20)
        assert set(result["galactic"]) == {"l", "b"}

    def test_array_skycoord(self):
        result = serialize_result(SkyCoord(ra=[1, 2] * u.deg, dec=[3, 4] * u.deg))
        assert result["count"] == 2
        assert result["ra_deg"] == pytest.approx([1, 2])

    def test_quantity(self):
        assert serialize_result(3 * u.arcsec) == {"value": 3.0, "unit": "arcsec"}

    def test_numpy_scalar_and_bytes(self):
        assert serialize_result(np.int64(4)) == 4
        assert serialize_result(b"abc") == "abc"

    def test_nested_containers(self):
        assert serialize_result({"x": [np.float64(1.5)]}) == {"x": [1.5]}


class TestMaxRows:
    big = Table({"a": list(range(30))})

    def test_single_table(self):
        result = serialize_result(self.big, max_rows=10)
        assert (result["row_count"], result["total_rows"], result["truncated"]) == (10, 30, True)
        assert result["data"][-1] == {"a": 9}

    def test_small_table_not_marked_truncated(self):
        result = serialize_result(Table({"a": [1, 2]}), max_rows=10)
        assert (result["row_count"], result["total_rows"], result["truncated"]) == (2, 2, False)

    def test_list_of_tables(self):
        # VizieR returns a TableList (a list of tables)
        result = serialize_result([self.big, self.big], max_rows=3)
        assert [r["row_count"] for r in result] == [3, 3]

    def test_tables_nested_in_dict(self):
        # Gaia load_data returns {name: [Table, ...]}
        result = serialize_result({"epoch_photometry": [self.big]}, max_rows=4)
        assert result["epoch_photometry"][0]["row_count"] == 4

    def test_no_limit_by_default(self):
        result = serialize_result(self.big)
        assert result["row_count"] == 30
        assert "truncated" not in result


class TestDispatch:
    def test_unknown_module(self):
        with pytest.raises(MCPError) as exc:
            execute_function("not_a_module", "query_object")
        assert exc.value.code == ErrorCode.VALIDATION_ERROR

    def test_unknown_function(self):
        with pytest.raises(MCPError) as exc:
            execute_function("coordinates", "no_such_function")
        assert exc.value.code == ErrorCode.VALIDATION_ERROR

    def test_bad_parameters_are_validation_errors(self):
        with pytest.raises(MCPError) as exc:
            execute_function("coordinates", "from_name", {"not_a_param": 1})
        assert exc.value.code == ErrorCode.VALIDATION_ERROR

    def test_list_modules_covers_registry(self):
        result = list_modules()
        assert result["module_count"] == len(ASTROQUERY_MODULES)
        assert {m["name"] for m in result["modules"]} == set(ASTROQUERY_MODULES)

    def test_get_function_info_describes_parameters(self, monkeypatch):
        # Discovering every archive imports modules that reach out to servers; only introspect SIMBAD
        monkeypatch.setattr(
            executor, "discover_all_functions",
            lambda: {"simbad": introspect_class("simbad", ASTROQUERY_MODULES["simbad"])},
        )
        info = get_function_info("simbad", "query_object")
        assert info["method"] == "query_object"
        assert "object_name" in {p["name"] for p in info["parameters"]}

    def test_get_function_info_unknown(self, monkeypatch):
        monkeypatch.setattr(executor, "discover_all_functions", lambda: {"simbad": []})
        assert "error" in get_function_info("simbad", "no_such_function")
